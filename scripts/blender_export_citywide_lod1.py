#!/usr/bin/env python3
"""Export official citywide LOD1 JSON tiles as local-coordinate GLB meshes.

Run with Blender's bundled Python. The source JSON and provenance stay intact;
buildings without a DEM5A ground sample remain absent from the 3D mesh.
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
from mathutils.geometry import tessellate_polygon

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_TILESET = ROOT / "data/derived/fukushima-citywide-lod1-v2/tileset.json"
DEFAULT_OUT = ROOT / "data/derived/fukushima-citywide-lod1-glb"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ring_points(raw):
    points = [(float(x), float(z)) for x, z in raw]
    if len(points) > 1 and math.dist(points[0], points[-1]) < .001:
        points.pop()
    if len(points) < 3 or not all(math.isfinite(v) for point in points for v in point):
        raise ValueError("LOD1 ring has fewer than three finite vertices")
    return points


def signed_area(ring):
    return sum(x * ring[(i + 1) % len(ring)][1] - z * ring[(i + 1) % len(ring)][0]
               for i, (x, z) in enumerate(ring)) / 2


def material(name, color):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    result.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*color, 1)
    result.use_backface_culling = False
    return result


def build_tile_mesh(buildings, tile_id, source_kind="official"):
    if source_kind not in ("official", "osm_fallback"):
        raise ValueError(f"Unsupported building source kind: {source_kind}")
    vertices, faces, face_materials = [], [], []
    exported = skipped = triangles = 0
    roof_area = 0.0
    for building in buildings:
        base = building.get("base_elevation_m")
        if base is None:
            skipped += 1
            continue
        height = float(building["height_m"])
        if not (math.isfinite(base) and math.isfinite(height) and 1 <= height < 500 and
                building.get("vertical_datum") == "T.P. (Tokyo Peil)"):
            raise ValueError(f"{tile_id} {building.get('id')}: invalid height or vertical datum")
        if source_kind == "official" and building.get("lod") != "LOD1":
            raise ValueError(f"{tile_id} {building.get('id')}: official geometry is not LOD1")
        if source_kind == "osm_fallback" and (building.get("source") != "OpenStreetMap" or
                                                building.get("source_license") != "ODbL 1.0" or
                                                not building.get("height_quality")):
            raise ValueError(f"{tile_id} {building.get('id')}: OSM source or estimate quality missing")
        rings = [ring_points(building["footprint"])] + [ring_points(hole) for hole in building.get("holes", [])]
        expected_area = abs(signed_area(rings[0])) - sum(abs(signed_area(ring)) for ring in rings[1:])
        if expected_area <= .01:
            raise ValueError(f"{tile_id} {building.get('id')}: degenerate clipped footprint")
        top = base + height
        roof_loops, top_indices, roof_index_order = [], {}, []
        for ring in rings:
            winding = signed_area(ring)
            if abs(winding) <= .01:
                raise ValueError(f"{tile_id} {building.get('id')}: degenerate ring")
            bottom_indices, ring_top_indices, vectors = [], [], []
            for x, z in ring:
                # Blender is Z-up; glTF export_yup maps (X,Y,Z) to
                # (east, height, south). The JSON footprint is east/south.
                bottom_indices.append(len(vertices)); vertices.append((x, -z, base))
                ring_top_indices.append(len(vertices)); vertices.append((x, -z, top))
                vector = Vector((x, -z, top))
                vectors.append(vector)
                key = (x, z)
                if key in top_indices:
                    raise ValueError(f"{tile_id} {building.get('id')}: duplicate roof vertex")
                top_indices[key] = ring_top_indices[-1]
                roof_index_order.append(ring_top_indices[-1])
            roof_loops.append(vectors)
            for i in range(len(ring)):
                j = (i + 1) % len(ring)
                face = (bottom_indices[i], ring_top_indices[i], ring_top_indices[j], bottom_indices[j])
                faces.append(face if winding > 0 else tuple(reversed(face)))
                face_materials.append(0)
                triangles += 2
        generated_area = 0.0
        for tri in tessellate_polygon(roof_loops):
            # Blender 3.1 returns indices into the flattened input loops; newer
            # versions may return the Vector values instead.
            indices = (tuple(roof_index_order[v] for v in tri) if isinstance(tri[0], int) else
                       tuple(top_indices[(float(v.x), -float(v.y))] for v in tri))
            a, b, c = (vertices[index] for index in indices)
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            generated_area += abs(cross) / 2
            faces.append(indices if cross > 0 else tuple(reversed(indices)))
            face_materials.append(1)
            triangles += 1
        if abs(generated_area - expected_area) > max(.02, expected_area * .01):
            raise ValueError(f"{tile_id} {building.get('id')}: roof triangulation area {generated_area:.3f} != footprint {expected_area:.3f}")
        roof_area += generated_area
        exported += 1
    mesh = bpy.data.meshes.new(f"citywide_{tile_id}_geometry")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    if not mesh.validate(verbose=False, clean_customdata=False):
        pass
    if source_kind == "official":
        mesh.materials.append(material("LOD1 walls / official shape", (.34, .65, .57)))
        mesh.materials.append(material("LOD1 roofs / official shape", (.58, .76, .66)))
    else:
        mesh.materials.append(material("OSM fallback walls / estimated height", (.66, .46, .34)))
        mesh.materials.append(material("OSM fallback roofs / estimated height", (.84, .63, .45)))
    for face, index in zip(mesh.polygons, face_materials):
        face.material_index = index
    obj = bpy.data.objects.new(f"{'PLATEAU_LOD1' if source_kind == 'official' else 'OSM_FALLBACK'}_{tile_id}", mesh)
    bpy.context.collection.objects.link(obj)
    obj["source"] = ("Project PLATEAU / Fukushima City 2025 CityGML LOD1" if source_kind == "official"
                     else "© OpenStreetMap contributors / ODbL 1.0; footprint real, height possibly estimated")
    obj["vertical_datum"] = "T.P. (Tokyo Peil) DEM5A representative ground sample"
    obj["tile_id"] = tile_id
    return obj, {"buildings": exported, "skipped_no_ground_sample": skipped,
                 "triangles": triangles, "roof_area_m2": round(roof_area, 3)}


def run(tileset_path, output_dir, tile_id=None):
    tileset = json.loads(tileset_path.read_text(encoding="utf-8"))
    if (tileset.get("status") != "complete" or "EPSG:6677" not in tileset.get("projected_crs", "") or
            tileset.get("terrain", {}).get("vertical_datum") != "T.P. (Tokyo Peil)"):
        raise ValueError("Expected completed EPSG:6677 citywide tiles with DEM5A T.P. samples")
    selected = [t for t in tileset["tiles"] if tile_id is None or t["id"] == tile_id]
    if not selected:
        raise ValueError(f"Unknown tile ID: {tile_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for number, tile in enumerate(selected, 1):
        source = tileset_path.parent / tile["path"]
        if sha256(source) != tile["sha256"]:
            raise ValueError(f"Source tile SHA-256 mismatch: {tile['id']}")
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("tile_id") != tile["id"] or len(data.get("buildings", [])) != tile["building_count"]:
            raise ValueError(f"Source tile ID or building count mismatch: {tile['id']}")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        obj, stats = build_tile_mesh(data["buildings"], tile["id"])
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
                        "tile_size_m": tile["tile_size_m"], **stats})
        if number == 1 or number % 10 == 0 or number == len(selected):
            print(f"[{number}/{len(selected)}] {tile['id']}: {stats['buildings']} buildings, {glb.stat().st_size:,} bytes", flush=True)
    manifest = {"schema": "therabby.geoengine.citywide-lod1-glb.v0.1",
                "status": "complete" if len(selected) == len(tileset["tiles"]) else "partial",
                "projected_crs": tileset["projected_crs"], "vertical_datum": "T.P. (Tokyo Peil)",
                "axes": "X east, Y up, Z south; tile-local X/Z, absolute T.P. Y",
                "source_tileset": str(tileset_path.relative_to(ROOT)).replace('\\', '/'),
                "source_tileset_sha256": sha256(tileset_path),
                "source_attribution": tileset["attribution"],
                "ground_attribution": tileset["terrain"]["attribution"],
                "visual_quality": "official PLATEAU LOD1 extrusion, untextured; not photorealistic LOD2",
                "tiles": entries,
                "statistics": {"tiles": len(entries),
                               "buildings": sum(e["buildings"] for e in entries),
                               "skipped_no_ground_sample": sum(e["skipped_no_ground_sample"] for e in entries),
                               "triangles": sum(e["triangles"] for e in entries),
                               "bytes": sum(e["byte_length"] for e in entries)}}
    (output_dir / "tileset.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["statistics"], ensure_ascii=False), flush=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tileset", type=pathlib.Path, default=DEFAULT_TILESET)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--tile-id")
    args = parser.parse_args(argv)
    run(args.tileset.resolve(), args.output_dir.resolve(), args.tile_id)


if __name__ == "__main__":
    main()
