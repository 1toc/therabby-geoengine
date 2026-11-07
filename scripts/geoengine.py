#!/usr/bin/env python3
"""Therabby GeoEngine: OSM + PLATEAU LOD1/LOD2 to local-meter scene JSON.

Only Python standard library is required on the development machine.
No Python is required on client PCs. This module intentionally refuses
unsupported coordinate formats rather than silently misaligning buildings.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import math
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
METERS_PER_DEG_LAT = 111_320.0
NS = {"bldg": "http://www.opengis.net/citygml/building/2.0", "gml": "http://www.opengis.net/gml",
      "app": "http://www.opengis.net/citygml/appearance/2.0"}


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_area(path):
    area = read_json(path)
    for key in ("id", "center_lat", "center_lon", "half_size_m"):
        if key not in area:
            raise ValueError(f"area config missing: {key}")
    if not (20 <= area["center_lat"] <= 50 and 120 <= area["center_lon"] <= 155):
        raise ValueError("center coordinates are outside Japan; check latitude/longitude")
    if not (10 <= area["half_size_m"] <= 2000):
        raise ValueError("half_size_m must be between 10 and 2000")
    if area.get("projection", "local_equirectangular") not in ("local_equirectangular", "JGD2011_JPRCS_IX_GRS80"):
        raise ValueError(f"Unsupported projection: {area['projection']}")
    return area


def jprcs_ix(lat, lon):
    """GRS80 Transverse Mercator, Japan Plane Rectangular CS IX (metres)."""
    a, inv_f, scale = 6378137.0, 298.257222101, .9999
    e2 = 2 / inv_f - 1 / inv_f**2
    ep2 = e2 / (1 - e2)
    phi, lam = math.radians(lat), math.radians(lon)
    lam0, phi0 = math.radians(139 + 50 / 60), math.radians(36)
    def meridional(p):
        return a * ((1-e2/4-3*e2**2/64-5*e2**3/256)*p
                    -(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*p)
                    +(15*e2**2/256+45*e2**3/1024)*math.sin(4*p)
                    -(35*e2**3/3072)*math.sin(6*p))
    s, c = math.sin(phi), math.cos(phi)
    n = a / math.sqrt(1-e2*s*s)
    t, cc, aa = math.tan(phi)**2, ep2*c*c, (lam-lam0)*c
    east = scale*n*(aa+(1-t+cc)*aa**3/6+(5-18*t+t*t+72*cc-58*ep2)*aa**5/120)
    north = scale*(meridional(phi)-meridional(phi0)+n*math.tan(phi)*
                   (aa**2/2+(5-t+9*cc+4*cc*cc)*aa**4/24+
                    (61-58*t+t*t+600*cc-330*ep2)*aa**6/720))
    return east, north


def xy_of(lat, lon, area):
    """Three.js coordinates: +X East, +Z South, +Y up."""
    if area.get("projection") == "JGD2011_JPRCS_IX_GRS80":
        east, north = jprcs_ix(lat, lon)
        e0, n0 = jprcs_ix(area["center_lat"], area["center_lon"])
        return [round(east-e0, 3), round(n0-north, 3)]
    x = (lon - area["center_lon"]) * METERS_PER_DEG_LAT * math.cos(math.radians(area["center_lat"]))
    z = -(lat - area["center_lat"]) * METERS_PER_DEG_LAT
    return [round(x, 3), round(z, 3)]


def bbox_of(area, margin=20):
    half = area["half_size_m"] + margin
    dlat = half / METERS_PER_DEG_LAT
    dlon = half / (METERS_PER_DEG_LAT * math.cos(math.radians(area["center_lat"])))
    return (area["center_lat"] - dlat, area["center_lon"] - dlon,
            area["center_lat"] + dlat, area["center_lon"] + dlon)


def overpass_query(area):
    s, w, n, e = bbox_of(area, margin=35)
    return ("[out:json][timeout:90];("
            f'way["highway"]({s:.8f},{w:.8f},{n:.8f},{e:.8f});'
            f'way["building"]({s:.8f},{w:.8f},{n:.8f},{e:.8f});'
            ");out geom;")


def osm_fetch(area, output, endpoint, timeout):
    q = overpass_query(area)
    data = urllib.parse.urlencode({"data": q}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"User-Agent": "TherabbyGeoEngine-M1/0.1 (non-commercial development)", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Overpass HTTP {resp.status}")
            raw = resp.read(25_000_001)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"OSM data fetch failed: {exc}; use --osm with a saved Overpass JSON") from exc
    if len(raw) > 25_000_000:
        raise ValueError("Unexpectedly large Overpass response; reduce area")
    parsed = json.loads(raw)
    if "elements" not in parsed:
        raise ValueError("Overpass did not return elements (may be server overload)")
    write_json(output, parsed)
    print(f"Saved {len(parsed['elements'])} OSM elements: {output}")


def osm_fetch_api(area, output, timeout):
    """OSM 0.6 map API fallback when Overpass is unavailable."""
    south, west, north, east = bbox_of(area, margin=35)
    url = ("https://api.openstreetmap.org/api/0.6/map?bbox="
           f"{west:.8f},{south:.8f},{east:.8f},{north:.8f}")
    request = urllib.request.Request(url, headers={"User-Agent": "TherabbyGeoEngine-M1/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(25_000_001)
    if len(raw) > 25_000_000:
        raise ValueError("OSM API response exceeds 25 MB; reduce area")
    root = ET.fromstring(raw)
    nodes = {node.attrib["id"]: {"lat": float(node.attrib["lat"]),
                                  "lon": float(node.attrib["lon"])}
             for node in root.findall("node")}
    elements = []
    for way in root.findall("way"):
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
        if "highway" not in tags and "building" not in tags:
            continue
        points = [nodes[ref.attrib["ref"]] for ref in way.findall("nd") if ref.attrib["ref"] in nodes]
        if len(points) >= 2:
            elements.append({"type": "way", "id": int(way.attrib["id"]),
                             "geometry": points, "tags": tags})
    write_json(output, {"version": 0.6, "generator": "Therabby OSM API extractor",
                        "source_url": url, "elements": elements})
    print(f"Saved {len(elements)} OSM ways from OSM map API: {output}")


def segment_clip(a, b, limit):
    """Liang-Barsky line clipping to square [-limit, limit]."""
    x0, z0 = a
    x1, z1 = b
    dx, dz = x1 - x0, z1 - z0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 + limit), (dx, limit - x0), (-dz, z0 + limit), (dz, limit - z0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return [[round(x0 + t0*dx, 3), round(z0 + t0*dz, 3)],
            [round(x0 + t1*dx, 3), round(z0 + t1*dz, 3)]]


def dedupe_points(points):
    out = []
    for p in points:
        if not out or math.dist(p, out[-1]) > .05:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) < .05:
        out.pop()
    return out


def polygon_area(pts):
    return abs(sum(x1*z2-x2*z1 for (x1,z1),(x2,z2) in zip(pts,pts[1:]+pts[:1]))) / 2 if len(pts)>=3 else 0


def plateau_index_url(area, base="https://api.plateauview.mlit.go.jp"):
    s, w, n, e = bbox_of(area, margin=0)
    # Official PLATEAU CityGML file-search API: /datacatalog/citygml/r:west,south,east,north
    return base.rstrip("/") + f"/datacatalog/citygml/r:{w:.7f},{s:.7f},{e:.7f},{n:.7f}?types=bldg"


def official_bldg_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and parsed.netloc == "assets.cms.plateau.reearth.io"
            and re.search(r"/\d{8}_bldg_\d+_op\.gml$", parsed.path, re.I) is not None)


def select_plateau_files(index, area):
    """Select only LOD1 building files for the configured municipality and year."""
    city_code, year = area.get("plateau_city_code"), area.get("plateau_year")
    if not city_code or not year:
        raise ValueError("Area config needs plateau_city_code and plateau_year for PLATEAU retrieval")
    cities = index.get("cities")
    if not isinstance(cities, list):
        raise ValueError("Unexpected PLATEAU catalog schema: missing cities[]")
    selected = [city for city in cities if city.get("cityCode") == city_code and city.get("year") == year]
    if len(selected) != 1:
        raise ValueError(f"Expected one PLATEAU city {city_code} year {year}; found {len(selected)}")
    files = selected[0].get("files", {}).get("bldg", [])
    if not isinstance(files, list):
        raise ValueError("Unexpected PLATEAU catalog schema: files.bldg must be a list")
    result = []
    for item in files:
        if not isinstance(item, dict) or not official_bldg_url(item.get("url", "")):
            raise ValueError("PLATEAU catalog contains an invalid building GML URL")
        if not isinstance(item.get("lod1"), int) or item["lod1"] <= 0:
            continue
        size = item.get("fileSize")
        if not isinstance(size, int) or not 0 < size <= 150_000_000:
            raise ValueError("PLATEAU building GML size is missing or exceeds 150 MB")
        result.append({"url": item["url"], "file_size": size, "mesh_code": item.get("code"),
                       "lod1_features": item["lod1"], "dataset_year": year, "city_code": city_code})
    if not result:
        raise ValueError("No LOD1 building GML files found for this city, year and area")
    return result


def discover_plateau_gml_links(obj):
    """Compatibility helper for inspecting a saved catalog without area selection."""
    found = set()
    def walk(value):
        if isinstance(value, dict):
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
        elif isinstance(value, str) and official_bldg_url(value):
            found.add(value)
    walk(obj)
    return sorted(found)


def fetch_plateau(area, out_dir, index_file=None, dry_run=False, limit=12):
    out_dir=pathlib.Path(out_dir)
    url=plateau_index_url(area)
    if index_file:
        index=read_json(index_file)
    else:
        req=urllib.request.Request(url,headers={"User-Agent":"TherabbyGeoEngine-M1/0.1","Accept":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=90) as response:
                raw=response.read(15_000_001)
            if len(raw)>15_000_000:raise RuntimeError("Unexpectedly large PLATEAU index")
            index=json.loads(raw)
        except (urllib.error.URLError,TimeoutError) as exc:
            raise RuntimeError(f"PLATEAU API error: {exc}") from exc
    out_dir.mkdir(parents=True,exist_ok=True)
    write_json(out_dir/"plateau_catalog_response.json",index)
    files=select_plateau_files(index,area)
    write_json(out_dir/"plateau_file_list.json",{"endpoint":url,"files":files})
    print(f"PLATEAU index: {len(files)} LOD1 building GML file(s), {sum(f['file_size'] for f in files):,} bytes total")
    if len(files)>limit:
        raise RuntimeError(f"Found {len(files)} building files, exceeds --limit={limit}. Reduce area or check index before downloading")
    if sum(f["file_size"] for f in files)>1_000_000_000:
        raise RuntimeError("Building files exceed 1 GB total; reduce area and review before downloading")
    if dry_run:
        for item in files: print("DRY RUN",item["file_size"],item["url"])
        return
    for item in files:
        link=item["url"]
        filename=pathlib.Path(urllib.parse.urlsplit(link).path).name
        dest=out_dir/filename
        if dest.is_file():
            print("SKIP existing",dest)
            continue
        req=urllib.request.Request(link,headers={"User-Agent":"TherabbyGeoEngine-M1/0.1"})
        try:
            with urllib.request.urlopen(req,timeout=120) as response:
                with dest.open("wb") as output:
                    total=0
                    while True:
                        chunk=response.read(256*1024)
                        if not chunk:break
                        total+=len(chunk)
                        if total>150_000_000:
                            raise RuntimeError("File >150 MB; aborting to avoid unbounded download")
                        output.write(chunk)
        except Exception:
            if dest.exists():dest.unlink()
            raise
        print("Downloaded",dest, f"{total:,} bytes")


def osm_height(tags):
    value = str(tags.get("height", "")).strip().lower().replace("meters", "m")
    try:
        if value.endswith("m"):
            value = value[:-1].strip()
        h = float(value)
        if math.isfinite(h) and 1 <= h <= 300:
            return round(h, 2), "measured-osm-tag"
    except ValueError:
        pass
    try:
        levels = float(tags.get("building:levels", ""))
        if math.isfinite(levels) and 1 <= levels <= 100:
            return round(levels * 3.1, 2), "estimated-from-osm-levels"
    except ValueError:
        pass
    return 9.0, "fallback-placeholder-not-measured"


HIGHWAY_WIDTH = {"motorway": 12, "trunk": 11, "primary": 10, "secondary": 9,
                 "tertiary": 8, "residential": 6, "unclassified": 6, "service": 4,
                 "living_street": 4, "pedestrian": 4, "footway": 2, "path": 2, "cycleway": 2}


def parse_osm(osm, area):
    if not isinstance(osm.get("elements"), list):
        raise ValueError("OSM JSON must contain elements[]")
    roads, buildings = [], []
    limit = area["half_size_m"] + 10
    for element in osm["elements"]:
        if element.get("type") != "way" or not element.get("geometry"):
            continue
        tags = element.get("tags", {})
        points = [xy_of(p["lat"], p["lon"], area) for p in element["geometry"]]
        if "highway" in tags:
            cropped = []
            for a, b in zip(points, points[1:]):
                pair = segment_clip(a, b, limit)
                if pair and math.dist(*pair) > .2:
                    if not cropped or math.dist(cropped[-1][-1],pair[0]) > .1:
                        cropped.append(pair)
                    else:
                        cropped[-1].append(pair[1])
            width = HIGHWAY_WIDTH.get(tags["highway"], 5)
            # Width tag is advisory, not surveyed lane geometry.
            for j, segment in enumerate(cropped):
                context={key:tags[key] for key in
                         ('bridge','tunnel','layer','lanes','surface','access','motor_vehicle')
                         if key in tags}
                roads.append({"id": f"osm-way-{element['id']}-{j}", "points": segment,
                              "width_m": width, "width_quality": "class-estimate",
                              "highway": tags["highway"], "oneway": tags.get("oneway", "no"),
                              "name": tags.get("name", ""), **context})
        if "building" in tags:
            pts = dedupe_points(points)
            if len(pts) < 3 or polygon_area(pts) < 2:
                continue
            if not (min(p[0] for p in pts) < limit and max(p[0] for p in pts) > -limit and
                    min(p[1] for p in pts) < limit and max(p[1] for p in pts) > -limit):
                continue
            h, quality = osm_height(tags)
            buildings.append({"id": f"osm-way-{element['id']}", "footprint": pts,
                              "height_m": h, "base_elevation_m": 0, "height_quality": quality,
                              "source": "OpenStreetMap", "lod": "approx"})
    return roads, buildings


def extract_coords_from_poslist(raw, dimension=3, srs_name=None):
    supported = (r"urn:ogc:def:crs:EPSG::(?:6697|4979)|"
                 r"https?://www\.opengis\.net/def/crs/EPSG/0/(?:6697|4979)|"
                 r"EPSG:(?:6697|4979)")
    if not isinstance(srs_name, str) or not re.fullmatch(supported, srs_name, re.I):
        raise ValueError(f"Unsupported or missing PLATEAU CRS: {srs_name!r}; expected EPSG:6697 or EPSG:4979")
    values = [float(v) for v in raw.split()]
    if dimension != 3 or len(values) % 3:
        raise ValueError("PLATEAU LOD1 requires 3D coordinate triples")
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Non-finite PLATEAU coordinate")
    triplets = [values[i:i+dimension] for i in range(0,len(values),dimension)]
    coords = []
    for vals in triplets:
        p, q = vals[0], vals[1]
        # Both supported EPSG definitions use latitude, longitude, height axis order.
        if not (20 <= p <= 50 and 120 <= q <= 155):
            raise ValueError(f"PLATEAU coordinate pair {p},{q} is not lat/lon in Japan for {srs_name}")
        lat, lon = p, q
        coords.append((lat, lon, vals[2] if dimension == 3 else 0.0))
    return coords


def local_of_coords(coords, area):
    return [xy_of(lat,lon,area) for lat,lon,_ in coords]


def appearance_targets(member):
    """Index PLATEAU's polygon-to-JPEG UV references in an appearance member."""
    targets = {}
    for texture in member.findall(".//app:ParameterizedTexture", NS):
        uri = texture.findtext("app:imageURI", namespaces=NS)
        if not uri:
            continue
        for target in texture.findall("app:target", NS):
            polygon_id = target.attrib.get("uri", "").removeprefix("#")
            if not polygon_id or polygon_id in targets:
                raise ValueError("Duplicate or missing PLATEAU appearance polygon ID")
            rings = {}
            for coordinates in target.findall("app:TexCoordList/app:textureCoordinates", NS):
                ring_id = coordinates.attrib.get("ring", "").removeprefix("#")
                if not ring_id or not coordinates.text:
                    raise ValueError("Incomplete PLATEAU texture coordinates")
                values = [float(v) for v in coordinates.text.split()]
                if len(values) % 2 or not all(math.isfinite(v) for v in values):
                    raise ValueError("Invalid PLATEAU texture coordinates")
                uv = [[values[i], values[i + 1]] for i in range(0, len(values), 2)]
                if len(uv) > 1 and math.dist(uv[0], uv[-1]) < 1e-7:
                    uv.pop()
                rings[ring_id] = uv
            targets[polygon_id] = {"uri": uri, "rings": rings}
    return targets


