#!/usr/bin/env python3
"""Fetch official GSI DEM5A tiles for PLATEAU building samples and make terrain RGB.

Only tiles touched by the 4-pixel interpolation at each building footprint centroid
are downloaded. Missing tiles/no-data samples stay unknown; they are never filled
with guessed building base elevations.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import pathlib
import urllib.error
import urllib.request
from datetime import datetime, timezone

from geoengine import jprcs_ix, read_json, write_json
from fetch_ortho import world_pixel

ROOT = pathlib.Path(__file__).resolve().parents[1]
TILESET = ROOT / "data/derived/fukushima-citywide-lod1/tileset.json"
TILES_DIR = ROOT / "data/derived/fukushima-citywide-lod1/tiles"
RAW_DIR = ROOT / "data/raw/gsi_dem5a_citywide"
OUT_DIR = ROOT / "data/derived/fukushima-citywide-lod1"
ZOOM = 15
MAX_TILE_BYTES = 300_000


def tile_sample_latlon(tile: dict, building: dict) -> tuple[float, float]:
    """Inverse project the footprint ring's vertex centroid to WGS84."""
    ring = building["footprint"]
    open_ring = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    x = sum(p[0] for p in open_ring) / len(open_ring)
    z = sum(p[1] for p in open_ring) / len(open_ring)
    east = tile["tile_origin_east_m"] + x
    north = tile["tile_origin_north_m"] - z
    lat, lon = 37.8, 140.4
    for _ in range(5):
        e, n = jprcs_ix(lat, lon)
        el, nl = jprcs_ix(lat + 1e-5, lon)
        eo, no = jprcs_ix(lat, lon + 1e-5)
        a, b, c, d = (el-e)/1e-5, (eo-e)/1e-5, (nl-n)/1e-5, (no-n)/1e-5
        det = a*d-b*c
        if not math.isfinite(det) or abs(det) < 1e-8:
            raise ValueError("Cannot inverse-project a building DEM sample point")
        de, dn = east-e, north-n
        lat += (d*de-b*dn)/det
        lon += (-c*de+a*dn)/det
    return lat, lon


