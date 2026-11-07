#!/usr/bin/env python3
"""Create clearly approximate, low-detail distant building mass tiles.

Each 50 m cell becomes one box based on official LOD1 footprints/heights.
These boxes are visual LOD only; they are not building geometry or road data.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
import statistics
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/derived/fukushima-citywide-lod1-v2/tileset.json"
OUT = ROOT / "data/derived/fukushima-citywide-far-glb"
CELL_M = 50


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def footprint_area(points):
    if len(points) < 3:
        return 0
    return abs(sum(x * points[(i + 1) % len(points)][1] -
                   z * points[(i + 1) % len(points)][0]
                   for i, (x, z) in enumerate(points)) / 2)


def build_far_mesh(buildings, tile_id):
    groups = collections.defaultdict(list)
    skipped = 0
    for building in buildings:
        base = building.get("base_elevation_m")
        if base is None:
            skipped += 1
            continue
        if building.get("vertical_datum") != "T.P. (Tokyo Peil)" or building.get("lod") != "LOD1":
            raise ValueError(f"Unsupported vertical datum/LOD: {building.get('id')}")
        ring = building["footprint"]
        xs = [point[0] for point in ring]
        zs = [point[1] for point in ring]
        cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
        area = max(1, footprint_area(ring) - sum(footprint_area(h) for h in building.get("holes", [])))
        height = float(building["height_m"])
        if not all(math.isfinite(v) for v in (cx, cz, area, base, height)) or height <= 0:
            raise ValueError(f"Non-finite building mass: {building.get('id')}")
        groups[math.floor(cx / CELL_M), math.floor(cz / CELL_M)].append((cx, cz, area, base, height))
    vertices, faces = [], []
    for samples in groups.values():
        area_sum = sum(item[2] for item in samples)
        cx = sum(item[0] * item[2] for item in samples) / area_sum
        cz = sum(item[1] * item[2] for item in samples) / area_sum
        base = statistics.median(item[3] for item in samples)
        heights = sorted(item[4] for item in samples)
        height = heights[math.floor((len(heights) - 1) * .75)]
        side = min(45, max(4, math.sqrt(area_sum) * .8))
        x0, x1, z0, z1 = cx-side/2, cx+side/2, cz-side/2, cz+side/2
        start = len(vertices)
        # Blender Z-up -> glTF Y-up: (east, north, T.P. height).
        vertices.extend(((x0,-z1,base),(x1,-z1,base),(x1,-z0,base),(x0,-z0,base),
                         (x0,-z1,base+height),(x1,-z1,base+height),
                         (x1,-z0,base+height),(x0,-z0,base+height)))
        for quad in ((0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0),(4,7,6,5)):
            faces.append(tuple(start + index for index in quad))
    mesh = bpy.data.meshes.new(f"far_building_masses_{tile_id}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    material = bpy.data.materials.new("Approximate distant building masses")
    material.diffuse_color = (.31, .53, .50, 1)
    material.use_nodes = True
    material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (.31, .53, .50, 1)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(f"DISTANT_APPROX_{tile_id}", mesh)
    bpy.context.collection.objects.link(obj)
    obj["source"] = "Project PLATEAU / Fukushima City 2025 LOD1"
    obj["quality"] = "approximate visual mass, 50 m cells; not official building footprint"
    obj["collision_ready"] = False
    return obj, {"cells": len(groups), "source_buildings": len(buildings)-skipped,
                 "skipped_no_ground_sample": skipped, "triangles": len(faces)*2}


def run(source_path=SOURCE, output_dir=OUT, tile_id=None):
    source_path = pathlib.Path(source_path).resolve()
    output_dir = pathlib.Path(output_dir).resolve()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if source.get("schema") != "therabby.geoengine.citywide-lod1-tiles.v0.1" or \
            source.get("status") != "complete" or "EPSG:6677" not in source.get("projected_crs", "") or \
            source.get("terrain", {}).get("vertical_datum") != "T.P. (Tokyo Peil)":
        raise ValueError("Expected complete EPSG:6677 LOD1 tiles with T.P. DEM5A samples")
    selected = [item for item in source["tiles"] if tile_id is None or item["id"] == tile_id]
    if not selected:
        raise ValueError(f"Unknown tile ID: {tile_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for number, item in enumerate(selected, 1):
        path = source_path.parent / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Source tile hash mismatch: {item['id']}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("tile_id") != item["id"] or len(data["buildings"]) != item["building_count"]:
            raise ValueError(f"Source tile mismatch: {item['id']}")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        obj, stats = build_far_mesh(data["buildings"], item["id"])
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        glb = output_dir / f"{item['id']}.glb"
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True,
                                  export_extras=True, export_yup=True)
        records.append({"id": item["id"], "glb": glb.name, "byte_length": glb.stat().st_size,
                        "sha256": sha256(glb), "tile_origin_east_m": item["tile_origin_east_m"],
                        "tile_origin_north_m": item["tile_origin_north_m"],
                        "source_tile": item["path"], "source_sha256": item["sha256"], **stats})
        if number == 1 or number % 25 == 0 or number == len(selected):
            print(f"[{number}/{len(selected)}] {item['id']}: {stats['cells']} far cells", flush=True)
    result = {"schema": "therabby.geoengine.citywide-far-glb.v0.1",
              "status": "complete" if len(selected) == len(source["tiles"]) else "partial",
              "projected_crs": source["projected_crs"], "vertical_datum": "T.P. (Tokyo Peil)",
              "axes": "X east, Y up, Z south; tile-local X/Z, absolute T.P. Y",
              "visual_quality": "approximate 50 m cell building mass; not an official footprint or height for individual structures",
              "attribution": source["attribution"],
              "source_tileset": str(source_path.relative_to(ROOT)).replace('\\', '/'),
              "source_tileset_sha256": sha256(source_path),
              "statistics": {"tiles": len(records), "cells": sum(r["cells"] for r in records),
                             "source_buildings": sum(r["source_buildings"] for r in records),
                             "skipped_no_ground_sample": sum(r["skipped_no_ground_sample"] for r in records),
                             "triangles": sum(r["triangles"] for r in records),
                             "bytes": sum(r["byte_length"] for r in records)},
              "tiles": records}
    (output_dir / "tileset.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result["statistics"], ensure_ascii=False), flush=True)


def main():
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=SOURCE)
    parser.add_argument("--output-dir", type=pathlib.Path, default=OUT)
    parser.add_argument("--tile-id")
    args = parser.parse_args(argv)
    run(args.source, args.output_dir, args.tile_id)


if __name__ == "__main__":
    main()
