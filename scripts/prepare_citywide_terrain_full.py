#!/usr/bin/env python3
"""Acquire bounded official DEM5A terrain for the whole Fukushima municipality.

Only z15 GSI tiles intersecting the official N03-2026 polygon are requested.
The preflight cap is checked before any network request.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import pathlib
import shutil

from shapely.geometry import box, shape

import geoengine
from prepare_citywide_building_dem import MAX_TILE_BYTES, ZOOM, fetch_one, write_terrain_rgb

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "modules/city-boundary/data/fukushima_city_boundary_full.geojson"
RAW = ROOT / "data/raw/gsi_dem5a_citywide_full"
OUT = ROOT / "data/derived/fukushima-citywide-terrain-v1"
PRIOR = ROOT / "data/raw/gsi_dem5a_citywide"


def city_keys(boundary_path=BOUNDARY):
    document = geoengine.read_json(boundary_path)
    region = shape(document["features"][0]["geometry"])
    if not region.is_valid or region.is_empty:
        raise ValueError("Official Fukushima boundary is invalid")
    west, south, east, north = region.bounds
    count = 1 << ZOOM
    to_x = lambda lon: math.floor((lon + 180) / 360 * count)
    to_y = lambda lat: math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * count)
    lon_at = lambda x: x / count * 360 - 180
    lat_at = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / count))))
    result = []
    for x in range(to_x(west), to_x(east) + 1):
        for y in range(to_y(north), to_y(south) + 1):
            if region.intersects(box(lon_at(x), lat_at(y + 1), lon_at(x + 1), lat_at(y))):
                result.append((x, y))
    return sorted(result), [west, south, east, north]


def run(download=False, max_total_bytes=1_000_000_000, workers=8):
    keys, bounds = city_keys()
    cap = len(keys) * MAX_TILE_BYTES
    if cap > max_total_bytes:
        raise ValueError(f"DEM5A worst-case download {cap:,} exceeds cap {max_total_bytes:,}")
    print(f"Municipal DEM5A tiles: {len(keys)}; worst-case bytes: {cap:,}", flush=True)
    if not download:
        return
    RAW.mkdir(parents=True, exist_ok=True)
    previous = geoengine.read_json(PRIOR / "source_manifest.json")
    known = {(item["x"], item["y"]): item for item in previous["tiles"] if item.get("status") == "downloaded"}
    reused = 0
    for x, y in keys:
        item = known.get((x, y))
        if item is None:
            continue
        source = PRIOR / item["file"]
        target = RAW / item["file"]
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Cached DEM5A tile hash mismatch: {source}")
        if not target.exists():
            shutil.copyfile(source, target)
        reused += 1
    print(f"Reused {reused} previously verified DEM5A tiles", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        entries = list(pool.map(lambda key: fetch_one(key, RAW), keys))
    bytes_total = sum(item.get("bytes", 0) for item in entries)
    if bytes_total > max_total_bytes:
        raise ValueError(f"DEM5A bytes {bytes_total:,} exceed cap {max_total_bytes:,}")
    rgb_bytes, no_data_pixels = write_terrain_rgb(entries, RAW, OUT)
    missing = sum(item["status"] != "downloaded" for item in entries)
    manifest = {"schema": "therabby.geoengine.source.citywide-dem5a-full.v0.1",
                "status": "complete_with_gaps" if missing else "complete",
                "source": "GSI DEM5A z15 PNG elevation tiles",
                "source_url_template": "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png",
                "boundary_source": "MLIT N03-2026 Fukushima City 07201",
                "boundary_sha256": hashlib.sha256(BOUNDARY.read_bytes()).hexdigest(),
                "bounds_lon_lat": bounds, "zoom": ZOOM, "vertical_datum": "T.P. (Tokyo Peil)",
                "attribution": "© Geospatial Information Authority of Japan",
                "quality": "5 m mesh ground terrain; no road deck or building foundation height",
                "statistics": {"requested": len(entries), "reused_from_building_dem": reused,
                               "available": len(entries)-missing, "unavailable": missing,
                               "source_bytes": bytes_total, "terrain_rgb_bytes": rgb_bytes,
                               "preview_no_data_pixels_flattened_to_zero": no_data_pixels},
                "tiles": entries}
    geoengine.write_json(RAW / "source_manifest.json", manifest)
    geoengine.write_json(OUT / "tileset.json", manifest)
    print(json.dumps(manifest["statistics"], ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--max-total-bytes", type=int, default=1_000_000_000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(args.download, args.max_total_bytes, args.workers)


if __name__ == "__main__":
    main()
