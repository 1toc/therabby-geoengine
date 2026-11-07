#!/usr/bin/env python3
"""Extract real OSM building footprints outside official PLATEAU source meshes.

Only closed building-tagged ways are supported. Heights without a metric OSM
tag are explicitly estimated. Unknown DEM heights stay null. This is a
quality-labeled fallback, not a claim of official LOD1 coverage.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
import re

import osmium
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union
from shapely.prepared import prep

import geoengine
from build_citywide_road_tiles import load_dem, sha256
from terrain_grid import sample_dem

ROOT = pathlib.Path(__file__).resolve().parents[1]
PBF = ROOT / "data/raw/tohoku-latest.osm.pbf"
PLATEAU = ROOT / "data/raw/plateau/fukushima_citywide_2025/source_manifest.json"
ROAD_SOURCE = ROOT / "data/derived/fukushima-road-source-snapshot/index.json"
BOUNDARY = ROOT / "modules/city-boundary/data/fukushima_city_boundary_full.geojson"
DEM = ROOT / "data/raw/gsi_dem5a_citywide_full/source_manifest.json"
OUT = ROOT / "data/derived/fukushima-citywide-osm-buildings-v1"
METRIC_HEIGHT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:m|metres?)?\s*$", re.I)


def mesh_code(lat, lon):
    if not (20 <= lat <= 50 and 120 <= lon <= 155):
        raise ValueError("OSM coordinate is outside supported Japanese range")
    lat_mesh = lat * 1.5
    a, b = math.floor(lat_mesh), math.floor(lon)
    c, d = (lat_mesh-a)*8, (lon-b)*8
    e, f = math.floor(c), math.floor(d)
    g, h = min(9, math.floor((c-e)*10)), min(9, math.floor((d-f)*10))
    return f"{a:02d}{b-100:02d}{e}{f}{g}{h}"


def height_from_tags(tags):
    raw = tags.get("height", "")
    match = METRIC_HEIGHT.fullmatch(raw)
    if match:
        height = float(match.group(1))
        if 1 <= height < 500:
            return round(height, 2), "OSM metric height tag"
    levels = tags.get("building:levels", "")
    try:
        count = float(levels)
    except ValueError:
        count = 0
    if 1 <= count <= 100:
        return round(count*3, 2), "estimated from OSM building:levels × 3 m"
    return 6.0, "class estimate: no usable OSM height tag"


def polygon_parts(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type in ("MultiPolygon", "GeometryCollection"):
        for part in geometry.geoms:
            yield from polygon_parts(part)


def build(pbf=PBF, plateau_manifest=PLATEAU, road_source=ROAD_SOURCE,
          boundary=BOUNDARY, dem_manifest=DEM, output_dir=OUT):
    pbf, plateau_manifest, road_source, boundary, output_dir = map(pathlib.Path,
        (pbf, plateau_manifest, road_source, boundary, output_dir))
    source = geoengine.read_json(plateau_manifest)
    roads = geoengine.read_json(road_source)
    if source.get("status") != "complete" or source.get("municipality_code") != "07201" or \
            roads.get("boundary_quality") != "official_2026" or \
            sha256(pbf) != roads["source_metadata"]["sha256"]:
        raise ValueError("PLATEAU coverage, official boundary or OSM PBF hash mismatch")
    official = {item["mesh_code"] for item in source["files"]}
    boundary_data = geoengine.read_json(boundary)
    city = unary_union([shape(item["geometry"]) for item in boundary_data["features"]])
    if not city.is_valid:
        raise ValueError("Official Fukushima municipality boundary invalid")
    city_prepared = prep(city)
    min_lon, min_lat, max_lon, max_lat = city.bounds
    dem_images, dem_path = load_dem(dem_manifest)
    tiles = collections.defaultdict(list)
    counts = collections.Counter()

    class Extractor(osmium.SimpleHandler):
        def way(self, way):
            tags = dict(way.tags)
            if "building" not in tags or tags["building"] == "no":
                return
            counts["building_tagged_ways"] += 1
            if len(way.nodes) < 4 or way.nodes[0].ref != way.nodes[-1].ref:
                counts["unsupported_open_or_short"] += 1
                return
            if any(not node.location.valid() for node in way.nodes):
                counts["missing_osm_node_location"] += 1
                return
            coords = [(node.lon, node.lat) for node in way.nodes]
            if max(lon for lon, _ in coords) < min_lon or min(lon for lon, _ in coords) > max_lon or \
                    max(lat for _, lat in coords) < min_lat or min(lat for _, lat in coords) > max_lat:
                return
            polygon = Polygon(coords)
            if polygon.is_empty or not polygon.is_valid or polygon.area == 0:
                counts["invalid_osm_polygon"] += 1
                return
            if not city_prepared.intersects(polygon):
                return
            clipped = polygon.intersection(city)
            height, quality = height_from_tags(tags)
            for part_index, part in enumerate(polygon_parts(clipped)):
                if part.area < 1e-11:
                    continue
                center = part.representative_point()
                code = mesh_code(center.y, center.x)
                if code in official:
                    counts["inside_official_source_mesh"] += 1
                    continue
                if len(part.interiors):
                    counts["unsupported_interior_ring"] += 1
                    continue
                points = [geoengine.jprcs_ix(lat, lon) for lon, lat in part.exterior.coords]
                projected = Polygon(points)
                if not projected.is_valid or projected.area < 1:
                    counts["invalid_projected_polygon"] += 1
                    continue
                representative = projected.representative_point()
                tx, ty = math.floor(representative.x/1000), math.floor(representative.y/1000)
                try:
                    ground = round(sample_dem(dem_images, center.y, center.x), 2)
                except ValueError:
                    ground = None
                record = {"id": f"osm-building-way-{way.id}:{part_index}",
                          "source_way_id": f"osm-way-{way.id}", "source_mesh_code": code,
                          "footprint": [[round(east-tx*1000, 3), round((ty+1)*1000-north, 3)]
                                        for east, north in points],
                          "height_m": height, "height_quality": quality,
                          "base_elevation_m": ground,
                          "ground_height_quality": "GSI DEM5A representative ground sample; not foundation height" if ground is not None else "unknown: DEM5A unavailable or no-data",
                          "vertical_datum": "T.P. (Tokyo Peil)" if ground is not None else None,
                          "source": "OpenStreetMap", "source_license": "ODbL 1.0",
                          "visual_quality": "OSM footprint; untextured estimated extrusion, not official PLATEAU LOD1",
                          "collision_ready": False}
                tiles[(tx, ty)].append(record)
                counts["fallback_buildings"] += 1
                counts["dem_ground_known" if ground is not None else "dem_ground_unknown"] += 1
                counts["height_"+quality] += 1

    print("Reading existing Tohoku PBF for OSM building footprints…", flush=True)
    Extractor().apply_file(str(pbf), locations=True, idx="flex_mem")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tiles").mkdir(exist_ok=True)
    records = []
    for (tx, ty), buildings in sorted(tiles.items()):
        buildings.sort(key=lambda item: item["id"])
        identifier = f"{tx}_{ty}"
        path = output_dir / "tiles" / f"{identifier}.json"
        path.write_text(json.dumps({"schema": "therabby.geoengine.osm-building-tile.v0.1",
                                    "tile_id": identifier, "projected_crs": "EPSG:6677",
                                    "tile_origin_east_m": tx*1000,
                                    "tile_origin_north_m": (ty+1)*1000,
                                    "buildings": buildings}, ensure_ascii=False, separators=(",", ":"))+"\n",
                        encoding="utf-8")
        records.append({"id": identifier, "path": f"tiles/{identifier}.json",
                        "tile_origin_east_m": tx*1000, "tile_origin_north_m": (ty+1)*1000,
                        "building_count": len(buildings), "byte_length": path.stat().st_size,
                        "sha256": sha256(path)})
    manifest = {"schema": "therabby.geoengine.citywide-osm-building-tiles.v0.1",
                "status": "complete_with_known_limits", "projected_crs": "JGD2011 / Japan Plane Rectangular CS IX (EPSG:6677)",
                "ground_vertical_datum": "T.P. (Tokyo Peil)", "tile_size_m": 1000,
                "source_pbf": str(pbf.resolve().relative_to(ROOT)).replace('\\', '/'),
                "source_pbf_sha256": sha256(pbf),
                "source_snapshot_utc": roads["source_metadata"]["snapshot_timestamp_utc"],
                "official_coverage_manifest": str(plateau_manifest.resolve().relative_to(ROOT)).replace('\\', '/'),
                "official_coverage_sha256": sha256(plateau_manifest),
                "official_mesh_exclusion": "OSM building representative point in any of the 212 PLATEAU source mesh codes is excluded; source meshes are not polygon-perfect coverage",
                "boundary_source": str(boundary.resolve().relative_to(ROOT)).replace('\\', '/'),
                "boundary_sha256": sha256(boundary),
                "dem_source_manifest": str(dem_path.relative_to(ROOT)).replace('\\', '/'),
                "dem_source_manifest_sha256": sha256(dem_path),
                "attribution": "© OpenStreetMap contributors", "license": "ODbL 1.0",
                "quality": "real OSM way footprints; height and appearance may be estimated; not PLATEAU LOD1",
                "limitations": ["closed building-tagged OSM ways only", "relation-only multipolygons unsupported",
                                "source mesh exclusion is coarse", "height may be class-estimated",
                                "missing DEM ground stays null"],
                "statistics": {**counts, "tiles": len(records)}, "tiles": records}
    geoengine.write_json(output_dir / "tileset.json", manifest)
    print(json.dumps(manifest["statistics"], ensure_ascii=False), flush=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=pathlib.Path, default=PBF)
    parser.add_argument("--plateau-manifest", type=pathlib.Path, default=PLATEAU)
    parser.add_argument("--road-source", type=pathlib.Path, default=ROAD_SOURCE)
    parser.add_argument("--boundary", type=pathlib.Path, default=BOUNDARY)
    parser.add_argument("--dem-manifest", type=pathlib.Path, default=DEM)
    parser.add_argument("--output-dir", type=pathlib.Path, default=OUT)
    args = parser.parse_args()
    build(args.pbf, args.plateau_manifest, args.road_source, args.boundary, args.dem_manifest, args.output_dir)
