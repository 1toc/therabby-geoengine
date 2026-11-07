#!/usr/bin/env python3
"""Export OSM fallback building footprints as visibly distinct GLB tiles.

Run with Blender's bundled Python after build_citywide_osm_buildings.py.
The input JSON keeps each footprint's OSM way ID and height-quality field.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from blender_export_citywide_lod1 import build_tile_mesh, sha256

DEFAULT_TILESET = ROOT / "data/derived/fukushima-citywide-osm-buildings-v1/tileset.json"
DEFAULT_OUT = ROOT / "data/derived/fukushima-citywide-osm-buildings-glb"


def run(tileset_path, output_dir, tile_id=None):
    tileset_path, output_dir = pathlib.Path(tileset_path).resolve(), pathlib.Path(output_dir).resolve()
    source = json.loads(tileset_path.read_text(encoding="utf-8"))
    if (source.get("schema") != "therabby.geoengine.citywide-osm-building-tiles.v0.1" or
            source.get("status") != "complete_with_known_limits" or
            "EPSG:6677" not in source.get("projected_crs", "") or
            source.get("ground_vertical_datum") != "T.P. (Tokyo Peil)" or
            source.get("license") != "ODbL 1.0"):
        raise ValueError("Expected OSM fallback source with explicit EPSG:6677, T.P. and ODbL quality")
    selected = [item for item in source["tiles"] if tile_id is None or item["id"] == tile_id]
    if not selected:
        raise ValueError(f"Unknown OSM fallback building tile: {tile_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for number, tile in enumerate(selected, 1):
        source_path = tileset_path.parent / tile["path"]
        if sha256(source_path) != tile["sha256"]:
            raise ValueError(f"Source tile SHA-256 mismatch: {tile['id']}")
        data = json.loads(source_path.read_text(encoding="utf-8"))
        if data.get("schema") != "therabby.geoengine.osm-building-tile.v0.1" or \
                data.get("tile_id") != tile["id"] or len(data.get("buildings", [])) != tile["building_count"]:
            raise ValueError(f"OSM tile ID/schema/building count mismatch: {tile['id']}")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        obj, stats = build_tile_mesh(data["buildings"], tile["id"], "osm_fallback")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        glb = output_dir / f"{tile['id']}.glb"
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True,
                                  export_extras=True, export_yup=True)
        entries.append({"id": tile["id"], "glb": glb.name, "byte_length": glb.stat().st_size,
                        "sha256": sha256(glb), "source_tile": tile["path"],
                        "source_tile_sha256": tile["sha256"],
                        "tile_origin_east_m": tile["tile_origin_east_m"],
                        "tile_origin_north_m": tile["tile_origin_north_m"],
                        "tile_size_m": source["tile_size_m"], **stats})
        if number == 1 or number % 10 == 0 or number == len(selected):
            print(f"[{number}/{len(selected)}] {tile['id']}: {stats['buildings']} OSM buildings", flush=True)
    manifest = {"schema": "therabby.geoengine.citywide-osm-building-glb.v0.1",
                "status": "complete_with_known_limits" if len(selected) == len(source["tiles"]) else "partial",
                "projected_crs": source["projected_crs"], "vertical_datum": "T.P. (Tokyo Peil)",
                "axes": "X east, Y up, Z south; tile-local X/Z, absolute T.P. Y",
                "source_tileset": str(tileset_path.relative_to(ROOT)).replace('\\', '/'),
                "source_tileset_sha256": sha256(tileset_path),
                "source_pbf_sha256": source["source_pbf_sha256"],
                "official_coverage_sha256": source["official_coverage_sha256"],
                "attribution": source["attribution"], "license": source["license"],
                "visual_quality": "real OSM footprints outside official source meshes; untextured and height possibly estimated; not PLATEAU LOD1",
                "limitations": source["limitations"], "tiles": entries,
                "statistics": {"tiles": len(entries),
                               "buildings": sum(item["buildings"] for item in entries),
                               "skipped_no_ground_sample": sum(item["skipped_no_ground_sample"] for item in entries),
                               "triangles": sum(item["triangles"] for item in entries),
                               "bytes": sum(item["byte_length"] for item in entries)}}
    (output_dir / "tileset.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest["statistics"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tileset", type=pathlib.Path, default=DEFAULT_TILESET)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--tile-id")
    args = parser.parse_args(argv)
    run(args.tileset, args.output_dir, args.tile_id)