def safe_texture_uri(gml_name, uri):
    stem = pathlib.Path(gml_name).stem.removesuffix("_op")
    if not re.fullmatch(re.escape(stem) + r"_appearance/[A-Za-z0-9_.-]+\.jpe?g", uri, re.I):
        raise ValueError(f"Unsupported PLATEAU texture path: {uri!r}")
    return uri


def lod2_surfaces_from_building(elem, area, crs, appearances=None, gml_name=None):
    """Read inline LOD2 thematic surfaces, rings and optional real photo UVs."""
    surfaces = []
    for bounded in elem.findall("bldg:boundedBy", NS):
        for thematic in bounded:
            multi = thematic.find("bldg:lod2MultiSurface", NS)
            if multi is None:
                continue
            surface_type = thematic.tag.rsplit("}", 1)[-1]
            surface_crs = multi.attrib.get("srsName") or crs
            for polygon in multi.findall(".//gml:Polygon", NS):
                rings = []
                ring_ids = []
                boundaries = polygon.findall("gml:exterior", NS) + polygon.findall("gml:interior", NS)
                for boundary in boundaries:
                    ring_node = boundary.find("gml:LinearRing", NS)
                    poslist = boundary.find("gml:LinearRing/gml:posList", NS)
                    if poslist is None or not poslist.text:
                        raise ValueError("LOD2 polygon uses unsupported ring encoding")
                    dimension = int(poslist.attrib.get("srsDimension", multi.attrib.get("srsDimension", 3)))
                    coords = extract_coords_from_poslist(poslist.text, dimension,
                                                          poslist.attrib.get("srsName") or surface_crs)
                    if len(coords) > 1 and math.dist(coords[0], coords[-1]) < 0.001:
                        coords.pop()
                    if len(coords) < 3:
                        raise ValueError("LOD2 polygon has a degenerate ring")
                    rings.append([[*xy_of(lat, lon, area), round(height, 3)] for lat, lon, height in coords])
                    ring_ids.append(ring_node.attrib.get("{%s}id" % NS["gml"]))
                if rings:
                    surface = {"type": surface_type, "rings": rings}
                    polygon_id = polygon.attrib.get("{%s}id" % NS["gml"])
                    appearance = (appearances or {}).get(polygon_id)
                    if appearance:
                        uri = safe_texture_uri(gml_name, appearance["uri"])
                        uv_rings = [appearance["rings"].get(ring_id) for ring_id in ring_ids]
                        if any(uv is None or len(uv) != len(ring) for uv, ring in zip(uv_rings, rings)):
                            raise ValueError(f"LOD2 texture UV mismatch for polygon {polygon_id}")
                        surface["texture_uri"] = uri
                        surface["texture_uv_rings"] = uv_rings
                    surfaces.append(surface)
    if not surfaces:
        return []
    base = min(point[2] for surface in surfaces for ring in surface["rings"] for point in ring)
    for surface in surfaces:
        for ring in surface["rings"]:
            for point in ring:
                point[2] = round(point[2] - base, 3)
    return surfaces


