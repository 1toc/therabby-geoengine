#!/usr/bin/env python3
"""Verify generated citywide map assets, graph seams and declared gaps."""
from __future__ import annotations

import collections
import hashlib
import json
import math
import pathlib
import sys

from glb_audit import read_glb

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data/derived"
MANIFESTS = {
    "building": DATA / "fukushima-citywide-lod1-glb/tileset.json",
    "osmBuilding": DATA / "fukushima-citywide-osm-buildings-glb/tileset.json",
    "far": DATA / "fukushima-citywide-far-glb/tileset.json",
    "terrain": DATA / "fukushima-citywide-terrain-glb/tileset.json",
    "road": DATA / "fukushima-citywide-roads-v1/tileset.json",
}
SCHEMAS = {
    "building": "therabby.geoengine.citywide-lod1-glb.v0.1",
    "osmBuilding": "therabby.geoengine.citywide-osm-building-glb.v0.1",
    "far": "therabby.geoengine.citywide-far-glb.v0.1",
    "terrain": "therabby.geoengine.citywide-terrain-glb.v0.1",
    "road": "therabby.geoengine.citywide-road-tiles.v0.1",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check_glb_axes(path, kind):
    doc, _ = read_glb(path)
    positions = [doc["accessors"][primitive["attributes"]["POSITION"]]
                 for mesh in doc.get("meshes", []) for primitive in mesh["primitives"]]
    if not positions:
        raise ValueError(f"No GLB POSITION: {path}")
    lower = [min(a["min"][axis] for a in positions) for axis in range(3)]
    upper = [max(a["max"][axis] for a in positions) for axis in range(3)]
    if any(not math.isfinite(v) for v in lower + upper):
        raise ValueError(f"Non-finite GLB position: {path}")
    # Local projected horizontal axes remain within one source tile, allowing
    # crossings/large buildings; Y must be a plausible absolute T.P. height.
    if not (-500 < lower[0] <= upper[0] < 2500 and
            -500 < lower[2] <= upper[2] < 2500 and
            -20 < lower[1] <= upper[1] < 3000):
        raise ValueError(f"Unexpected X-east/Y-height/Z-south GLB bounds ({kind}): {path}: {lower}, {upper}")
    return lower, upper


def check_terrain_seams():
    manifest_path = DATA / "fukushima-citywide-terrain-meshes/tileset.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "therabby.geoengine.citywide-terrain-mesh-inputs.v0.1" or \
            manifest.get("vertical_datum") != "T.P. (Tokyo Peil)":
        raise ValueError("Unexpected terrain mesh source manifest")
    edges = {}
    for item in manifest["tiles"]:
        path = manifest_path.parent / item["path"]
        if digest(path) != item["sha256"]:
            raise ValueError(f"Terrain source hash mismatch: {path}")
        tile = json.loads(path.read_text(encoding="utf-8"))
        if tile.get("tile_id") != item["id"] or tile.get("grid_cells") != 32:
            raise ValueError(f"Terrain mesh input mismatch: {path}")
        values = tile["vertices_x_south_height"]
        if len(values) != 1089:
            raise ValueError(f"Terrain mesh vertex count mismatch: {path}")
        east, north = item["tile_origin_east_m"], item["tile_origin_north_m"]
        def absolute(index):
            x, south, height = values[index]
            return east+x, north-south, height
        edges[item["id"]] = {
            "left": [absolute(row*33) for row in range(33)],
            "right": [absolute(row*33+32) for row in range(33)],
            "top": [absolute(col) for col in range(33)],
            "bottom": [absolute(32*33+col) for col in range(33)]}
    pairs = valid = missing = 0
    for identifier, item in edges.items():
        z, x, y = (int(part) for part in identifier.split("_"))
        for neighbor_id, side, opposite in ((f"{z}_{x+1}_{y}", "right", "left"),
                                            (f"{z}_{x}_{y+1}", "bottom", "top")):
            neighbor = edges.get(neighbor_id)
            if neighbor is None:
                continue
            for a, b in zip(item[side], neighbor[opposite]):
                pairs += 1
                if math.hypot(a[0]-b[0], a[1]-b[1]) > .002:
                    raise ValueError(f"Terrain projected seam gap: {identifier}/{neighbor_id}")
                if a[2] is None and b[2] is None:
                    missing += 1
                elif a[2] is not None and b[2] is not None and abs(a[2]-b[2]) <= .01:
                    valid += 1
                else:
                    raise ValueError(f"Terrain elevation seam mismatch: {identifier}/{neighbor_id}")
    return {"terrain_seam_pairs": pairs, "terrain_seam_valid_elevation_pairs": valid,
            "terrain_seam_missing_pairs": missing}


def run(output=DATA / "fukushima-citywide-release-audit.json"):
    manifests = {}
    for kind, path in MANIFESTS.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMAS[kind] or "EPSG:6677" not in data.get("projected_crs", "") or \
                not isinstance(data.get("tiles"), list):
            raise ValueError(f"Unsupported {kind} manifest")
        if kind != "road" and data.get("vertical_datum") != "T.P. (Tokyo Peil)":
            raise ValueError(f"Unsupported {kind} vertical datum")
        if data.get("status") not in ("complete", "complete_with_gaps", "complete_with_known_limits"):
            raise ValueError(f"Incomplete {kind} manifest")
        manifests[kind] = data
    building, osm_building, far, terrain, road = (manifests[k] for k in ("building", "osmBuilding", "far", "terrain", "road"))
    if {t["id"] for t in building["tiles"]} != {t["id"] for t in far["tiles"]}:
        raise ValueError("Near and far building tile IDs differ")
    if building["statistics"]["buildings"] != far["statistics"]["source_buildings"] or \
            building["statistics"]["skipped_no_ground_sample"] != far["statistics"]["skipped_no_ground_sample"]:
        raise ValueError("Near/far source building totals differ")
    checks = collections.Counter()
    osm_source_path = DATA / "fukushima-citywide-osm-buildings-v1/tileset.json"
    osm_source = json.loads(osm_source_path.read_text(encoding="utf-8"))
    plateau_source_path = ROOT / "data/raw/plateau/fukushima_citywide_2025/source_manifest.json"
    plateau_source = json.loads(plateau_source_path.read_text(encoding="utf-8"))
    official_meshes = {item["mesh_code"] for item in plateau_source["files"]}
    if (osm_building.get("license") != "ODbL 1.0" or
            osm_building.get("source_tileset_sha256") != digest(osm_source_path) or
            osm_building.get("official_coverage_sha256") != digest(plateau_source_path) or
            osm_source.get("schema") != "therabby.geoengine.citywide-osm-building-tiles.v0.1" or
            osm_source.get("source_pbf_sha256") != osm_building.get("source_pbf_sha256") or
            {item["id"] for item in osm_source["tiles"]} != {item["id"] for item in osm_building["tiles"]}):
        raise ValueError("OSM fallback provenance or source/GLB tile set mismatch")
    osm_count = osm_unknown = 0
    seen_osm_ids = set()
    for item in osm_source["tiles"]:
        path = osm_source_path.parent / item["path"]
        if digest(path) != item["sha256"] or path.stat().st_size != item["byte_length"]:
            raise ValueError(f"OSM fallback source hash mismatch: {path}")
        tile = json.loads(path.read_text(encoding="utf-8"))
        if tile.get("schema") != "therabby.geoengine.osm-building-tile.v0.1" or \
                tile.get("tile_id") != item["id"] or len(tile["buildings"]) != item["building_count"]:
            raise ValueError(f"OSM fallback source tile mismatch: {path}")
        for feature in tile["buildings"]:
            osm_count += 1
            if feature["id"] in seen_osm_ids or feature["source_mesh_code"] in official_meshes or \
                    feature["source"] != "OpenStreetMap" or feature["source_license"] != "ODbL 1.0" or \
                    not feature["height_quality"] or feature["collision_ready"] is not False:
                raise ValueError(f"OSM fallback provenance/overlap/ID mismatch: {feature['id']}")
            seen_osm_ids.add(feature["id"])
            if feature["base_elevation_m"] is None:
                osm_unknown += 1
    if osm_count != osm_source["statistics"]["fallback_buildings"] or \
            osm_unknown != osm_building["statistics"]["skipped_no_ground_sample"] or \
            osm_count-osm_unknown != osm_building["statistics"]["buildings"]:
        raise ValueError("OSM fallback source, unknown ground and exported totals differ")
    for kind in ("building", "osmBuilding", "far", "terrain", "road"):
        parent = MANIFESTS[kind].parent
        for item in manifests[kind]["tiles"]:
            path = parent / item.get("glb", item.get("path", ""))
            if not path.is_file() or path.stat().st_size != item["byte_length"] or digest(path) != item["sha256"]:
                raise ValueError(f"Asset missing, size or SHA-256 mismatch: {path}")
            checks[f"{kind}_files"] += 1
            checks[f"{kind}_bytes"] += item["byte_length"]
            if kind != "road":
                check_glb_axes(path, kind)
    nodes = {}
    shared = set()
    search_points = set()
    for item in road["tiles"]:
        tile = json.loads((MANIFESTS["road"].parent / item["path"]).read_text(encoding="utf-8"))
        if tile.get("schema") != "therabby.geoengine.citywide-road-tile.v0.1" or \
                tile.get("tile_id") != item["id"] or len(tile["edges"]) != item["edge_count"]:
            raise ValueError(f"Road tile schema/count mismatch: {item['id']}")
        for edge in tile["edges"]:
            checks["road_edges"] += 1
            if edge.get("width_quality") != "class-estimate" or edge.get("road_deck_height_m") is not None or \
                    edge.get("legal_drivability") is not None:
                raise ValueError(f"Misleading road quality fields: {edge.get('id')}")
            p, q = edge["points"]
            east = tile["tile_origin_east_m"] + (p[0] + q[0]) / 2
            north = tile["tile_origin_north_m"] - (p[1] + q[1]) / 2
            if edge.get("name"):
                search_points.add((edge["name"], round(east, 2), round(north, 2)))
            for identifier, point, height in ((edge["from_node"], p, edge["ground_height_from_tp_m"]),
                                              (edge["to_node"], q, edge["ground_height_to_tp_m"])):
                absolute = (round(tile["tile_origin_east_m"]+point[0], 3),
                            round(tile["tile_origin_north_m"]-point[1], 3), height)
                if identifier in nodes:
                    previous = nodes[identifier]
                    if previous[:2] != absolute[:2] or previous[2] != absolute[2]:
                        raise ValueError(f"Road graph seam mismatch: {identifier}")
                    if previous[3] != item["id"]:
                        shared.add(identifier)
                else:
                    nodes[identifier] = (*absolute, item["id"])
    if len(nodes) != road["statistics"]["unique_nodes"] or \
            checks["road_edges"] != road["statistics"]["output_edges"] or not shared:
        raise ValueError("Road graph count/seam mismatch")
    search_path = MANIFESTS["road"].parent / "search_index.json"
    search = json.loads(search_path.read_text(encoding="utf-8"))
    if search.get("schema") != "therabby.geoengine.citywide-search.v0.1" or \
            search.get("source_manifest_sha256") != digest(MANIFESTS["road"]):
        raise ValueError("Search index source mismatch")
    for entry in search["entries"]:
        if (entry["name"], entry["east_m"], entry["north_m"]) not in search_points:
            raise ValueError(f"Search representative not on named OSM segment: {entry['name']}")
    checks.update(check_terrain_seams())
    report = {"schema": "therabby.geoengine.citywide-release-audit.v0.1",
              "asset_integrity": "passed", "projected_crs": "EPSG:6677",
              "vertical_datum_for_buildings_and_ground": "T.P. (Tokyo Peil)",
              "verified": dict(checks), "road_unique_nodes": len(nodes),
              "road_shared_seam_nodes": len(shared), "road_search_names": len(search["entries"]),
              "known_gaps": {"building_ground_unknown": building["statistics"]["skipped_no_ground_sample"],
                             "osm_fallback_buildings": osm_count,
                             "osm_fallback_ground_unknown": osm_unknown,
                             "official_building_mesh_coverage": "partial municipality: 212 source meshes; Fukushima City reports 174.6 km² LOD1 of 229 km² planned urban area",
                             "terrain_missing_vertices": terrain["statistics"]["missing_vertices"],
                             "terrain_unpublished_source_tiles": terrain["statistics"]["unpublished_source_tiles"],
                             "road_ground_unknown_nodes": road["statistics"]["ground_unknown_nodes"]},
              "not_verified": ["I-RIHA101 10-minute 1280x720 performance",
                               "two surveyed georeferencing anchors",
                               "dataset-specific PLATEAU redistribution terms",
                               "actual road deck heights and legal drivability"],
              "v1_0_acceptance_complete": False}
    pathlib.Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return report


if __name__ == "__main__":
    run()
