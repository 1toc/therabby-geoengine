#!/usr/bin/env python3
"""Prepare a 300 m official-photo LOD2 overlay for the EPSG:6677 citywide viewer.

Only the two already downloaded 2025 CityGML meshes are read. Geometry keeps
its source-relative heights; a DEM5A sample from the corresponding LOD1 tile
anchors each building for *visual display*. This is not a vertical datum
conversion or a surveyed foundation elevation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import shutil
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import geoengine  # noqa: E402

AREA = ROOT / "config/fukushima_station_east_300m.json"
SOURCE_DIR = ROOT / "data/raw/plateau/fukushima_citywide_2025"
SOURCE_MANIFEST = SOURCE_DIR / "source_manifest.json"
TEXTURE_DIR = ROOT / "data/raw/plateau"
LOD1_TILESET = ROOT / "data/derived/fukushima-citywide-lod1-v2/tileset.json"
OUTPUT = ROOT / "data/derived/fukushima-station-lod2-overlay"
SOURCE_NAMES = ("56405306_bldg_6697_op.gml", "56405307_bldg_6697_op.gml")
SCHEMA = "therabby.geoengine.station-lod2-overlay.v0.1"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_sources(manifest: dict) -> tuple[list[pathlib.Path], list[dict]]:
    if (manifest.get("status") != "complete" or manifest.get("municipality_code") != "07201"
            or manifest.get("dataset_year") != 2025):
        raise ValueError("Expected complete official Fukushima City 2025 source manifest")
    by_name = {entry["filename"]: entry for entry in manifest["files"]}
    selected = []
    for name in SOURCE_NAMES:
        entry = by_name[name]
        path = SOURCE_DIR / name
        if not path.is_file() or path.stat().st_size != entry["file_size"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"Source CityGML size/hash mismatch: {name}")
        if entry.get("max_lod", 0) < 2:
            raise ValueError(f"Source catalog does not declare LOD2: {name}")
        selected.append(entry)
    return [SOURCE_DIR / item["filename"] for item in selected], selected


def index_lod1(tile_manifest: dict) -> tuple[dict, dict]:
    if (tile_manifest.get("status") != "complete" or
            "EPSG:6677" not in tile_manifest.get("projected_crs", "") or
            tile_manifest.get("terrain", {}).get("vertical_datum") != "T.P. (Tokyo Peil)"):
        raise ValueError("Expected completed EPSG:6677 LOD1 tiles with DEM5A T.P. bases")
    buildings, tiles = {}, {}
    for tile in tile_manifest["tiles"]:
        if tile["id"] not in ("55_194", "55_195"):
            continue
        source = LOD1_TILESET.parent / tile["path"]
        if sha256(source) != tile["sha256"]:
            raise ValueError(f"Official LOD1 tile hash mismatch: {tile['id']}")
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("tile_id") != tile["id"]:
            raise ValueError(f"Official LOD1 tile ID mismatch: {tile['id']}")
        tiles[tile["id"]] = tile
        for building in data["buildings"]:
            if building["id"] in buildings:
                raise ValueError(f"Duplicate official building ID: {building['id']}")
            buildings[building["id"]] = (tile, building)
    if set(tiles) != {"55_194", "55_195"}:
        raise ValueError("Station area source tile coverage changed")
    return buildings, tiles


def tile_surface(surface: dict, area_origin: tuple[float, float], tile: dict, base_tp: float) -> dict:
    east0, north0 = area_origin
    result = {key: value for key, value in surface.items() if key != "rings"}
    rings = []
    for ring in surface["rings"]:
        points = []
        for x, z, relative_height in ring:
            east, north = east0 + x, north0 - z
            local_x = east - tile["tile_origin_east_m"]
            local_z = tile["tile_origin_north_m"] - north
            y = base_tp + relative_height
            if not all(math.isfinite(v) for v in (local_x, local_z, y)):
                raise ValueError("Non-finite LOD2 coordinate")
            points.append([round(local_x, 3), round(local_z, 3), round(y, 3)])
        rings.append(points)
    result["rings"] = rings
    return result


def fetch_photos(buildings: list[dict], entries: list[dict], output: pathlib.Path,
                 download: bool) -> list[dict]:
    source_map = {"provenance": [{"name": "PLATEAU CityGML", "source_files": list(SOURCE_NAMES)}],
                  "buildings": buildings}
    file_list = {"files": entries}
    urls = geoengine.texture_requests(source_map, file_list)
    if not urls:
        raise ValueError("The selected LOD2 geometry has no official photographic UVs")
    prior = output / "source_photos.json"
    prior_files = ({item["uri"]: item for item in geoengine.read_json(prior).get("files", [])}
                   if prior.is_file() else {})
    legacy = TEXTURE_DIR / "texture_file_list.json"
    legacy_files = ({item["uri"]: item for item in geoengine.read_json(legacy).get("files", [])}
                    if legacy.is_file() else {})
    records, total = [], 0
    for uri, url in sorted(urls.items()):
        target = TEXTURE_DIR / pathlib.PurePosixPath(uri)
        if not target.exists():
            if not download:
                raise FileNotFoundError(f"Missing official photo: {uri}; rerun with --fetch-photos")
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_suffix(".jpg.part")
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "TherabbyGeoEngine/1.0",
                                                               "Accept": "image/jpeg"})
                with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as stream:
                    if response.status != 200 or not response.headers.get("Content-Type", "").startswith("image/jpeg"):
                        raise ValueError(f"Unexpected official photo response: {uri}")
                    size = response.headers.get("Content-Length")
                    if size and int(size) > 20_000_000:
                        raise ValueError(f"Official photo too large: {uri}")
                    copied = 0
                    while chunk := response.read(256 * 1024):
                        copied += len(chunk)
                        if copied > 20_000_000:
                            raise ValueError(f"Official photo too large: {uri}")
                        stream.write(chunk)
                if part.read_bytes()[:2] != b"\xff\xd8":
                    raise ValueError(f"Official photo is not JPEG: {uri}")
                part.replace(target)
            except Exception:
                part.unlink(missing_ok=True)
                raise
        size = target.stat().st_size
        total += size
        if total > 250_000_000:
            raise ValueError("Selected official photo assets exceed 250 MB")
        checksum = sha256(target)
        for known in (legacy_files.get(uri), prior_files.get(uri)):
            if known and (known["source_url"] != url or known["bytes"] != size or known["sha256"] != checksum):
                raise ValueError(f"Previously recorded official photo changed: {uri}")
        records.append({"uri": uri, "source_url": url, "bytes": size, "sha256": checksum})
    output.mkdir(parents=True, exist_ok=True)
    geoengine.write_json(output / "source_photos.json", {
        "source": "Project PLATEAU / Fukushima City 2025", "downloaded_or_verified_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": records, "bytes": total, "redistribution_status": "internal_preview_pending_dataset_terms"})
    return records


def prepare_texture_variants(records: list[dict], output: pathlib.Path) -> dict:
    """Create bounded-resolution derivatives; the official JPEGs remain untouched."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required on the development PC to build photo quality variants") from exc
    variants = {}
    for name, max_edge in (("low", 512), ("medium", 1024)):
        root = output / f"textures-{name}"
        pixel_count = byte_count = 0
        for record in records:
            source = TEXTURE_DIR / pathlib.PurePosixPath(record["uri"])
            target = root / pathlib.PurePosixPath(record["uri"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as image:
                if image.format != "JPEG":
                    raise ValueError(f"Photo is not JPEG: {record['uri']}")
                if max(image.size) <= max_edge:
                    shutil.copyfile(source, target)
                    dimensions = image.size
                else:
                    image.draft("RGB", (max_edge, max_edge))
                    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                    dimensions = image.size
                    image.save(target, format="JPEG", quality=88, subsampling=0, optimize=True)
            pixel_count += dimensions[0] * dimensions[1]
            byte_count += target.stat().st_size
        variants[name] = {"texture_root": root.name, "max_edge_px": max_edge,
                          "image_pixels": pixel_count, "jpeg_bytes": byte_count,
                          "rgba8_mip_estimate_bytes": math.ceil(pixel_count * 4 * 4 / 3)}
    pixel_count = 0
    for record in records:
        with Image.open(TEXTURE_DIR / pathlib.PurePosixPath(record["uri"])) as image:
            pixel_count += image.width * image.height
    variants["high"] = {"texture_root": str(TEXTURE_DIR.relative_to(ROOT)).replace('\\', '/'),
                        "max_edge_px": None, "image_pixels": pixel_count,
                        "jpeg_bytes": sum(record["bytes"] for record in records),
                        "rgba8_mip_estimate_bytes": math.ceil(pixel_count * 4 * 4 / 3)}
    return variants


def build(output: pathlib.Path = OUTPUT, download: bool = False) -> dict:
    area = geoengine.load_area(AREA)
    if (area["half_size_m"] != 150 or area["projection"] != "JGD2011_JPRCS_IX_GRS80"
            or area["plateau_year"] != 2025):
        raise ValueError("Station LOD2 area must be 300 m, projected, and from 2025")
    source_manifest = geoengine.read_json(SOURCE_MANIFEST)
    source_paths, source_entries = checked_sources(source_manifest)
    candidates, _ = geoengine.plateau_buildings(source_paths, area, include_lod2=True)
    selected = [building for building in candidates if building.get("lod2_surfaces")]
    lod1_manifest = geoengine.read_json(LOD1_TILESET)
    lod1_by_id, source_tiles = index_lod1(lod1_manifest)
    if not selected or len({building["id"] for building in selected}) != len(selected):
        raise ValueError("No unique station LOD2 building set")
    photo_records = fetch_photos(selected, source_entries, output, download)
    variants = prepare_texture_variants(photo_records, output)
    origin = geoengine.jprcs_ix(area["center_lat"], area["center_lon"])
    groups = {tile_id: [] for tile_id in source_tiles}
    for building in selected:
        if building["id"] not in lod1_by_id:
            raise ValueError(f"LOD2 building lacks official citywide LOD1 match: {building['id']}")
        tile, lod1 = lod1_by_id[building["id"]]
        base = lod1.get("base_elevation_m")
        if (lod1.get("vertical_datum") != "T.P. (Tokyo Peil)" or
                not isinstance(base, (int, float)) or not math.isfinite(base)):
            raise ValueError(f"LOD2 building has no compatible DEM5A visual anchor: {building['id']}")
        groups[tile["id"]].append({
            "id": building["id"], "base_elevation_m": base,
            "lod2_surfaces": [tile_surface(s, origin, tile, base) for s in building["lod2_surfaces"]]})
    entries = []
    for tile_id, buildings in groups.items():
        if not buildings:
            continue
        scene = {"schema": "therabby.geoengine.station-lod2-scene.v0.1", "tile_id": tile_id,
                 "projected_crs": "EPSG:6677", "render_vertical_frame": "T.P. (Tokyo Peil) via DEM5A visual base",
                 "source_vertical_status": "CityGML relative height only; no EPSG:6697/4979 to T.P. height conversion",
                 "buildings": buildings}
        scene_path = output / f"scene_{tile_id}.json"
        geoengine.write_json(scene_path, scene)
        source_tile = source_tiles[tile_id]
        entries.append({"id": tile_id, "tile_origin_east_m": source_tile["tile_origin_east_m"],
                        "tile_origin_north_m": source_tile["tile_origin_north_m"],
                        "scene": scene_path.name, "scene_sha256": sha256(scene_path),
                        "source_lod1_tile": source_tile["path"], "source_lod1_sha256": source_tile["sha256"],
                        "replaced_building_ids": sorted(b["id"] for b in buildings),
                        "lod2_buildings": len(buildings), "lod2_surfaces": sum(len(b["lod2_surfaces"]) for b in buildings),
                        "lod2_glb": f"lod2_{tile_id}.glb", "lod1_filtered_glb": f"lod1_filtered_{tile_id}.glb"})
    result = {"schema": SCHEMA, "status": "prepared", "scope": "300 m square centred on Fukushima Station east; intersecting buildings may cross bounds",
              "projected_crs": "JGD2011 / Japan Plane Rectangular CS IX (EPSG:6677)",
              "render_vertical_frame": "T.P. (Tokyo Peil) via DEM5A visual base",
              "vertical_accuracy": "Unverified visual anchoring: source relative LOD2 geometry + DEM5A sample at LOD1 footprint representative point; not surveyed or a datum conversion",
              "area": {"center_lat": area["center_lat"], "center_lon": area["center_lon"],
                       "center_east_m": origin[0], "center_north_m": origin[1], "half_size_m": 150},
              "source_manifest": str(SOURCE_MANIFEST.relative_to(ROOT)).replace('\\', '/'),
              "source_manifest_sha256": sha256(SOURCE_MANIFEST),
              "source_citygml": [{"path": str(path.relative_to(ROOT)).replace('\\', '/'), "sha256": entry["sha256"]}
                                 for path, entry in zip(source_paths, source_entries)],
              "source_lod1_tileset": str(LOD1_TILESET.relative_to(ROOT)).replace('\\', '/'),
              "source_lod1_tileset_sha256": sha256(LOD1_TILESET),
              "source_photos": "source_photos.json", "source_photos_sha256": sha256(output / "source_photos.json"),
              "quality_variants": variants,
              "official_photo_count": len(photo_records), "official_photo_surfaces": sum(
                  bool(s.get("texture_uri")) for b in selected for s in b["lod2_surfaces"]),
              "lod2_buildings": len(selected), "lod2_surfaces": sum(len(b["lod2_surfaces"]) for b in selected),
              "tiles": entries, "attribution": "Project PLATEAU / Fukushima City 2025; GSI DEM5A ground visual anchor",
              "redistribution_status": "internal_preview_pending_dataset_terms",
              "limitations": ["Vertical placement is a terrain-relative visual alignment, not a geodetic height conversion.",
                              "Some walls have no official photo UV and use a plain PBR material.",
                              "Detailed LOD2 geometry is only supplied for the selected 300 m station area."]}
    geoengine.write_json(output / "tileset.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    parser.add_argument("--fetch-photos", action="store_true", help="Fetch only missing official JPEGs (250 MB cap)")
    args = parser.parse_args()
    result = build(args.output, args.fetch_photos)
    print(f"Prepared {result['lod2_buildings']} LOD2 buildings, {result['official_photo_count']} official photos, {len(result['tiles'])} source tiles")


if __name__ == "__main__":
    main()
