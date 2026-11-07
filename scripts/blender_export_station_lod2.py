"""Build official-photo station GLBs and matching LOD1-without-duplicates GLBs.

Run in Blender 3.1: blender --background --python-exit-code 1 --python
scripts/blender_export_station_lod2.py -- --overlay data/derived/fukushima-station-lod2-overlay/tileset.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from blender_export import add_lod2_buildings  # noqa: E402
from blender_export_citywide_lod1 import build_tile_mesh  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        bpy.data.images.remove(image)


def export(objects, path):
    if not objects:
        raise ValueError(f"No objects to export: {path}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_extras=True, export_yup=True, export_apply=True,
                              export_cameras=False, export_lights=False)
    if path.stat().st_size < 1024:
        raise ValueError(f"Empty GLB: {path}")
    return {"path": path.name, "byte_length": path.stat().st_size, "sha256": sha256(path)}


def run(overlay_path):
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    if (overlay.get("schema") != "therabby.geoengine.station-lod2-overlay.v0.1" or
            overlay.get("status") not in ("prepared", "complete") or
            "EPSG:6677" not in overlay.get("projected_crs", "") or
            overlay.get("render_vertical_frame") != "T.P. (Tokyo Peil) via DEM5A visual base"):
        raise ValueError("Unsupported station overlay manifest/coordinate frame")
    for tile in overlay["tiles"]:
        scene_path = overlay_path.parent / tile["scene"]
        lod1_path = ROOT / overlay["source_lod1_tileset"]
        lod1_tile_path = lod1_path.parent / tile["source_lod1_tile"]
        if sha256(scene_path) != tile["scene_sha256"] or sha256(lod1_tile_path) != tile["source_lod1_sha256"]:
            raise ValueError(f"Station source hash mismatch: {tile['id']}")
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        lod1 = json.loads(lod1_tile_path.read_text(encoding="utf-8"))
        removed = set(tile["replaced_building_ids"])
        if (scene.get("tile_id") != tile["id"] or lod1.get("tile_id") != tile["id"] or
                {b["id"] for b in scene["buildings"]} != removed or
                not removed.issubset({b["id"] for b in lod1["buildings"]})):
            raise ValueError(f"LOD1/LOD2 building ID set mismatch: {tile['id']}")
        filtered = [building for building in lod1["buildings"] if building["id"] not in removed]
        clear_scene()
        obj, stats = build_tile_mesh(filtered, tile["id"])
        tile["lod1_filtered"] = export([obj], overlay_path.parent / tile["lod1_filtered_glb"])
        tile["lod1_filtered"]["buildings"] = stats["buildings"]
        tile["lod1_filtered"]["skipped_no_ground_sample"] = stats["skipped_no_ground_sample"]
        for variant, detail in overlay["quality_variants"].items():
            clear_scene()
            texture_root = (ROOT / detail["texture_root"] if variant == "high"
                            else overlay_path.parent / detail["texture_root"])
            objects = add_lod2_buildings(scene, texture_root)
            for obj in objects:
                obj["geometry_source"] = "Project PLATEAU / Fukushima City 2025 LOD2"
                obj["texture_source"] = "official PLATEAU JPEG, resized" if variant != "high" else "official PLATEAU JPEG"
                obj["vertical_quality"] = overlay["vertical_accuracy"]
            path = overlay_path.parent / f"lod2_{variant}_{tile['id']}.glb"
            tile[f"lod2_{variant}"] = export(objects, path)
            tile[f"lod2_{variant}"]["buildings"] = tile["lod2_buildings"]
        print(f"{tile['id']}: {tile['lod2_buildings']} LOD2 buildings; LOD1 replacement {stats['buildings']} buildings", flush=True)
    overlay["status"] = "complete"
    overlay["render_quality"] = "official photo UVs where available; other thematic surfaces use plain PBR; no AI redraw"
    overlay["tested_outputs"] = "GLB size/SHA-256 recorded at export; browser rendering and baseline-PC FPS require separate checks"
    overlay_path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Completed station LOD2 GLBs", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", type=pathlib.Path,
                        default=ROOT / "data/derived/fukushima-station-lod2-overlay/tileset.json")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    run(args.overlay.resolve())


if __name__ == "__main__":
    main()