def pixel_tiles(lat: float, lon: float, zoom: int = ZOOM) -> set[tuple[int, int]]:
    px, py = world_pixel(lat, lon, zoom)
    x0, y0 = math.floor(px-.5), math.floor(py-.5)
    return {(x//256, y//256) for y in (y0, y0+1) for x in (x0, x0+1)}


def required_tiles(tileset: dict, tiles_dir: pathlib.Path = TILES_DIR) -> tuple[set[tuple[int, int]], int]:
    needed: set[tuple[int, int]] = set()
    count = 0
    for tile in tileset["tiles"]:
        data = read_json(tiles_dir / tile["path"].split("/", 1)[1])
        for building in data["buildings"]:
            lat, lon = tile_sample_latlon(tile, building)
            needed.update(pixel_tiles(lat, lon))
            count += 1
    return needed, count


def fetch_one(key: tuple[int, int], raw_dir: pathlib.Path) -> dict:
    x, y = key
    path = raw_dir / f"dem5a_{ZOOM}_{x}_{y}.png"
    url = f"https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{ZOOM}/{x}/{y}.png"
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "TherabbyGeoEngine/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read(MAX_TILE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"x": x, "y": y, "url": url, "status": "not_published"}
            raise
        if len(data) > MAX_TILE_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"Invalid or oversized GSI DEM5A tile: {url}")
        path.write_bytes(data)
    data = path.read_bytes()
    if len(data) > MAX_TILE_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Invalid cached GSI DEM5A tile: {path}")
    return {"x": x, "y": y, "url": url, "file": path.name,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "status": "downloaded"}


def encode_mapbox_rgb(elevation_m: float) -> tuple[int, int, int]:
    """Encode elevation using Mapbox Terrain-RGB's 0.1 m quantization."""
    value = round((elevation_m + 10000.0) * 10)
    if not 0 <= value < (1 << 24):
        raise ValueError(f"Elevation outside Mapbox Terrain-RGB range: {elevation_m}")
    return (value >> 16, (value >> 8) & 255, value & 255)


def write_terrain_rgb(entries: list[dict], raw_dir: pathlib.Path, out_dir: pathlib.Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required on the development PC to convert DEM PNG tiles") from exc
    from terrain_grid import decode_dem5a
    total_bytes = nodata_pixels = 0
    for entry in entries:
        if entry.get("status") != "downloaded":
            continue
        source = Image.open(raw_dir / entry["file"]).convert("RGB")
        if source.size != (256, 256):
            raise ValueError(f"Unexpected GSI DEM5A dimensions: {entry['file']} {source.size}")
        pixels = bytearray(256 * 256 * 3)
        source_pixels = source.tobytes()
        for index in range(256 * 256):
            start = index * 3
            rgb = source_pixels[start:start + 3]
            elevation = decode_dem5a(rgb)
            if elevation is None:
                # MapLibre Terrain-RGB has no nodata alpha convention. This is a
                # visual-only flat placeholder; building samples remain null.
                elevation = 0.0
                nodata_pixels += 1
            pixels[index*3:index*3+3] = bytes(encode_mapbox_rgb(elevation))
        output = out_dir / "terrain_rgb" / str(ZOOM) / str(entry["x"]) / f"{entry['y']}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.frombytes("RGB", (256, 256), bytes(pixels)).save(output, "PNG", optimize=True)
        entry["terrain_rgb_file"] = output.relative_to(out_dir).as_posix()
        entry["terrain_rgb_bytes"] = output.stat().st_size
        entry["terrain_rgb_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        total_bytes += output.stat().st_size
    return total_bytes, nodata_pixels


def sample_buildings(tileset: dict, tiles_dir: pathlib.Path, dem_tiles: dict,
                     output_dir: pathlib.Path) -> dict:
    from terrain_grid import sample_dem
    stats = {"sampled": 0, "unknown_missing_tile": 0, "unknown_nodata": 0}
    for tile in tileset["tiles"]:
        path = output_dir / tile["path"]
        data = read_json(path)
        for building in data["buildings"]:
            lat, lon = tile_sample_latlon(tile, building)
            try:
                value = sample_dem(dem_tiles, lat, lon, zoom=ZOOM)
            except ValueError as exc:
                building["base_elevation_m"] = None
                if "Missing GSI DEM5A tile" in str(exc):
                    building["ground_height_quality"] = "unknown: DEM5A tile unavailable"
                    stats["unknown_missing_tile"] += 1
                else:
                    building["ground_height_quality"] = "unknown: DEM5A no-data"
                    stats["unknown_nodata"] += 1
            else:
                building["base_elevation_m"] = round(value, 2)
                building["ground_height_quality"] = "GSI DEM5A ground sample at footprint vertex centroid; T.P."
                stats["sampled"] += 1
            building["vertical_datum"] = "T.P. (Tokyo Peil)" if building["base_elevation_m"] is not None else None
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
        path.write_text(raw, encoding="utf-8")
        tile["byte_length"] = path.stat().st_size
        tile["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        tile["terrain_sample_count"] = sum(1 for b in data["buildings"] if b["base_elevation_m"] is not None)
    return stats


def run(download: bool, workers: int = 4, max_total_bytes: int = 1_000_000_000,
        output_dir: pathlib.Path = OUT_DIR):
    tileset_path = output_dir / "tileset.json"
    tiles_dir = output_dir / "tiles"
    tileset = read_json(tileset_path)
    keys, buildings = required_tiles(tileset, tiles_dir)
    cap = len(keys) * MAX_TILE_BYTES
    if cap > max_total_bytes:
        raise ValueError(f"DEM5A worst-case download {cap} exceeds configured cap {max_total_bytes}")
    print(f"Buildings: {buildings}; DEM5A z15 tiles required: {len(keys)}; worst-case bytes: {cap:,}")
    if not download:
        print("DRY RUN only. Add --download to fetch official GSI elevation tiles.")
        return
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    keys = sorted(keys)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        entries = list(pool.map(lambda key: fetch_one(key, RAW_DIR), keys))
    total_source = sum(e.get("bytes", 0) for e in entries)
    if total_source > max_total_bytes:
        raise ValueError(f"Actual DEM5A bytes exceed configured cap: {total_source} > {max_total_bytes}")
    manifest = {"schema": "therabby.geoengine.source.citywide-dem5a.v0.1",
                "status": "complete", "source": "GSI DEM5A PNG elevation tiles z15",
                "vertical_datum": "T.P. (Tokyo Peil)",
                "height_quality": "5 m mesh ground terrain; buildings, bridge decks and road surfaces excluded",
                "sample_method": "bilinear interpolation at the PLATEAU clipped footprint vertex centroid",
                "source_zoom": ZOOM, "tile_count_requested": len(entries),
                "tile_count_downloaded": sum(e.get("status") == "downloaded" for e in entries),
                "tile_count_unavailable": sum(e.get("status") != "downloaded" for e in entries),
                "source_bytes": total_source, "generated_utc": datetime.now(timezone.utc).isoformat(),
                "attribution": "Geospatial Information Authority of Japan",
                "tiles": entries}
    write_json(RAW_DIR / "source_manifest.json", manifest)
    terrain_bytes, nodata_pixels = write_terrain_rgb(entries, RAW_DIR, output_dir)
    image_dir = ROOT / "data/raw/gsi_dem5a_1km"
    _, dem_tiles = __import__("terrain_grid").load_source(image_dir, "fukushima-station-east-1km")
    # Citywide tile IDs may overlap the four station preview DEM tiles. Load citywide
    # files last so each coordinate is taken from the manifest-verified source above.
    from PIL import Image
    from terrain_grid import decode_dem5a
    for entry in entries:
        if entry.get("status") == "downloaded":
            image = Image.open(RAW_DIR / entry["file"]).convert("RGB")
            dem_tiles[(entry["x"], entry["y"])] = image
    sample_stats = sample_buildings(tileset, tiles_dir, dem_tiles, output_dir)
    manifest["terrain_rgb_bytes"] = terrain_bytes
    manifest["terrain_nodata_pixels_flattened_for_preview"] = nodata_pixels
    manifest["sample_statistics"] = sample_stats
    write_json(RAW_DIR / "source_manifest.json", manifest)
    tileset["statistics"]["base_elevation_sampled"] = sample_stats["sampled"]
    tileset["statistics"]["base_elevation_unknown"] = buildings - sample_stats["sampled"]
    tileset["height_semantics"] = "Official PLATEAU measuredHeight or LOD1 geometry-derived height; T.P. terrain sample at building footprint centroid where available"
    tileset["limitations"] = [item for item in tileset.get("limitations", [])
                              if item != "Building base elevation and vertical datum are unknown and remain null."]
    tileset["limitations"].append("Building base elevation is a DEM5A ground sample at one point; no-data remains null.")
    tileset["terrain"] = {"source": "GSI DEM5A", "vertical_datum": "T.P. (Tokyo Peil)",
                          "zoom": ZOOM, "tile_template": "terrain_rgb/{z}/{x}/{y}.png",
                          "source_manifest": "../../raw/gsi_dem5a_citywide/source_manifest.json",
                          "source_manifest_sha256": hashlib.sha256((RAW_DIR/"source_manifest.json").read_bytes()).hexdigest(),
                          "attribution": manifest["attribution"],
                          "quality": "DEM5A 5 m mesh ground terrain; building centroids only; no-data remains null for base elevations"}
    write_json(tileset_path, tileset)
    print(json.dumps({**sample_stats, "terrain_rgb_bytes": terrain_bytes,
                      "nodata_pixels_flattened_for_preview": nodata_pixels}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--download", action="store_true", help="Fetch the preflighted official GSI tiles")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--max-total-bytes", type=int, default=1_000_000_000)
    p.add_argument("--output-dir", type=pathlib.Path, default=OUT_DIR)
    args = p.parse_args()
    run(args.download, args.workers, args.max_total_bytes, args.output_dir)


if __name__ == "__main__":
    main()
