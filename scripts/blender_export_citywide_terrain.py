#!/usr/bin/env python3
"""Export seam-aligned GSI DEM5A ground meshes as static GLB tiles.

Only cells with four valid DEM samples become triangles. Unknown heights are
holes; the exporter does not infer road decks or building foundations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/derived/fukushima-citywide-terrain-meshes/tileset.json"
OUT = ROOT / "data/derived/fukushima-citywide-terrain-glb"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_mesh(data):
    size = data["grid_cells"]
    samples = data["vertices_x_south_height"]
    if len(samples) != (size + 1) ** 2:
        raise ValueError(f"Terrain grid size mismatch: {data['tile_id']}")
    vertices, mapping = [], {}
    for index, (x, south, height) in enumerate(samples):
        if height is not None:
            mapping[index] = len(vertices)
            # Blender is Z-up. glTF export_yup maps this to X east,
            # Y absolute T.P. height, Z south.
            vertices.append((x, -south, height))
    faces = []
    for row in range(size):
        for col in range(size):
            a = row * (size + 1) + col
            b, c, d = a + 1, a + size + 2, a + size + 1
            if all(index in mapping for index in (a, b, c, d)):
                faces.extend(((mapping[a], mapping[c], mapping[b]),
                              (mapping[a], mapping[d], mapping[c])))
    mesh = bpy.data.meshes.new(f"DEM5A_{data['tile_id']}_geometry")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    material = bpy.data.materials.new("GSI DEM5A ground / T.P.")
    material.diffuse_color = (.38, .53, .42, 1)
    material.use_nodes = True
    material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (.38, .53, .42, 1)
    material.use_backface_culling = False
    mesh.materials.append(material)
    obj = bpy.data.objects.new(f"DEM5A_{data['tile_id']}", mesh)
    bpy.context.collection.objects.link(obj)
    obj["source"] = "Geospatial Information Authority of Japan DEM5A"
    obj["vertical_datum"] = "T.P. (Tokyo Peil)"
    obj["ground_only"] = True
    return obj, {"valid_vertices": len(vertices), "triangles": len(faces),
                 "missing_vertices": len(samples) - len(vertices)}


def run(source_path=SOURCE, output_dir=OUT, tile_id=None):
    source_path = pathlib.Path(source_path).resolve()
    output_dir = pathlib.Path(output_dir).resolve()
    manifest = json.loads(source_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "therabby.geoengine.citywide-terrain-mesh-inputs.v0.1" or
            manifest.get("vertical_datum") != "T.P. (Tokyo Peil)" or
            "EPSG:6677" not in manifest.get("projected_crs", "")):
        raise ValueError("Unexpected terrain mesh input CRS or vertical datum")
    selected = [item for item in manifest["tiles"] if tile_id is None or item["id"] == tile_id]
    if not selected:
        raise ValueError(f"Unknown DEM5A tile: {tile_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for number, item in enumerate(selected, 1):
        path = source_path.parent / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Terrain mesh input SHA-256 mismatch: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("tile_id") != item["id"]:
            raise ValueError(f"Terrain mesh input tile ID mismatch: {path}")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        obj, stats = build_mesh(data)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        glb = output_dir / f"{item['id']}.glb"
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True,
                                  export_extras=True, export_yup=True)
        records.append({"id": item["id"], "glb": glb.name,
                        "byte_length": glb.stat().st_size, "sha256": sha256(glb),
                        "tile_origin_east_m": item["tile_origin_east_m"],
                        "tile_origin_north_m": item["tile_origin_north_m"],
                        "source_mesh_input": item["path"], "source_sha256": item["sha256"],
                        **stats})
        if number == 1 or number % 100 == 0 or number == len(selected):
            print(f"[{number}/{len(selected)}] {item['id']}: {stats['triangles']} triangles", flush=True)
    result = {"schema": "therabby.geoengine.citywide-terrain-glb.v0.1",
              "status": "complete_with_gaps" if manifest["status"] != "complete" else "complete",
              "projected_crs": manifest["projected_crs"], "vertical_datum": manifest["vertical_datum"],
              "axes": "X east, Y up, Z south; source-tile-local X/Z, absolute T.P. Y",
              "source_manifest": str(source_path.relative_to(ROOT)).replace('\\', '/'),
              "source_manifest_sha256": sha256(source_path),
              "attribution": manifest["attribution"], "quality": manifest["quality"],
              "statistics": {"tiles": len(records), "triangles": sum(r["triangles"] for r in records),
                             "bytes": sum(r["byte_length"] for r in records),
                             "missing_vertices": sum(r["missing_vertices"] for r in records),
                             "unpublished_source_tiles": manifest["statistics"]["unpublished_source_tiles"]},
              "tiles": records}
    (output_dir / "tileset.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["statistics"], ensure_ascii=False), flush=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=SOURCE)
    parser.add_argument("--output-dir", type=pathlib.Path, default=OUT)
    parser.add_argument("--tile-id")
    args = parser.parse_args(argv)
    run(args.source, args.output_dir, args.tile_id)


if __name__ == "__main__":
    main()
