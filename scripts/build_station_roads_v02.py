#!/usr/bin/env python3
"""Package the official station road corridor and DEM for the static viewer.

The PLATEAU tran zero coordinate is a placeholder.  Only GSI DEM5A is used
for visual draping; neither source establishes a surveyed carriageway height.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from geoengine import jprcs_ix, load_area, write_json
from road_tiles import clip_polygon_rect

ROOT = Path(__file__).resolve().parents[1]
ROAD_SOURCE = ROOT / "dist/real/fukushima-east-1km/plateau_road_extent.json"
DEM_SOURCE = ROOT / "dist/real/fukushima-east-1km/terrain_grid_5m.json"
AREA_SOURCE = ROOT / "config/fukushima_station_east_1km.json"
OUTPUT = ROOT / "data/derived/fukushima-station-roads-v02/road_extent.json"


def build(roads_source=ROAD_SOURCE, dem_source=DEM_SOURCE, area_source=AREA_SOURCE):
    area = load_area(area_source)
    roads = json.loads(Path(roads_source).read_text(encoding="utf-8"))
    dem = json.loads(Path(dem_source).read_text(encoding="utf-8"))
    if area["projection"] != "JGD2011_JPRCS_IX_GRS80" or area["half_size_m"] != 500:
        raise ValueError("Station source must use JGD2011 plane rectangular IX, 1 km bounds")
    if roads.get("schema") != "therabby.geoengine.plateau-road-extent.v0.1" or \
            roads.get("area_id") != area["id"] or roads.get("bounds") != [-500, -500, 500, 500] or \
            roads.get("coordinate_system", {}).get("vertical") != "not-provided; source zero placeholder":
        raise ValueError("Unsupported PLATEAU road schema, coordinates, or vertical status")
    if dem.get("schema") != "therabby.geoengine.terrain-grid.v0.1" or \
            dem.get("area_id") != area["id"] or dem.get("bounds") != [-500, -500, 500, 500] or \
            dem.get("step_m") != 5 or not dem.get("vertical_datum", "").startswith("T.P."):
        raise ValueError("Unsupported DEM5A grid or vertical datum")
    if len(dem["heights_relative_m"]) != 201 or \
            any(len(row) != 201 for row in dem["heights_relative_m"]):
        raise ValueError("DEM5A grid must be 201 x 201")
    bounds = [-150, -150, 150, 150]
    clipped = []
    for road in roads["roads"]:
        if road.get("geometry_quality") != "official-road-extent-not-carriageway" or \
                road.get("height_m") is not None:
            raise ValueError(f"Unsupported official road quality: {road.get('id')}")
        polygon = clip_polygon_rect(road["polygon"], bounds)
        if polygon:
            clipped.append({"id": road["id"], "polygon": polygon,
                            "source_file": road["source_file"],
                            "geometry_quality": road["geometry_quality"],
                            "surface_height_quality": "GSI DEM5A visual drape, not roadway survey"})
    if not clipped:
        raise ValueError("No official road polygons cover the station area")
    east, north = jprcs_ix(area["center_lat"], area["center_lon"])
    return {
        "schema": "therabby.geoengine.station-road-corridor.v0.2",
        "status": "complete", "projected_crs": "EPSG:6677",
        "center_east_m": east, "center_north_m": north,
        "bounds_local_xz_m": bounds, "road_count": len(clipped), "roads": clipped,
        "terrain": {"bounds_local_xz_m": bounds, "step_m": 5,
                    "height_origin_tp_m": dem["height_origin_tp_m"],
                    "heights_relative_m": [row[70:131] for row in dem["heights_relative_m"][70:131]],
                    "vertical_datum": "T.P. (Tokyo Peil)"},
        "sources": [{"path": str(Path(path).relative_to(ROOT)).replace("\\", "/"),
                     "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                    for path in (roads_source, dem_source, area_source)],
        "attribution": ["Project PLATEAU / Fukushima City 2025", "© Geospatial Information Authority of Japan"],
        "limitations": ["PLATEAU LOD1 road corridor does not separate carriageway and sidewalk",
                        "Visual height is GSI DEM5A ground, not surveyed road deck",
                        "OSM width and centerline are estimates, not collision-ready"],
    }


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = build()
    write_json(OUTPUT, result)
    print(f"{result['road_count']} official corridor polygons -> {OUTPUT}")
