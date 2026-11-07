#!/usr/bin/env python3
"""Compare surveyed Fukushima anchors to map geometry and DEM ground.

Input must declare JGD2011 geographic EPSG:6668 and T.P. heights. OSM road
centerlines and PLATEAU building outlines are separate horizontal checks;
DEM5A is compared only with surveyed bare-earth ground, never road deck or
building foundation heights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib

import geoengine
from build_citywide_road_tiles import load_dem
from terrain_grid import sample_dem

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADS = ROOT / "data/derived/fukushima-citywide-roads-v1"
BUILDINGS = ROOT / "data/derived/fukushima-citywide-lod1-v2"
DEM = ROOT / "data/raw/gsi_dem5a_citywide_full/source_manifest.json"


def distance_to_segment(x, y, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length2 = dx*dx+dy*dy
    fraction = max(0, min(1, ((x-a[0])*dx+(y-a[1])*dy)/length2)) if length2 else 0
    return math.hypot(x-(a[0]+fraction*dx), y-(a[1]+fraction*dy))


def validate_input(data):
    if data.get("schema") != "therabby.geoengine.survey-anchors.v0.1" or \
            data.get("horizontal_crs") != "JGD2011 geographic (EPSG:6668)" or \
            data.get("vertical_datum") != "T.P. (Tokyo Peil)":
        raise ValueError("Survey input must explicitly declare EPSG:6668 and T.P.; no silent CRS/datum conversion")
    anchors = data.get("anchors")
    if not isinstance(anchors, list) or len(anchors) < 2:
        raise ValueError("At least two real surveyed anchors are required")
    ids, positions = set(), set()
    for anchor in anchors:
        if not isinstance(anchor, dict) or anchor.get("feature") not in \
                ("osm_road_centerline", "plateau_building_outline"):
            raise ValueError("Anchor feature must be an OSM road centerline or official PLATEAU building outline")
        identifier = anchor.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError("Each surveyed anchor needs a unique nonempty ID")
        ids.add(identifier)
        for name in ("lat_deg", "lon_deg", "surveyed_bare_earth_tp_m",
                     "horizontal_tolerance_m", "vertical_tolerance_m"):
            value = anchor.get(name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{identifier}: missing or nonfinite {name}")
        if not (37 <= anchor["lat_deg"] <= 39 and 139 <= anchor["lon_deg"] <= 142 and
                0 < anchor["horizontal_tolerance_m"] <= 100 and
                0 < anchor["vertical_tolerance_m"] <= 100):
            raise ValueError(f"{identifier}: coordinates or declared tolerances outside supported range")
        position = (anchor["lat_deg"], anchor["lon_deg"])
        if position in positions:
            raise ValueError(f"{identifier}: survey anchors must be distinct points")
        positions.add(position)
        for name in ("survey_method", "survey_date", "survey_source"):
            if not isinstance(anchor.get(name), str) or not anchor[name].strip():
                raise ValueError(f"{identifier}: documented {name} is required")
    return anchors


def load_nearby(directory, manifest, east, north):
    tx, ty = math.floor(east/1000), math.floor(north/1000)
    by_id = {item["id"]: item for item in manifest["tiles"]}
    for x in range(tx-1, tx+2):
        for y in range(ty-1, ty+2):
            item = by_id.get(f"{x}_{y}")
            if item:
                path = directory / item["path"]
                raw = path.read_bytes()
                if len(raw) != item["byte_length"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                    raise ValueError(f"Survey source tile size or SHA-256 mismatch: {path}")
                data = json.loads(raw)
                if data.get("tile_id") != item["id"]:
                    raise ValueError(f"Tile ID mismatch: {path}")
                if "tile_origin_east_m" not in data:
                    data["tile_origin_east_m"] = item["tile_origin_east_m"]
                    data["tile_origin_north_m"] = item["tile_origin_north_m"]
                yield data


def nearest_road(east, north, manifest):
    best = None
    for tile in load_nearby(ROADS, manifest, east, north):
        for edge in tile["edges"]:
            a, b = edge["points"]
            origin_e, origin_n = tile["tile_origin_east_m"], tile["tile_origin_north_m"]
            a = (origin_e+a[0], origin_n-a[1])
            b = (origin_e+b[0], origin_n-b[1])
            distance = distance_to_segment(east, north, a, b)
            if best is None or distance < best["horizontal_error_m"]:
                best = {"horizontal_error_m": round(distance, 3), "feature_id": edge["id"],
                        "source_way_id": edge["source_way_id"], "source": "OpenStreetMap",
                        "road_deck_height_tp_m": None,
                        "road_deck_quality": "unverified; DEM ground must not be used as road deck"}
    return best


def nearest_building(east, north, manifest):
    best = None
    for tile in load_nearby(BUILDINGS, manifest, east, north):
        origin_e, origin_n = tile["tile_origin_east_m"], tile["tile_origin_north_m"]
        for building in tile["buildings"]:
            ring = [(origin_e+p[0], origin_n-p[1]) for p in building["footprint"]]
            if len(ring) < 3:
                continue
            distance = min(distance_to_segment(east, north, a, b)
                           for a, b in zip(ring, ring[1:]+ring[:1]))
            if best is None or distance < best["horizontal_error_m"]:
                best = {"horizontal_error_m": round(distance, 3),
                        "feature_id": building["id"], "source": "Project PLATEAU / Fukushima City 2025 LOD1",
                        "foundation_height_tp_m": None,
                        "foundation_quality": "unverified; DEM ground must not be used as foundation"}
    return best


def run(input_path, output_path):
    input_path, output_path = pathlib.Path(input_path).resolve(), pathlib.Path(output_path).resolve()
    raw = input_path.read_bytes()
    data = json.loads(raw)
    anchors = validate_input(data)
    roads_manifest = geoengine.read_json(ROADS / "tileset.json")
    buildings_manifest = geoengine.read_json(BUILDINGS / "tileset.json")
    if roads_manifest.get("schema") != "therabby.geoengine.citywide-road-tiles.v0.1" or \
            buildings_manifest.get("status") != "complete" or \
            "EPSG:6677" not in buildings_manifest.get("projected_crs", ""):
        raise ValueError("Expected completed EPSG:6677 official building and OSM road tiles")
    dem_images, _ = load_dem(DEM)
    results = []
    for anchor in anchors:
        lat, lon = anchor["lat_deg"], anchor["lon_deg"]
        east, north = geoengine.jprcs_ix(lat, lon)
        feature = nearest_road(east, north, roads_manifest) if anchor["feature"] == "osm_road_centerline" \
            else nearest_building(east, north, buildings_manifest)
        try:
            ground = round(sample_dem(dem_images, lat, lon), 3)
            vertical_error = round(ground-anchor["surveyed_bare_earth_tp_m"], 3)
        except ValueError:
            ground = vertical_error = None
        horizontal_pass = feature is not None and feature["horizontal_error_m"] <= anchor["horizontal_tolerance_m"]
        vertical_pass = vertical_error is not None and abs(vertical_error) <= anchor["vertical_tolerance_m"]
        results.append({"id": anchor["id"], "survey_source": anchor["survey_source"],
                        "survey_method": anchor["survey_method"], "survey_date": anchor["survey_date"],
                        "survey_crs": data["horizontal_crs"], "projected_east_m": round(east, 3),
                        "projected_north_m": round(north, 3), "feature_type": anchor["feature"],
                        "nearest_feature": feature,
                        "surveyed_bare_earth_tp_m": anchor["surveyed_bare_earth_tp_m"],
                        "dem5a_ground_tp_m": ground,
                        "dem_minus_survey_ground_m": vertical_error,
                        "dem_quality": "GSI DEM5A interpolated bare-earth ground; not road deck or building foundation" if ground is not None else "missing",
                        "horizontal_tolerance_m": anchor["horizontal_tolerance_m"],
                        "vertical_tolerance_m": anchor["vertical_tolerance_m"],
                        "horizontal_within_declared_tolerance": horizontal_pass,
                        "ground_within_declared_tolerance": vertical_pass})
    report = {"schema": "therabby.geoengine.survey-anchor-check.v0.1",
              "input_sha256": hashlib.sha256(raw).hexdigest(),
              "anchor_count": len(results), "checks": results,
              "all_within_declared_tolerances": all(item["horizontal_within_declared_tolerance"] and
                                                    item["ground_within_declared_tolerance"] for item in results),
              "scope": "Local surveyed point comparison only; not citywide positional certification",
              "road_deck_and_building_foundation_certified": False}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    geoengine.write_json(output_path, report)
    print(json.dumps({"output": str(output_path), "anchors": len(results),
                      "all_within_declared_tolerances": report["all_within_declared_tolerances"]}, ensure_ascii=True))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    run(args.input, args.output)