def plateau_buildings(gml_paths, area, include_lod2=True):
    """LOD1 footprints and optional LOD2 surfaces and photo UVs for CityGML buildings.

    Does not support BuildingParts. Fails closed on non-geographic coordinates.
    """
    result = []
    scanned = 0
    for gml in gml_paths:
        path = pathlib.Path(gml)
        if not path.is_file():
            raise FileNotFoundError(path)
        scanned += 1
        # Parse incrementally to avoid loading whole city into RAM.
        parser = ET.iterparse(path, events=("start", "end"))
        _, root = next(parser)
        envelope_crs = None
        appearances = {}
        for event, elem in parser:
            if event == "end" and elem.tag == "{%s}Envelope" % NS["gml"]:
                envelope_crs = elem.attrib.get("srsName")
            if event == "end" and elem.tag == "{%s}appearanceMember" % NS["app"]:
                appearances.update(appearance_targets(elem))
                elem.clear()
            if event != "end" or elem.tag != "{%s}Building" % NS["bldg"]:
                continue
            building_id = (elem.attrib.get("{%s}id" % NS["gml"]) or f"building-{len(result)}")
            polygons = []
            # Only explicitly LOD1 geometry; never mislabel LOD2 as LOD1.
            for lod in elem.findall("bldg:lod1Solid", NS):
                solid = lod.find("gml:Solid", NS)
                if solid is None:
                    raise ValueError(f"Building {building_id}: lod1Solid has no gml:Solid")
                solid_crs = solid.attrib.get("srsName") or envelope_crs
                for pl in lod.findall(".//gml:posList", NS):
                    if not pl.text:
                        continue
                    ring = extract_coords_from_poslist(
                        pl.text, int(pl.attrib.get("srsDimension", solid.attrib.get("srsDimension", 3))),
                        pl.attrib.get("srsName") or solid_crs)
                    if len(ring)<4:
                        continue
                    # Wall rings can have a large projected area. Only flat rings
                    # are candidates for a ground footprint.
                    if max(p[2] for p in ring)-min(p[2] for p in ring) > .7:
                        continue
                    points = dedupe_points(local_of_coords(ring, area))
                    if len(points)<3:
                        continue
                    limit = area["half_size_m"] + 15
                    if (max(x for x,z in points)<-limit or min(x for x,z in points)>limit or
                        max(z for x,z in points)<-limit or min(z for x,z in points)>limit):
                        continue
                    area_m2 = polygon_area(points)
                    # Official LOD1 contains valid small structures around 1 m².
                    # Reject only near-zero rings that cannot survive tile clipping.
                    if area_m2 < .01: continue
                    polygons.append((ring,points,area_m2))
            if polygons:
                # Pick largest horizontal ring, prioritizing lower-elevation ring.
                zmin = min(v[2] for r,_,_ in polygons for v in r)
                ground_candidates = [(r,p,a) for r,p,a in polygons if abs(sum(v[2] for v in r)/len(r)-zmin)<.7]
                _, footprint, _ = max(ground_candidates, key=lambda x:x[2])
                measured = elem.find("bldg:measuredHeight", NS)
                elevations = [v[2] for ring,_,_ in polygons for v in ring]
                h = max(elevations) - min(elevations)
                quality = "geometry-lod1"
                if measured is not None and measured.text:
                    try:
                        cand = float(measured.text)
                        if 1 <= cand <= 300:
                            h = cand
                            quality = "plateau-measuredHeight"
                    except ValueError: pass
                if h >= 1 and h < 500:
                    building = {"id": "plateau-"+building_id, "footprint": footprint,
                                "height_m": round(h,2), "base_elevation_m": 0,
                                "height_quality": quality,
                                "source": "PLATEAU CityGML", "lod": "LOD1"}
                    lod2 = (lod2_surfaces_from_building(elem, area, envelope_crs, appearances, path.name)
                            if include_lod2 else [])
                    if lod2:
                        building["lod2_surfaces"] = lod2
                        building["visual_lod"] = "LOD2 geometry with available photo UVs; locally flattened"
                    result.append(building)
            elem.clear()
            root.clear()
    return result, scanned


