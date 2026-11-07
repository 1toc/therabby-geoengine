#!/usr/bin/env python3
"""Build a self-contained, local-only static preview from audited assets.

This is not a public v1.0 release. Dataset-specific redistribution terms,
survey anchors and baseline PC performance must be accepted separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "dist/citywide-v1-preview"
ASSET_DIRS = (
    "fukushima-citywide-lod1-glb",
    "fukushima-citywide-osm-buildings-glb",
    "fukushima-citywide-far-glb",
    "fukushima-citywide-terrain-glb",
    "fukushima-citywide-roads-v1",
)
STATIC_FILES = (
    "docs/STATION_V03_PILOT.md",
    "docs/STATION_V03_STREAMING.md",
    "docs/WALKING_QA.md",
    "docs/evidence/station_photo_stream_cached_stress.json",
    "docs/evidence/station_photo_stream_stress.json",
    "docs/evidence/station_photo_stream_all10.json",
    "docs/evidence/station_photo_stream_failure.json",
    "docs/evidence/station_photo_stream_budget.json",
    "docs/evidence/station_photo_stream_ab.png",
    "docs/evidence/station_photo_stream_ab.json",
    "docs/evidence/station_photo_stream_c.png",
    "docs/evidence/station_photo_pilot_log.json",
    "viewer/geoengine-photo-pilot.js",
    "viewer/geoengine-photo-stream.js",
    "viewer/geoengine-walk-collision.js",
    "viewer/station-texture-comparison.html",
    "viewer/station-texture-comparison.js",
    "viewer/station-style-profiles.js",
    "data/derived/station-photo-pilot/pilot.json",
    "data/derived/station-photo-pilot/stream.json",
    "data/derived/station-photo-pilot/stream-full.json",
    "data/derived/station-photo-pilot/official.jpg",
    "OPEN_ME_FIRST.txt",
    "start_citywide_benchmark.cmd", "start_station_lod2.cmd", "serve_citywide_preview.ps1",
    "verify_citywide_preview.ps1",
    "viewer/citywide-v1.html", "viewer/citywide-v1.js",
    "viewer/geoengine-station-roads-v02.js",
    "viewer/geoengine-citywide-api.js", "docs/CITYWIDE_ATTRIBUTION.md",
    "docs/CITYWIDE_V1_STATUS.md",
    "docs/CITYWIDE_RELEASE_RIGHTS_REVIEW.md",
    "docs/PHASE6_PROVISIONAL_CLOSEOUT.md",
    "docs/V1_ACCEPTANCE_PROCEDURE.md",
    "docs/STATION_LOD2_INTEGRATION.md",
    "docs/STATION_V02_ROADS_TEXTURES.md",
    "docs/evidence/station_texture_v02_audit.json",
    "docs/evidence/station_texture_v02_source_variants.png",
    "docs/evidence/station_photo_v02_browser_low_vs_source.png",
    "docs/evidence/station_photo_v02_browser_low_vs_source.json",
    "data/derived/fukushima-station-roads-v02/road_extent.json",
    "data/derived/fukushima-station-roads-v02/visual_terrain.json",
    "docs/evidence/geoengine-citywide-2026-10-31T21-57-31-614Z.json",
    "docs/evidence/geoengine-citywide-2026-11-01T05-33-54-406Z.json",
    "docs/evidence/geoengine-citywide-2026-11-02T09-52-57-038Z.json",
    "data/derived/fukushima-citywide-release-audit.json",
    "data/raw/plateau/fukushima_citywide_2025/source_manifest.json",
    "data/raw/gsi_dem5a_citywide_full/source_manifest.json",
    "data/derived/fukushima-road-source-snapshot/index.json",
)


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def package(output=DEFAULT_OUT):
    output = pathlib.Path(output).resolve()
    if not output.is_relative_to(ROOT / "dist") or output == ROOT / "dist":
        raise ValueError("Preview output must be a child of the project dist directory")
    audit_path = ROOT / "data/derived/fukushima-citywide-release-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("asset_integrity") != "passed" or audit.get("schema") != "therabby.geoengine.citywide-release-audit.v0.1":
        raise ValueError("A passing citywide asset audit is required")
    sources = {ROOT / relative for relative in STATIC_FILES}
    stream_dir = ROOT / "data/derived/station-photo-pilot"
    for filename, expected_count in (("stream.json", 10), ("stream-full.json", 117)):
        stream = json.loads((stream_dir / filename).read_text(encoding="utf-8"))
        if stream.get("schema") != "therabby.station-photo-stream.v0.3" or \
                "EPSG:6677" not in stream.get("projected_crs", "") or len(stream.get("photos", [])) != expected_count:
            raise ValueError(f"Station photo stream manifest is invalid: {filename}")
        for photo in stream["photos"]:
            image = (stream_dir / photo["jpeg"]).resolve()
            if not image.is_relative_to(stream_dir) or image.stat().st_size != photo["byte_length"] or \
                    digest(image) != photo["sha256"]:
                raise ValueError(f"Stream photo absent or changed: {image}")
            sources.add(image)
    sources.update((ROOT / "viewer/vendor/three").rglob("*"))
    sources = {path for path in sources if path.is_file()}
    counts = {}
    for name in ASSET_DIRS:
        directory = ROOT / "data/derived" / name
        manifest = json.loads((directory / "tileset.json").read_text(encoding="utf-8"))
        expected = {
            "fukushima-citywide-lod1-glb": "building",
            "fukushima-citywide-osm-buildings-glb": "osmBuilding",
            "fukushima-citywide-far-glb": "far",
            "fukushima-citywide-terrain-glb": "terrain",
            "fukushima-citywide-roads-v1": "road",
        }[name]
        if len(manifest["tiles"]) != audit["verified"][f"{expected}_files"]:
            raise ValueError(f"Tile count differs from audit: {name}")
        counts[expected] = len(manifest["tiles"])
        sources.add(directory / "tileset.json")
        for item in manifest["tiles"]:
            file = (directory / item.get("glb", item.get("path", ""))).resolve()
            if not file.is_relative_to(directory) or not file.is_file() or \
                    file.stat().st_size != item["byte_length"] or digest(file) != item["sha256"]:
                raise ValueError(f"Tile absent or changed since audit: {file}")
            sources.add(file)
        if expected == "road":
            sources.add(directory / "search_index.json")
    photo_dir = ROOT / "data/derived/fukushima-station-lod2-overlay"
    photo_manifest_path = photo_dir / "tileset.json"
    if photo_manifest_path.is_file():
        photo = json.loads(photo_manifest_path.read_text(encoding="utf-8"))
        if (photo.get("schema") != "therabby.geoengine.station-lod2-overlay.v0.1" or
                photo.get("status") != "complete" or "EPSG:6677" not in photo.get("projected_crs", "")):
            raise ValueError("Station LOD2 overlay is incomplete or has unsupported CRS")
        sources.add(photo_manifest_path)
        sources.add(photo_dir / photo["source_photos"])
        for tile in photo["tiles"]:
            for key in ("lod1_filtered", "lod2_low", "lod2_medium", "lod2_high"):
                record = tile[key]
                asset = (photo_dir / record["path"]).resolve()
                if not asset.is_relative_to(photo_dir) or not asset.is_file() or \
                        asset.stat().st_size != record["byte_length"] or digest(asset) != record["sha256"]:
                    raise ValueError(f"Station LOD2 GLB absent or changed: {asset}")
                sources.add(asset)
        counts["station_lod2_buildings"] = photo["lod2_buildings"]
    road_v02 = json.loads((ROOT / "data/derived/fukushima-station-roads-v02/road_extent.json").read_text(encoding="utf-8"))
    if (road_v02.get("schema") != "therabby.geoengine.station-road-corridor.v0.2" or
            road_v02.get("status") != "complete" or road_v02.get("projected_crs") != "EPSG:6677" or
            road_v02.get("road_count") != len(road_v02.get("roads", [])) or
            road_v02.get("terrain", {}).get("vertical_datum") != "T.P. (Tokyo Peil)"):
        raise ValueError("Station v0.2 roads have unsupported provenance or coordinates")
    counts["station_road_corridors"] = road_v02["road_count"]
    output.mkdir(parents=True, exist_ok=True)
    files = []
    for source in sorted(sources):
        source = source.resolve()
        if not source.is_relative_to(ROOT):
            raise ValueError(f"Source escapes project root: {source}")
        relative = source.relative_to(ROOT)
        target = output / relative
        if not target.resolve().is_relative_to(output):
            raise ValueError(f"Preview target escapes output: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        checksum = digest(source)
        if not target.exists() or target.stat().st_size != source.stat().st_size or digest(target) != checksum:
            shutil.copy2(source, target)
        if digest(target) != checksum:
            raise ValueError(f"Preview copy verification failed: {target}")
        files.append({"path": relative.as_posix(), "byte_length": target.stat().st_size,
                      "sha256": checksum})
    package_manifest = {
        "schema": "therabby.geoengine.citywide-static-preview.v0.1",
        "status": "internal_preview; v1.0 acceptance pending",
        "entry": "viewer/citywide-v1.html",
        "acceptance_complete": audit["v1_0_acceptance_complete"],
        "tile_counts": counts, "files": files,
        "limitations": audit["not_verified"],
    }
    manifest_path = output / "preview_manifest.json"
    manifest_path.write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "files": len(files),
                      "bytes": sum(item["byte_length"] for item in files),
                      "tile_counts": counts, "acceptance_complete": audit["v1_0_acceptance_complete"]},
                     ensure_ascii=True))
    return package_manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    package(args.output)
