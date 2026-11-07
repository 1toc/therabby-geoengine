#!/usr/bin/env python3
"""Build an editable Fukushima Station scene from audited citywide tiles.

Run with Blender's bundled Python. The scene uses local Blender X east,
Y north, Z T.P. elevation. Full source tiles intersecting the configured
area are included; meshes are not cropped at the area rectangle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys

import bpy
from mathutils import Vector

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from geoengine import jprcs_ix, load_area

DEFAULT_AREA = ROOT / "config/fukushima_station_east_1km.json"
DEFAULT_OUTPUT = ROOT / "dist/real/fukushima-station-citywide/fukushima_station_citywide.blend"
ASSETS = {
    "official_buildings": ("fukushima-citywide-lod1-glb", "therabby.geoengine.citywide-lod1-glb.v0.1"),
    "osm_fallback_buildings": ("fukushima-citywide-osm-buildings-glb", "therabby.geoengine.citywide-osm-building-glb.v0.1"),
    "terrain": ("fukushima-citywide-terrain-glb", "therabby.geoengine.citywide-terrain-glb.v0.1"),
}
ROAD_DIR = ROOT / "data/derived/fukushima-citywide-roads-v1"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path, schema, vertical=True):
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema") != schema or "EPSG:6677" not in data.get("projected_crs", "") or
            data.get("status") not in ("complete", "complete_with_gaps", "complete_with_known_limits") or
            not isinstance(data.get("tiles"), list) or
            (vertical and data.get("vertical_datum") != "T.P. (Tokyo Peil)")):
        raise ValueError(f"Unsupported source schema, CRS or vertical datum: {path}")
    return data


def intersects_tile(tile, east, north, half):
    # GLB tile origin is its north-west corner. DEM5A source tiles are
    # slightly smaller than 1 km, so this conservative box may include an
    # adjacent full tile without leaving a gap in the requested area.
    west = tile["tile_origin_east_m"]
    top = tile["tile_origin_north_m"]
    return west < east + half and west + 1000 > east - half and \
        top > north - half and top - 1000 < north + half


def create_collection(name):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def import_glb_tile(path, tile, collection, east, north, kind):
    if path.stat().st_size != tile["byte_length"] or sha256(path) != tile["sha256"]:
        raise ValueError(f"GLB differs from audited manifest: {path}")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = set(bpy.data.objects) - before
    if not any(obj.type == "MESH" for obj in imported):
        raise ValueError(f"GLB has no mesh: {path}")
    for obj in imported:
        for old_collection in tuple(obj.users_collection):
            old_collection.objects.unlink(obj)
        collection.objects.link(obj)
        obj["tile_id"] = tile["id"]
        obj["source_glb"] = str(path.relative_to(ROOT)).replace("\\", "/")
        obj["source_sha256"] = tile["sha256"]
        obj["source_kind"] = kind
        if obj.parent is None:
            obj.location.x += tile["tile_origin_east_m"] - east
            obj.location.y += tile["tile_origin_north_m"] - north
    return len(imported)


def road_material(name, color):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*color, 1)
    return material


def known_no_tag(value):
    return str(value or "").lower() in ("", "no", "false", "0")


def add_roads(tile, collection, east, north, materials):
    groups = {}
    counts = {"displayed_ground_centerlines": 0, "unknown_ground": 0, "bridge_or_tunnel": 0}
    for edge in tile["edges"]:
        h0, h1 = edge["ground_height_from_tp_m"], edge["ground_height_to_tp_m"]
        if not (isinstance(h0, (int, float)) and isinstance(h1, (int, float)) and
                math.isfinite(h0) and math.isfinite(h1)):
            counts["unknown_ground"] += 1
            continue
        if not (known_no_tag(edge.get("bridge_osm_tag")) and known_no_tag(edge.get("tunnel_osm_tag"))):
            counts["bridge_or_tunnel"] += 1
            continue
        road_class = "walk" if edge.get("road_class") == "walk" else \
            "major" if edge.get("road_class") == "major" else "local"
        if road_class not in groups:
            groups[road_class] = bpy.data.curves.new(f"roads_{tile['tile_id']}_{road_class}", "CURVE")
            groups[road_class].dimensions = "3D"
            groups[road_class].resolution_u = 1
            groups[road_class].bevel_depth = 0.12
            groups[road_class].bevel_resolution = 0
            groups[road_class].materials.append(materials[road_class])
        spline = groups[road_class].splines.new("POLY")
        spline.points.add(1)
        for point, height, target in zip(edge["points"], (h0, h1), spline.points):
            target.co = (tile["tile_origin_east_m"] + point[0] - east,
                         tile["tile_origin_north_m"] - point[1] - north,
                         height + 0.18, 1)
        counts["displayed_ground_centerlines"] += 1
    for road_class, curve in groups.items():
        obj = bpy.data.objects.new(f"OSM_{tile['tile_id']}_{road_class}_centerlines", curve)
        collection.objects.link(obj)
        obj["source"] = "OpenStreetMap / Geofabrik Tohoku"
        obj["license"] = "ODbL 1.0"
        obj["quality"] = "OSM centerline at GSI DEM5A ground height; not road deck or surveyed width"
        obj["tile_id"] = tile["tile_id"]
    return counts


def add_camera(scene):
    camera_data = bpy.data.cameras.new("Station overview camera")
    camera = bpy.data.objects.new("Station overview camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (-950, -1200, 1150)
    target = Vector((0, 0, 70))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 2850
    camera_data.clip_end = 10000
    scene.camera = camera
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_location = target
                area.spaces.active.region_3d.view_distance = 1900
                area.spaces.active.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
                area.spaces.active.clip_end = 10000
                area.spaces.active.shading.color_type = "MATERIAL"


def run(area_path=DEFAULT_AREA, output=DEFAULT_OUTPUT):
    area_path, output = pathlib.Path(area_path).resolve(), pathlib.Path(output).resolve()
    if not output.is_relative_to(ROOT / "dist") or output.suffix.lower() != ".blend":
        raise ValueError("Blender scene must be a .blend below project dist")
    area = load_area(area_path)
    if area.get("projection") != "JGD2011_JPRCS_IX_GRS80":
        raise ValueError("Station scene requires declared JGD2011 / EPSG:6677 coordinates")
    east, north = jprcs_ix(area["center_lat"], area["center_lon"])
    half = area["half_size_m"]
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene["projected_crs"] = "JGD2011 / EPSG:6677"
    scene["vertical_datum"] = "T.P. (Tokyo Peil)"
    scene["local_axes"] = "X east, Y north, Z T.P. height, metres"
    scene["origin_east_m"] = east
    scene["origin_north_m"] = north
    scene["area_config"] = str(area_path.relative_to(ROOT)).replace("\\", "/")
    scene["status"] = "Internal editing preview; v1.0 acceptance and redistribution pending"
    scene["quality_limits"] = "PLATEAU LOD1 is untextured; DEM5A is ground only; OSM roads are centerlines"
    source_records = {}
    counts = {}
    for kind, (directory, schema) in ASSETS.items():
        source_dir = ROOT / "data/derived" / directory
        manifest_path = source_dir / "tileset.json"
        manifest = read_manifest(manifest_path, schema)
        selected = [tile for tile in manifest["tiles"] if intersects_tile(tile, east, north, half)]
        collection = create_collection({"official_buildings": "PLATEAU 2025 LOD1 (official)",
                                        "osm_fallback_buildings": "OSM fallback buildings (estimated height)",
                                        "terrain": "GSI DEM5A ground (T.P.)"}[kind])
        for tile in selected:
            import_glb_tile(source_dir / tile["glb"], tile, collection, east, north, kind)
        counts[kind] = len(selected)
        source_records[kind] = {"manifest": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
                                "manifest_sha256": sha256(manifest_path),
                                "tiles": [{"id": tile["id"], "sha256": tile["sha256"]} for tile in selected]}
        print(f"{kind}: {len(selected)} GLB tiles", flush=True)
    if not counts["official_buildings"] or not counts["terrain"]:
        raise ValueError("Station scene has no official buildings or ground tiles")
    road_manifest_path = ROAD_DIR / "tileset.json"
    road_manifest = read_manifest(road_manifest_path, "therabby.geoengine.citywide-road-tiles.v0.1", False)
    road_tiles = [tile for tile in road_manifest["tiles"] if
                  tile["bbox_east_north_m"][0] < east + half and
                  tile["bbox_east_north_m"][2] > east - half and
                  tile["bbox_east_north_m"][1] < north + half and
                  tile["bbox_east_north_m"][3] > north - half]
    roads_collection = create_collection("OSM roads (ground centerlines only)")
    materials = {"major": road_material("OSM major centerline", (0.91, 0.55, 0.24)),
                 "local": road_material("OSM local centerline", (0.85, 0.81, 0.63)),
                 "walk": road_material("OSM walking path centerline", (0.7, 0.86, 0.65))}
    road_counts = {"displayed_ground_centerlines": 0, "unknown_ground": 0, "bridge_or_tunnel": 0}
    road_sources = []
    for meta in road_tiles:
        path = ROAD_DIR / meta["path"]
        if path.stat().st_size != meta["byte_length"] or sha256(path) != meta["sha256"]:
            raise ValueError(f"Road tile differs from audited manifest: {path}")
        tile = json.loads(path.read_text(encoding="utf-8"))
        if (tile.get("schema") != "therabby.geoengine.citywide-road-tile.v0.1" or
                tile.get("projected_crs") != "EPSG:6677" or
                tile.get("tile_id") != meta["id"] or len(tile.get("edges", [])) != meta["edge_count"]):
            raise ValueError(f"Unexpected road tile format: {path}")
        result = add_roads(tile, roads_collection, east, north, materials)
        for key, value in result.items():
            road_counts[key] += value
        road_sources.append({"id": meta["id"], "sha256": meta["sha256"]})
    counts["road_tiles"] = len(road_tiles)
    source_records["roads"] = {"manifest": str(road_manifest_path.relative_to(ROOT)).replace("\\", "/"),
                               "manifest_sha256": sha256(road_manifest_path), "tiles": road_sources}
    add_camera(scene)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_shadows = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    output.parent.mkdir(parents=True, exist_ok=True)
    preview = output.with_name(output.stem + "_preview.png")
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(preview)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    bpy.ops.render.render(write_still=True)
    sidecar = {"schema": "therabby.geoengine.station-blend-provenance.v0.1",
               "status": "internal_editing_preview; v1.0 acceptance and redistribution pending",
               "blend": output.name, "blend_bytes": output.stat().st_size, "blend_sha256": sha256(output),
               "preview": preview.name, "preview_sha256": sha256(preview),
               "area_config": str(area_path.relative_to(ROOT)).replace("\\", "/"),
               "area_config_sha256": sha256(area_path),
               "center_lat": area["center_lat"], "center_lon": area["center_lon"],
               "center_east_m": east, "center_north_m": north, "requested_half_size_m": half,
               "scene_axes": "Blender X east, Y north, Z T.P. height; full intersecting source tiles",
               "tile_counts": counts, "road_counts": road_counts, "sources": source_records,
               "attribution": {"official_buildings": "Project PLATEAU / Fukushima City 2025 LOD1",
                               "osm_fallback_buildings_and_roads": "© OpenStreetMap contributors / ODbL 1.0",
                               "terrain_and_road_ground": "© Geospatial Information Authority of Japan DEM5A"},
               "limitations": ["Official LOD1 is untextured, not photorealistic LOD2",
                               "DEM5A is ground elevation, not road deck or building foundation height",
                               "Road curves show only OSM centerlines with known DEM5A ground height",
                               "Bridge, tunnel and unknown-height road segments are omitted from the preview",
                               "Source GLB tiles are complete and may extend beyond the requested 1 km square",
                               "Dataset-specific public redistribution terms remain unverified"]}
    sidecar_path = output.with_suffix(".provenance.json")
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"blend": str(output), "preview": str(preview),
                      "tile_counts": counts, "road_counts": road_counts,
                      "bytes": output.stat().st_size}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", type=pathlib.Path, default=DEFAULT_AREA)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    run(args.area, args.output)
