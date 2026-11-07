#!/usr/bin/env python3
"""Project already-clipped Fukushima OSM roads into seam-stable 1 km tiles.

Input is the existing Geofabrik-derived city road index. Road widths are class
estimates and heights/road-deck status remain unknown.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib

import geoengine
from terrain_grid import sample_dem

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_INDEX = ROOT / "modules/city-boundary/data/roads/index.json"
OUT = ROOT / "data/derived/fukushima-citywide-roads-v1"
DEM_MANIFEST = ROOT / "data/raw/gsi_dem5a_citywide_full/source_manifest.json"
TILE_SIZE = 1000


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clip_segment(a, b, bounds):
    """Liang-Barsky clipping in absolute east/north metres."""
    x0, y0 = a
    dx, dy = b[0] - x0, b[1] - y0
    left, bottom, right, top = bounds
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, x0-left), (dx, right-x0), (-dy, y0-bottom), (dy, top-y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        t = q/p
        if p < 0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
        if lo > hi:
            return None
    if (hi-lo) * math.hypot(dx, dy) < .01:
        return None
    return ((round(x0+lo*dx, 3), round(y0+lo*dy, 3)),
            (round(x0+hi*dx, 3), round(y0+hi*dy, 3)))


def node_id(point):
    return f"n:{round(point[0]*1000)}:{round(point[1]*1000)}"


def load_dem(manifest_path):
    from PIL import Image
    manifest_path = pathlib.Path(manifest_path).resolve()
    manifest = geoengine.read_json(manifest_path)
    if (manifest.get("schema") != "therabby.geoengine.source.citywide-dem5a-full.v0.1" or
            manifest.get("vertical_datum") != "T.P. (Tokyo Peil)"):
        raise ValueError("Expected official GSI DEM5A T.P. source manifest")
    images = {}
    for item in manifest["tiles"]:
        if item.get("status") != "downloaded":
            continue
        path = manifest_path.parent / item["file"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"DEM5A source hash mismatch: {path}")
        images[(item["x"], item["y"])] = Image.open(path).convert("RGB")
    return images, manifest_path


def road_tiles(source_index=SOURCE_INDEX, output_dir=OUT, dem_manifest=DEM_MANIFEST):
    source_index = pathlib.Path(source_index).resolve()
    output_dir = pathlib.Path(output_dir).resolve()
    source = geoengine.read_json(source_index)
    if (source.get("schema") != "therabby.geodata.roads.v1" or source.get("status") != "ready" or
            source.get("coverage") != "municipality" or source.get("coordinate_system") != "EPSG:4326" or
            source.get("boundary_quality") != "official_2026" or source.get("source") != "geofabrik_pbf"):
        raise ValueError("Expected official-boundary Fukushima OSM road tile index in EPSG:4326")
    dem_images, dem_path = load_dem(dem_manifest)
    ground_cache = {}
    tiles = collections.defaultdict(dict)
    source_segments = 0
    for entry in source["tiles"]:
        path = source_index.parent / entry["file"]
        data = geoengine.read_json(path)
        if data.get("type") != "FeatureCollection":
            raise ValueError(f"Unexpected road GeoJSON: {path}")
        for feature in data["features"]:
            if feature.get("geometry", {}).get("type") != "LineString":
                raise ValueError(f"Unsupported road geometry in {path}")
            props = feature["properties"]
            osm_id = str(props.get("osm_id", ""))
            highway = props.get("highway", "")
            if not osm_id.isdigit() or not highway:
                raise ValueError(f"Missing OSM way ID/highway in {path}")
            coords = feature["geometry"]["coordinates"]
            if len(coords) < 2:
                continue
            projected = []
            for lon, lat in coords:
                if not (20 <= lat <= 50 and 120 <= lon <= 155):
                    raise ValueError(f"Road coordinate outside Japanese EPSG:4326 range: {lon},{lat}")
                projected.append(geoengine.jprcs_ix(lat, lon))
            for pair_index, (a, b) in enumerate(zip(projected, projected[1:])):
                source_segments += 1
                min_tx, max_tx = math.floor(min(a[0], b[0])/TILE_SIZE), math.floor(max(a[0], b[0])/TILE_SIZE)
                min_ty, max_ty = math.floor(min(a[1], b[1])/TILE_SIZE), math.floor(max(a[1], b[1])/TILE_SIZE)
                if (max_tx-min_tx+1)*(max_ty-min_ty+1) > 64:
                    raise ValueError(f"OSM road segment crosses over 64 km²: {osm_id}")
                for tx in range(min_tx, max_tx+1):
                    for ty in range(min_ty, max_ty+1):
                        pair = clip_segment(a, b, (tx*TILE_SIZE, ty*TILE_SIZE,
                                                    (tx+1)*TILE_SIZE, (ty+1)*TILE_SIZE))
                        if not pair:
                            continue
                        p, q = pair
                        # A line exactly on a grid edge belongs to one tile.
                        mid = ((p[0]+q[0])/2, (p[1]+q[1])/2)
                        if (math.floor(mid[0]/TILE_SIZE), math.floor(mid[1]/TILE_SIZE)) != (tx, ty):
                            continue
                        if p == q:
                            continue
                        key = f"{osm_id}:{node_id(p)}:{node_id(q)}"
                        edge_id = "osm-edge-" + hashlib.sha1(key.encode("ascii")).hexdigest()[:20]
                        heights = []
                        length2 = (b[0]-a[0])**2 + (b[1]-a[1])**2
                        for point in (p, q):
                            nid = node_id(point)
                            if nid not in ground_cache:
                                fraction = max(0, min(1, ((point[0]-a[0])*(b[0]-a[0]) +
                                                          (point[1]-a[1])*(b[1]-a[1])) / length2))
                                lon = coords[pair_index][0] + (coords[pair_index+1][0]-coords[pair_index][0]) * fraction
                                lat = coords[pair_index][1] + (coords[pair_index+1][1]-coords[pair_index][1]) * fraction
                                try:
                                    ground_cache[nid] = round(sample_dem(dem_images, lat, lon), 2)
                                except ValueError:
                                    ground_cache[nid] = None
                            heights.append(ground_cache[nid])
                        edge = {"id": edge_id, "source_way_id": f"osm-way-{osm_id}",
                                "from_node": node_id(p), "to_node": node_id(q),
                                "points": [[round(p[0]-tx*TILE_SIZE, 3), round((ty+1)*TILE_SIZE-p[1], 3)],
                                           [round(q[0]-tx*TILE_SIZE, 3), round((ty+1)*TILE_SIZE-q[1], 3)]],
                                "highway": highway, "road_class": props.get("road_class", ""),
                                "name": props.get("name", ""), "oneway_osm_tag": props.get("oneway", ""),
                                "bridge_osm_tag": props.get("bridge", ""), "tunnel_osm_tag": props.get("tunnel", ""),
                                "lanes_osm_tag": props.get("lanes", ""), "access_osm_tag": props.get("access", ""),
                                "width_m": geoengine.HIGHWAY_WIDTH.get(highway, 5),
                                "width_quality": "class-estimate", "road_deck_height_m": None,
                                "ground_height_from_tp_m": heights[0],
                                "ground_height_to_tp_m": heights[1],
                                "ground_height_quality": "GSI DEM5A ground sample, not road deck" if all(h is not None for h in heights) else "unknown: DEM5A unavailable or no-data",
                                "legal_drivability": None, "source": "OpenStreetMap"}
                        existing = tiles[(tx, ty)].get(edge_id)
                        if existing is not None and existing != edge:
                            raise ValueError(f"OSM edge ID collision: {edge_id}")
                        tiles[(tx, ty)][edge_id] = edge
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tiles").mkdir(exist_ok=True)
    manifest_tiles = []
    all_nodes = set()
    for (tx, ty), edges_by_id in sorted(tiles.items()):
        edges = [edges_by_id[key] for key in sorted(edges_by_id)]
        for edge in edges:
            all_nodes.add(edge["from_node"])
            all_nodes.add(edge["to_node"])
        tile_id = f"{tx}_{ty}"
        path = output_dir / "tiles" / f"{tile_id}.json"
        tile = {"schema": "therabby.geoengine.citywide-road-tile.v0.1", "tile_id": tile_id,
                "projected_crs": "EPSG:6677", "tile_origin_east_m": tx*TILE_SIZE,
                "tile_origin_north_m": (ty+1)*TILE_SIZE, "tile_size_m": TILE_SIZE,
                "edges": edges}
        path.write_text(json.dumps(tile, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        manifest_tiles.append({"id": tile_id, "path": f"tiles/{tile_id}.json", "edge_count": len(edges),
                               "byte_length": path.stat().st_size, "sha256": sha256(path),
                               "bbox_east_north_m": [tx*TILE_SIZE, ty*TILE_SIZE,
                                                     (tx+1)*TILE_SIZE, (ty+1)*TILE_SIZE]})
    manifest = {"schema": "therabby.geoengine.citywide-road-tiles.v0.1", "status": "complete",
                "projected_crs": "JGD2011 / Japan Plane Rectangular CS IX (EPSG:6677)",
                "vertical_datum": None, "tile_size_m": TILE_SIZE,
                "source_index": str(source_index.relative_to(ROOT)).replace('\\', '/'),
                "source_index_sha256": sha256(source_index),
                "dem_source_manifest": str(dem_path.relative_to(ROOT)).replace('\\', '/'),
                "dem_source_manifest_sha256": sha256(dem_path),
                "source_pbf_sha256": source["source_metadata"]["sha256"],
                "source_snapshot_utc": source["source_metadata"]["snapshot_timestamp_utc"],
                "source_url": source["source_detail"], "attribution": source["attribution"],
                "license": source["license"],
                "quality": "OSM centerlines; class-estimated widths; DEM5A ground sample where available; road deck height and legal drivability unverified",
                "statistics": {"source_line_segments": source_segments,
                               "output_edges": sum(t["edge_count"] for t in manifest_tiles),
                               "unique_nodes": len(all_nodes), "ground_sampled_nodes": sum(value is not None for value in ground_cache.values()),
                               "ground_unknown_nodes": sum(value is None for value in ground_cache.values()),
                               "tiles": len(manifest_tiles)},
                "tiles": manifest_tiles}
    geoengine.write_json(output_dir / "tileset.json", manifest)
    print(json.dumps(manifest["statistics"], ensure_ascii=False))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", type=pathlib.Path, default=SOURCE_INDEX)
    parser.add_argument("--output-dir", type=pathlib.Path, default=OUT)
    parser.add_argument("--dem-manifest", type=pathlib.Path, default=DEM_MANIFEST)
    args = parser.parse_args()
    road_tiles(args.source_index, args.output_dir, args.dem_manifest)


if __name__ == "__main__":
    main()
