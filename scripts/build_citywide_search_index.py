#!/usr/bin/env python3
"""Build a local, offline road-name search index from projected OSM tiles."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib

import geoengine

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADS = ROOT / "data/derived/fukushima-citywide-roads-v1/tileset.json"
OUT = ROOT / "data/derived/fukushima-citywide-roads-v1/search_index.json"


def build(roads_manifest=ROADS, output=OUT):
    roads_manifest = pathlib.Path(roads_manifest).resolve()
    manifest = geoengine.read_json(roads_manifest)
    if manifest.get("schema") != "therabby.geoengine.citywide-road-tiles.v0.1" or manifest.get("status") != "complete":
        raise ValueError("Expected complete projected Fukushima road tiles")
    names = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0, []])
    for tile in manifest["tiles"]:
        data = geoengine.read_json(roads_manifest.parent / tile["path"])
        for edge in data["edges"]:
            name = edge.get("name", "").strip()
            if not name or len(name) > 100:
                continue
            a, b = edge["points"]
            east = tile["bbox_east_north_m"][0] + (a[0] + b[0]) / 2
            north = tile["bbox_east_north_m"][3] - (a[1] + b[1]) / 2
            weight = math.hypot(b[0] - a[0], b[1] - a[1])
            if weight <= 0:
                continue
            value = names[name]
            value[0] += east * weight
            value[1] += north * weight
            value[2] += weight
            value[3] += 1
            value[4].append((east, north,
                             edge.get("ground_height_from_tp_m") is not None and
                             edge.get("ground_height_to_tp_m") is not None))
    entries = []
    for name, value in names.items():
        if value[2] <= 0:
            continue
        center = (value[0] / value[2], value[1] / value[2])
        grounded = [point for point in value[4] if point[2]]
        candidates = grounded or value[4]
        representative = min(candidates, key=lambda point: (point[0]-center[0])**2 +
                             (point[1]-center[1])**2)
        entries.append({"name": name, "east_m": round(representative[0], 2),
                        "north_m": round(representative[1], 2),
                        "source": "OpenStreetMap",
                        "quality": "OSM road-segment midpoint nearest length-weighted center; not a surveyed place point",
                        "ground_height_available": bool(representative[2]),
                        "segment_count": value[3]})
    entries.sort(key=lambda item: (-item["segment_count"], item["name"]))
    result = {"schema": "therabby.geoengine.citywide-search.v0.1",
              "projected_crs": manifest["projected_crs"],
              "source_manifest": str(roads_manifest.relative_to(ROOT)).replace('\\', '/'),
              "source_manifest_sha256": hashlib.sha256(roads_manifest.read_bytes()).hexdigest(),
              "attribution": manifest["attribution"], "license": manifest["license"],
              "entries": entries}
    geoengine.write_json(output, result)
    print(f"Indexed {len(entries)} OSM road names: {output}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roads-manifest", type=pathlib.Path, default=ROADS)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    args = parser.parse_args()
    build(args.roads_manifest, args.out)


if __name__ == "__main__":
    main()
