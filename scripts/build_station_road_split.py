#!/usr/bin/env python3
"""Offline 100 m visual road / sidewalk *candidate* partition for station-east.

Requires Shapely 2.x at build time only. Never changes source GIS files.
PLATEAU tran LOD1 is a road corridor, OSM centreline widths are class estimates.
There is NO legal, surveyed, accessible or collision-ready classification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

try:
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union
except ImportError as exc:
    raise SystemExit("Install build-only dependency: python -m pip install 'shapely>=2,<3'") from exc

ROOT=Path(__file__).resolve().parents[1]
STATION=ROOT/"data/derived/fukushima-station-roads-v02/road_extent.json"
OSM=ROOT/"data/derived/fukushima-citywide-roads-v1/tileset.json"
OUTPUT=ROOT/"data/derived/fukushima-station-roads-v02/road_split_100m.json"
SCHEMA="therabby.geoengine.station-road-split.visual.v0.1"
DRIVING={"motorway","trunk","primary","secondary","tertiary","residential",
         "unclassified","living_street","service","motorway_link","trunk_link",
         "primary_link","secondary_link","tertiary_link"}
EXCLUDED_VALUES={"","no","false","0"}
BBOX=(-50.0,-50.0,50.0,50.0)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def polygon_parts(shape, area_floor=0.025):
    if shape.is_empty:
        return []
    if shape.geom_type=="Polygon":
        return [shape] if shape.area>=area_floor else []
    if hasattr(shape,"geoms"):
        result=[]
        for child in shape.geoms:
            result.extend(polygon_parts(child,area_floor))
        return result
    return []

def lines_from(shape):
    if shape.is_empty:
        return []
    if shape.geom_type=="LineString":
        return [shape] if shape.length>1.5 else []
    if hasattr(shape,"geoms"):
        lines=[]
        for part in shape.geoms:
            lines.extend(lines_from(part))
        return lines
    return []

def points_valid(polygon):
    return isinstance(polygon,list) and len(polygon)>=3 and all(
        isinstance(pt,list) and len(pt)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in pt)
        for pt in polygon
    )

def fix_polygon(points):
    if not points_valid(points):
        raise ValueError("Invalid PLATEAU road coordinate ring")
    poly=Polygon(points)
    if not poly.is_valid:  # do not silently rewrite untrusted official boundaries
        raise ValueError("Invalid PLATEAU polygon topology; inspect input before conversion")
    if poly.area<=0.01:
        raise ValueError("Degenerate PLATEAU road polygon")
    return poly

def ring(coords):
    points=list(coords)
    if len(points)>1 and points[0]==points[-1]:
        points=points[:-1]
    return [[round(float(x),4),round(float(z),4)] for x,z in points]

def serialize(shape):
    return [
        {"outer":ring(poly.exterior.coords),"holes":[ring(hole.coords) for hole in poly.interiors]}
        for poly in sorted(polygon_parts(shape),key=lambda p:(round(p.bounds[0],2),round(p.bounds[1],2),-p.area))
    ]

def intersects(tile_bounds,box_bounds,padding=14):
    a,b,c,d=tile_bounds
    x0,z0,x1,z1=box_bounds
    return a<=x1+padding and c>=x0-padding and b<=z1+padding and d>=z0-padding

def build(station_path=STATION, osm_index_path=OSM, output_path=None):
    station_path=Path(station_path).resolve()
    osm_index_path=Path(osm_index_path).resolve()
    station=json.loads(station_path.read_text(encoding="utf-8"))
    index=json.loads(osm_index_path.read_text(encoding="utf-8"))
    if station.get("schema")!="therabby.geoengine.station-road-corridor.v0.2" or         station.get("status")!="complete" or station.get("projected_crs")!="EPSG:6677" or         station.get("bounds_local_xz_m")!=[-150,-150,150,150]:
        raise ValueError("Unexpected PLATEAU station corridor schema or projected CRS")
    if index.get("schema")!="therabby.geoengine.citywide-road-tiles.v0.1" or         index.get("status")!="complete" or "EPSG:6677" not in index.get("projected_crs",""):
        raise ValueError("Unexpected OSM road tile manifest / EPSG:6677")
    east=station.get("center_east_m");north=station.get("center_north_m")
    if not (isinstance(east,(int,float)) and math.isfinite(east) and
            isinstance(north,(int,float)) and math.isfinite(north)):
        raise ValueError("Unknown station projected center")
    sample=box(*BBOX)
    polys=[]
    for item in station["roads"]:
        if item.get("geometry_quality")!="official-road-extent-not-carriageway":
            raise ValueError("Official road is not a verified corridor")
        poly=fix_polygon(item["polygon"])
        if poly.intersects(sample):
            polys.append(poly.intersection(sample))
    if not polys:
        raise ValueError("No PLATEAU corridor in 100m pilot")
    corridor=unary_union(polys)
    if not corridor.is_valid:
        raise ValueError("Official corridor union has invalid topology")

    source_files=[{"path":station_path.name,"sha256":digest(station_path)},
                  {"path":osm_index_path.name,"sha256":digest(osm_index_path)}]
    segments=[];unique_ids=set();rejected=0;selected_tiles=0
    abs_bounds=[east+BBOX[0],north-BBOX[3],east+BBOX[2],north-BBOX[1]]
    for item in index["tiles"]:
        if not intersects(item["bbox_east_north_m"],abs_bounds):
            continue
        path=(osm_index_path.parent/item["path"]).resolve()
        # Fail closed: ensure the OSM derived file matches the published manifest.
        if digest(path)!=item["sha256"]:
            raise ValueError(f"OSM road tile checksum mismatch: {item['id']}")
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema")!="therabby.geoengine.citywide-road-tile.v0.1" or             data.get("tile_id")!=item["id"] or data.get("projected_crs")!="EPSG:6677":
            raise ValueError(f"Unexpected OSM tile schema: {item['id']}")
        if data.get("tile_origin_east_m") is None or data.get("tile_origin_north_m") is None:
            raise ValueError("Missing OSM tile origin")
        selected_tiles+=1
        source_files.append({"path":item["path"],"sha256":digest(path)})
        for edge in data["edges"]:
            if edge.get("highway") not in DRIVING or                 str(edge.get("bridge_osm_tag","")).lower() not in EXCLUDED_VALUES or                 str(edge.get("tunnel_osm_tag","")).lower() not in EXCLUDED_VALUES:
                rejected+=1;continue
            if str(edge.get("access_osm_tag","")).lower() in {"no","private"}:
                rejected+=1;continue
            width=edge.get("width_m")
            if not isinstance(width,(int,float)) or not math.isfinite(width) or width<2 or width>25 or                 edge.get("width_quality")!="class-estimate":
                rejected+=1;continue
            pts=edge.get("points")
            if not pts or len(pts)!=2 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in pts):
                rejected+=1;continue
            converted=[(data["tile_origin_east_m"]+p[0]-east,
                        north-data["tile_origin_north_m"]+p[1]) for p in pts]
            ln=LineString(converted)
            if ln.length<=0.1 or not ln.intersects(sample.buffer(14)):
                continue
            key=(edge.get("id"),tuple(round(v,3) for p in converted for v in p))
            if key in unique_ids:continue
            unique_ids.add(key)
            segments.append(ln.buffer(width/2,cap_style="flat",join_style="mitre"))
    if not segments:
        raise ValueError("No valid OSM carriageway centreline data near station 100m; refusing an empty guess")
    vehicle_buffer=unary_union(segments)
    carriage=corridor.intersection(vehicle_buffer)
    if carriage.is_empty or carriage.area<1:
        raise ValueError("OSM road corridor and PLATEAU extent do not overlap; verify georeferencing")
    remainder=corridor.difference(carriage)
    # 3m proximity is an arbitrary visual hypothesis, not a sidewalk survey.
    sidewalk=remainder.intersection(carriage.buffer(3.0,join_style="mitre"))
    unclassified=remainder.difference(sidewalk)
    geometry=unary_union([carriage,sidewalk,unclassified])
    loss=corridor.symmetric_difference(geometry).area
    overlap=carriage.intersection(sidewalk).area+carriage.intersection(unclassified).area+sidewalk.intersection(unclassified).area
    if loss>0.005 or overlap>0.005:
        raise ValueError(f"Visual road split lost/overlapped area: {loss:.4f}/{overlap:.4f} m²")
    # Lines shared by road & sidewalk are *candidates* for raised curb faces.
    curb_raw=carriage.boundary.intersection(sidewalk.boundary.buffer(0.002))
    curbs=[ring(line.coords) for line in lines_from(curb_raw)]
    result={
        "schema":SCHEMA,"status":"experimental","projected_crs":"EPSG:6677",
        "center_east_m":east,"center_north_m":north,
        "bounds_local_xz_m":list(BBOX),"height_reference":"station DEM5A visual ground T.P.; never surveyed road deck",
        "geometry_quality":"PLATEAU LOD1 corridor clipped with OSM estimated-width line buffers",
        "source":{"plateau":"Project PLATEAU / Fukushima City 2025","osm":"© OpenStreetMap contributors / ODbL 1.0",
                  "gsi":"© Geospatial Information Authority of Japan","inputs":source_files},
        "layers":{"carriageway_candidate":serialize(carriage),
                  "sidewalk_candidate":serialize(sidewalk),
                  "unclassified_corridor":serialize(unclassified)},
        "curb_candidates":curbs,
        "statistics":{"official_corridor_area_m2":round(corridor.area,3),
                      "carriageway_area_m2":round(carriage.area,3),
                      "sidewalk_candidate_area_m2":round(sidewalk.area,3),
                      "unclassified_area_m2":round(unclassified.area,3),
                      "partition_error_m2":round(loss,6),"overlap_error_m2":round(overlap,6),
                      "osm_segments_selected":len(segments),"osm_edges_excluded":rejected,
                      "osm_tiles_selected":selected_tiles,"curb_segments":len(curbs)},
        "limitations":["Sidewalk_candidate is proximity-to-road remainder; may actually be parking, plaza, shoulder, median or something else.",
                       "Curb is elevated for VISUAL PREVIEW ONLY (0.09m); no verified curb height or accessible pedestrian path.",
                       "Not legal traffic lanes, driving collision surface, TDS assessment, or geographic survey.",
                       "Road bridge/tunnel/deck, crossing and inaccessible access are not classified as verified roads."]
    }
    if output_path is not None:
        path=Path(output_path)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station",type=Path,default=STATION)
    parser.add_argument("--osm-index",type=Path,default=OSM)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    r=build(args.station,args.osm_index,args.output)
    print(json.dumps(r["statistics"],ensure_ascii=False,indent=2))
    print("EXPERIMENTAL ONLY: all carriageway and sidewalk classes are inferred visual candidates")
