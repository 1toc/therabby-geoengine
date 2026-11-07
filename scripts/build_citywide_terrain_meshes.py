#!/usr/bin/env python3
"""Sample official DEM5A to seam-aligned 32x32-cell terrain mesh inputs.

Missing DEM5A pixels remain null. These JSON grids are inputs to the Blender
GLB exporter and are never presented as surveyed road-deck heights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib

import geoengine
from terrain_grid import sample_dem

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/gsi_dem5a_citywide_full/source_manifest.json"
RAW = SOURCE.parent
OUT = ROOT / "data/derived/fukushima-citywide-terrain-meshes"
GRID = 32
ZOOM = 15


def lon_lat_at_pixel(px, py):
    scale = (1 << ZOOM) * 256
    lon = px / scale * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / scale))))
    return lon, lat


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source_manifest=SOURCE, output_dir=OUT):
    from PIL import Image
    source_manifest = pathlib.Path(source_manifest).resolve()
    output_dir = pathlib.Path(output_dir).resolve()
    manifest = geoengine.read_json(source_manifest)
    if (manifest.get("schema") != "therabby.geoengine.source.citywide-dem5a-full.v0.1" or
            manifest.get("vertical_datum") != "T.P. (Tokyo Peil)" or manifest.get("zoom") != ZOOM):
        raise ValueError("Expected verified GSI DEM5A citywide z15 source")
    available = [item for item in manifest["tiles"] if item.get("status") == "downloaded"]
    images = {}
    for item in available:
        path = source_manifest.parent / item["file"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"DEM5A source hash mismatch: {path}")
        image = Image.open(path).convert("RGB")
        if image.size != (256, 256):
            raise ValueError(f"DEM5A tile is not 256x256: {path}")
        images[(item["x"], item["y"])] = image
    (output_dir / "tiles").mkdir(parents=True, exist_ok=True)
    records = []
    valid_total = missing_total = 0
    for number, item in enumerate(available, 1):
        x, y = item["x"], item["y"]
        lon0, lat0 = lon_lat_at_pixel(x*256, y*256)
        east0, north0 = geoengine.jprcs_ix(lat0, lon0)
        vertices = []
        valid = 0
        for row in range(GRID + 1):
            for col in range(GRID + 1):
                lon, lat = lon_lat_at_pixel(x*256 + col*256/GRID,
                                            y*256 + row*256/GRID)
                east, north = geoengine.jprcs_ix(lat, lon)
                try:
                    height = sample_dem(images, lat, lon, ZOOM)
                except ValueError:
                    height = None
                if height is not None:
                    valid += 1
                vertices.append([round(east-east0, 3), round(north0-north, 3),
                                 round(height, 3) if height is not None else None])
        tile_id = f"{ZOOM}_{x}_{y}"
        payload = {"schema": "therabby.geoengine.terrain-mesh-input.v0.1",
                   "tile_id": tile_id, "grid_cells": GRID,
                   "projected_crs": "EPSG:6677", "vertical_datum": "T.P. (Tokyo Peil)",
                   "tile_origin_east_m": east0, "tile_origin_north_m": north0,
                   "vertices_x_south_height": vertices}
        path = output_dir / "tiles" / f"{tile_id}.json"
        geoengine.write_json(path, payload)
        records.append({"id": tile_id, "path": f"tiles/{tile_id}.json",
                        "source_file": item["file"], "source_sha256": item["sha256"],
                        "valid_samples": valid, "missing_samples": len(vertices)-valid,
                        "tile_origin_east_m": east0, "tile_origin_north_m": north0,
                        "byte_length": path.stat().st_size, "sha256": sha256(path)})
        valid_total += valid
        missing_total += len(vertices)-valid
        if number == 1 or number % 100 == 0 or number == len(available):
            print(f"[{number}/{len(available)}] {tile_id}: valid={valid} missing={len(vertices)-valid}", flush=True)
    result = {"schema": "therabby.geoengine.citywide-terrain-mesh-inputs.v0.1",
              "status": "complete_with_gaps" if manifest["statistics"]["unavailable"] or missing_total else "complete",
              "source_manifest": str(source_manifest.relative_to(ROOT)).replace('\\', '/'),
              "source_manifest_sha256": sha256(source_manifest),
              "projected_crs": "JGD2011 / Japan Plane Rectangular CS IX (EPSG:6677)",
              "vertical_datum": "T.P. (Tokyo Peil)",
              "attribution": manifest["attribution"],
              "quality": "GSI DEM5A ground elevation; no-data remains null; not road deck height",
              "grid_cells_per_source_tile": GRID,
              "statistics": {"mesh_inputs": len(records), "valid_samples": valid_total,
                             "missing_samples": missing_total,
                             "unpublished_source_tiles": manifest["statistics"]["unavailable"]},
              "tiles": records}
    geoengine.write_json(output_dir / "tileset.json", result)
    print(json.dumps(result["statistics"], ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=pathlib.Path, default=SOURCE)
    parser.add_argument("--output-dir", type=pathlib.Path, default=OUT)
    args = parser.parse_args()
    build(args.source_manifest, args.output_dir)


if __name__ == "__main__":
    main()