def list_gmls(value):
    """Expand directories/globs (Windows PowerShell may not glob)."""
    paths = []
    for pattern in value or []:
        p = pathlib.Path(pattern)
        if p.is_dir():
            paths.extend(str(q) for q in p.rglob("*_bldg_*.gml"))
        elif p.is_file() and p.suffix.lower() == ".gml":
            paths.append(str(p))
        else:
            paths.extend(glob.glob(pattern, recursive=True))
    return sorted(set(paths))


def texture_requests(map_data, file_list):
    """Resolve only referenced JPEGs against the recorded official GML URLs."""
    source_files = {name for source in map_data["provenance"] if source.get("name") == "PLATEAU CityGML"
                    for name in source.get("source_files", [])}
    gml_urls = {}
    for item in file_list.get("files", []):
        url = item.get("url", "")
        if not official_bldg_url(url):
            raise ValueError("Invalid official GML URL in file list")
        gml_urls[pathlib.PurePosixPath(urllib.parse.urlsplit(url).path).name] = url
    requests = {}
    for building in map_data["buildings"]:
        for surface in building.get("lod2_surfaces", []):
            uri = surface.get("texture_uri")
            if not uri:
                continue
            folder = uri.split("/", 1)[0]
            gml_name = folder.removesuffix("_appearance") + "_op.gml"
            safe_texture_uri(gml_name, uri)
            if gml_name not in source_files or gml_name not in gml_urls:
                raise ValueError(f"Texture has no recorded official GML source: {uri}")
            link = urllib.parse.urljoin(gml_urls[gml_name], uri)
            parsed = urllib.parse.urlsplit(link)
            if parsed.scheme != "https" or parsed.netloc != "assets.cms.plateau.reearth.io":
                raise ValueError("Texture URL left official PLATEAU host")
            requests[uri] = link
    return requests


def fetch_textures(map_path, file_list_path, out_dir, dry_run=False, limit=100):
    map_data, file_list = read_json(map_path), read_json(file_list_path)
    requests = texture_requests(map_data, file_list)
    if not requests:
        raise ValueError("No photographic textures referenced by this map")
    if len(requests) > limit:
        raise ValueError(f"Texture count {len(requests)} exceeds --limit={limit}")
    print(f"PLATEAU photo textures referenced: {len(requests)}")
    if dry_run:
        for uri, url in sorted(requests.items()):
            print("DRY RUN", uri, url)
        return
    out_dir = pathlib.Path(out_dir)
    manifest = []
    cumulative = 0
    for uri, url in sorted(requests.items()):
        dest = out_dir / pathlib.PurePosixPath(uri)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file():
            part = dest.with_suffix(dest.suffix + ".part")
            req = urllib.request.Request(url, headers={"User-Agent": "TherabbyGeoEngine-M1/0.1",
                                                    "Accept": "image/jpeg"})
            try:
                with urllib.request.urlopen(req, timeout=60) as response, part.open("wb") as output:
                    if response.status != 200 or not response.headers.get("Content-Type", "").startswith("image/jpeg"):
                        raise RuntimeError(f"Unexpected response for {uri}")
                    size = response.headers.get("Content-Length")
                    if size and int(size) > 20_000_000:
                        raise RuntimeError(f"Texture exceeds 20 MB: {uri}")
                    total = 0
                    while chunk := response.read(256 * 1024):
                        total += len(chunk)
                        if total > 20_000_000:
                            raise RuntimeError(f"Texture exceeds 20 MB: {uri}")
                        output.write(chunk)
                if part.read_bytes()[:2] != b"\xff\xd8":
                    raise RuntimeError(f"Not a JPEG: {uri}")
                part.replace(dest)
                print("Downloaded", uri, f"{dest.stat().st_size:,} bytes")
            except Exception:
                part.unlink(missing_ok=True)
                raise
        size = dest.stat().st_size
        cumulative += size
        if cumulative > 250_000_000:
            raise RuntimeError("Textures exceed 250 MB total; review area before continuing")
        manifest.append({"uri": uri, "source_url": url, "bytes": size,
                         "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
    write_json(out_dir / "texture_file_list.json", {"map": str(map_path), "files": manifest})
    print(f"Saved {len(manifest)} official JPEGs, {cumulative:,} bytes total")


def manifest(area, buildings, roads, osm_source, plateau_files):
    sources = []
    if osm_source:
        sources.append({"name":"OpenStreetMap","type":"real-map-data","license":"ODbL 1.0",
                        "attribution":"© OpenStreetMap contributors","original":osm_source})
    if plateau_files:
        sources.append({"name":"PLATEAU CityGML","type":"real-3d-city-data",
                        "license":"Check dataset terms (CC BY 4.0 / other offered licenses)",
                        "attribution":"Project PLATEAU / source municipality",
                        "city_code_declared":area.get("plateau_city_code"),
                        "dataset_year_declared":area.get("plateau_year"),
                        "files_read":len(plateau_files),
                        "source_files":[pathlib.Path(p).name for p in plateau_files]})
    projected = area.get("projection") == "JGD2011_JPRCS_IX_GRS80"
    return {"schema":"therabby.geoengine.map.v0.1", "area":area,
            "coordinate_system":{"unit":"meter","origin_wgs84":{"lat":area["center_lat"],"lon":area["center_lon"]},
                                 "axes":{"x":"east","y":"up","z":"south"},
                                 "height_datum":"flattened to local zero in M1; not surveyed road elevation",
                                 "projection":("JGD2011 Japan Plane Rectangular CS IX; GRS80 tmerc, lat_0=36, lon_0=139.833333333333, k=0.9999; "
                                               "OSM WGS84 coordinates treated as JGD2011 pending anchor survey"
                                               if projected else "local equirectangular approximation; restricted to <2km"),
                                 "projected_origin_m": (dict(zip(("east", "north"), jprcs_ix(area["center_lat"], area["center_lon"])))
                                                        if projected else None)},
            "provenance":sources,"statistics":{"roads":len(roads),"buildings":len(buildings)},
            "status":{"traffic_rules":"not implemented","collision":"not implemented",
                      "plateau_lod2_geometry":"thematic surfaces where available",
                      "plateau_lod2_textures":"photo UVs where available; source JPEGs fetched separately",
                      "terrain_elevation":"not implemented"},
            "roads":roads,"buildings":buildings}


def build(area, osm_path, plateau_paths, buildings_source, output, lod1_only=False):
    roads, osm_bldgs = [], []
    if osm_path:
        roads, osm_bldgs = parse_osm(read_json(osm_path),area)
    gmls = list_gmls(plateau_paths)
    if plateau_paths and not gmls:
        raise ValueError("No *_bldg_*.gml found in the specified --plateau path")
    plateau_bldgs, count = plateau_buildings(gmls, area, include_lod2=not lod1_only) if gmls else ([], 0)
    if buildings_source == "plateau":
        if not plateau_bldgs:
            raise ValueError("--buildings-source plateau requested but no PLATEAU LOD1 buildings found in area")
        buildings=plateau_bldgs
    elif buildings_source == "hybrid":
        # An OSM footprint is fallback only when its centre is outside every
        # nearby PLATEAU building bbox. It is never presented as measured LOD1.
        bins = {}
        for b in plateau_bldgs:
            xs = [p[0] for p in b["footprint"]]; zs = [p[1] for p in b["footprint"]]
            box = (min(xs), min(zs), max(xs), max(zs))
            for ix in range(math.floor(box[0]/25), math.floor(box[2]/25)+1):
                for iz in range(math.floor(box[1]/25), math.floor(box[3]/25)+1):
                    bins.setdefault((ix, iz), []).append(box)
        fallback = []
        for b in osm_bldgs:
            cx = sum(p[0] for p in b["footprint"])/len(b["footprint"])
            cz = sum(p[1] for p in b["footprint"])/len(b["footprint"])
            if not any(x0-2 <= cx <= x1+2 and z0-2 <= cz <= z1+2
                       for x0,z0,x1,z1 in bins.get((math.floor(cx/25), math.floor(cz/25)), [])):
                fallback.append(b)
        buildings = plateau_bldgs + fallback
    elif buildings_source == "osm":
        buildings=osm_bldgs
    else:
        buildings=plateau_bldgs if plateau_bldgs else osm_bldgs
    if not buildings and not roads:
        raise ValueError("Neither buildings nor roads found. Check AOI and input files.")
    m = manifest(area,buildings,roads,str(osm_path) if osm_path else None,gmls)
    m["buildings_source_selected"] = ("hybrid" if buildings_source == "hybrid" else
                                       "plateau" if buildings is plateau_bldgs else "osm")
    if lod1_only:
        m["status"]["plateau_lod2_geometry"] = "not included in this wide-area LOD1 build"
        m["status"]["plateau_lod2_textures"] = "not included in this wide-area LOD1 build"
    # Test data must never be mistaken for real Fukushima city. Detect bundled fixtures.
    fixture_root = (ROOT / "fixtures").resolve()
    used_paths = ([pathlib.Path(osm_path)] if osm_path else []) + [pathlib.Path(p) for p in gmls]
    is_fixture = any(p.resolve().is_relative_to(fixture_root) for p in used_paths)
    m["data_quality"] = "SYNTHETIC_TEST_FIXTURE" if is_fixture else "UNVERIFIED_REAL_SOURCE_NEEDS_QA"
    if is_fixture:
        m["provenance"] = [{"name":"SYNTHETIC FIXTURE (NOT REAL FUKUSHIMA)",
                            "type":"fictional-test-data", "license":"test-fixture", "attribution":"Therabby development fixture"}]
        for obj in (m["roads"] + m["buildings"]):
            obj["source"] = "synthetic test fixture"
    m["generated_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_json(output,m)
    print(f"Built {output}: buildings={len(buildings)} ({m['buildings_source_selected']}), roads={len(roads)}, PLATEAU GML files={count}")
    return m


def validate(path):
    m = read_json(path)
    if m.get("schema") != "therabby.geoengine.map.v0.1":
        raise ValueError("Unknown map schema")
    if not m.get("provenance"):
        raise ValueError("Missing source provenance; refuse release")
    if m["statistics"]["roads"] != len(m["roads"]) or m["statistics"]["buildings"] != len(m["buildings"]):
        raise ValueError("Map statistics mismatch")
    for b in m["buildings"]:
        if not (len(b["footprint"])>=3 and math.isfinite(b["height_m"]) and b["height_m"]>0):
            raise ValueError(f"Invalid building {b.get('id')}")
        if polygon_area(b["footprint"])<1:
            raise ValueError(f"Degenerate footprint {b.get('id')}")
        for surface in b.get("lod2_surfaces", []):
            if not surface.get("rings"):
                raise ValueError(f"Invalid LOD2 surface in building {b.get('id')}")
            for ring in surface["rings"]:
                if len(ring) < 3 or any(len(point) != 3 or not all(math.isfinite(v) for v in point)
                                             for point in ring):
                    raise ValueError(f"Invalid LOD2 ring in building {b.get('id')}")
            if "texture_uri" in surface:
                uv_rings = surface.get("texture_uv_rings")
                if not uv_rings or len(uv_rings) != len(surface["rings"]):
                    raise ValueError(f"LOD2 texture rings mismatch in building {b.get('id')}")
                for uv, ring in zip(uv_rings, surface["rings"]):
                    if len(uv) != len(ring) or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in uv):
                        raise ValueError(f"Invalid LOD2 texture UV in building {b.get('id')}")
    for road in m["roads"]:
        if len(road["points"])<2 or road["width_m"]<=0:
            raise ValueError(f"Invalid road {road.get('id')}")
    print(f"PASS map integrity: {path}, {len(m['roads'])} roads, {len(m['buildings'])} buildings")


def main():
    parser = argparse.ArgumentParser(description="Therabby GeoEngine M1 — generate maps offline before distributing to client PCs")
    subs=parser.add_subparsers(dest="command",required=True)
    f=subs.add_parser("fetch-osm", help="Download road/building vector data from Overpass (internet needed)")
    f.add_argument("--area",required=True);f.add_argument("--output",required=True)
    f.add_argument("--endpoint",default="https://overpass-api.de/api/interpreter");f.add_argument("--timeout",type=int,default=120)
    f.add_argument("--source",choices=["overpass","osm-api"],default="overpass")
    p=subs.add_parser("fetch-plateau",help="Discover/download building GML files for the AOI using PLATEAU experimental catalog API")
    p.add_argument("--area",required=True);p.add_argument("--output-dir",required=True)
    p.add_argument("--index-file",help="Use saved raw API index response for offline inspection")
    p.add_argument("--dry-run",action="store_true");p.add_argument("--limit",type=int,default=12)
    t=subs.add_parser("fetch-textures",help="Download only photo JPEGs referenced by a built PLATEAU map")
    t.add_argument("--map",required=True);t.add_argument("--file-list",required=True)
    t.add_argument("--output-dir",required=True);t.add_argument("--dry-run",action="store_true")
    t.add_argument("--limit",type=int,default=100)
    b=subs.add_parser("build",help="Generate local-meter scene JSON from saved OSM + optional PLATEAU CityGML")
    b.add_argument("--area",required=True);b.add_argument("--osm");b.add_argument("--plateau",nargs="*",default=[])
    b.add_argument("--buildings-source",choices=["auto","osm","plateau","hybrid"],default="auto")
    b.add_argument("--lod1-only",action="store_true",help="Wide-area geometry preview without LOD2 photo surfaces")
    b.add_argument("--output",required=True)
    v=subs.add_parser("validate",help="Validate scene JSON before publishing")
    v.add_argument("--map",required=True)
    args=parser.parse_args()
    try:
        if args.command=="fetch-osm":
            (osm_fetch_api(load_area(args.area),args.output,args.timeout) if args.source=="osm-api" else
             osm_fetch(load_area(args.area),args.output,args.endpoint,args.timeout))
        elif args.command=="fetch-plateau":fetch_plateau(load_area(args.area),args.output_dir,args.index_file,args.dry_run,args.limit)
        elif args.command=="fetch-textures":fetch_textures(args.map,args.file_list,args.output_dir,args.dry_run,args.limit)
        elif args.command=="build":build(load_area(args.area),args.osm,args.plateau,args.buildings_source,args.output,args.lod1_only)
        elif args.command=="validate":validate(args.map)
    except (ValueError,FileNotFoundError,RuntimeError,ET.ParseError,json.JSONDecodeError) as exc:
        print("ERROR:",exc,file=sys.stderr)
        sys.exit(2)


if __name__=="__main__": main()
