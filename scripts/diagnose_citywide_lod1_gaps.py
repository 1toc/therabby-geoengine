#!/usr/bin/env python3
"""Explain PLATEAU LOD1 buildings omitted by the current Fukushima parser.

This reads the already-downloaded source GMLs and never modifies them. The
report deliberately separates catalog counts from observed Building IDs.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import geoengine  # noqa: E402

DEFAULT_SOURCE = ROOT / "data/raw/plateau/fukushima_citywide_2025"
DEFAULT_MANIFEST = DEFAULT_SOURCE / "source_manifest.json"
DEFAULT_OUTPUT = ROOT / "data/derived/fukushima-citywide-lod1/parser_gap_report.json"
BUILDING = "{%s}Building" % geoengine.NS["bldg"]
GML_ID = "{%s}id" % geoengine.NS["gml"]


def classify_unmatched(building, envelope_crs, area):
    """Return the first existing-parser rule that excludes a Building."""
    solids = building.findall("bldg:lod1Solid", geoengine.NS)
    if not solids:
        return "no_lod1_solid"

    candidates = []
    saw_poslist = False
    saw_flat_ring = False
    saw_supported_ring = False
    for lod in solids:
        solid = lod.find("gml:Solid", geoengine.NS)
        if solid is None:
            return "lod1_solid_without_gml_solid"
        solid_crs = solid.attrib.get("srsName") or envelope_crs
        for poslist in lod.findall(".//gml:posList", geoengine.NS):
            if not poslist.text:
                continue
            saw_poslist = True
            try:
                ring = geoengine.extract_coords_from_poslist(
                    poslist.text,
                    int(poslist.attrib.get("srsDimension", solid.attrib.get("srsDimension", 3))),
                    poslist.attrib.get("srsName") or solid_crs,
                )
            except (ValueError, TypeError):
                continue
            if len(ring) < 4:
                continue
            saw_supported_ring = True
            if max(p[2] for p in ring) - min(p[2] for p in ring) > 0.7:
                continue
            saw_flat_ring = True
            points = geoengine.dedupe_points(geoengine.local_of_coords(ring, area))
            if len(points) < 3:
                continue
            limit = area["half_size_m"] + 15
            if (max(x for x, _ in points) < -limit or min(x for x, _ in points) > limit or
                    max(z for _, z in points) < -limit or min(z for _, z in points) > limit):
                continue
            size = geoengine.polygon_area(points)
            if size >= .01:
                candidates.append((ring, size))

    if not saw_poslist:
        return "no_nonempty_poslist"
    if not saw_supported_ring:
        return "unsupported_crs_dimension_or_ring"
    if not saw_flat_ring:
        return "no_horizontal_ground_ring"
    if not candidates:
        return "footprint_outside_parser_window_or_area_below_0_01m2"

    z_values = [p[2] for ring, _ in candidates for p in ring]
    height = max(z_values) - min(z_values)
    measured = building.find("bldg:measuredHeight", geoengine.NS)
    if measured is not None and measured.text:
        try:
            value = float(measured.text)
            if 1 <= value <= 300:
                height = value
        except ValueError:
            pass
    if not (1 <= height < 500):
        return "height_outside_parser_range"
    return "unclassified_parser_disagreement"


def inspect_file(path, item, area):
    """Match parser output IDs against raw Building IDs and diagnose gaps."""
    parser_ids = set()
    parser_error = None
    try:
        parsed, _ = geoengine.plateau_buildings([path], area, include_lod2=False)
        parser_ids = {record["id"].removeprefix("plateau-") for record in parsed}
    except Exception as exc:  # preserve file-level failures in the report
        parser_error = f"{type(exc).__name__}: {exc}"

    envelope_crs = None
    observed = 0
    gaps = []
    counts = collections.Counter()
    parser = ET.iterparse(path, events=("start", "end"))
    _, root = next(parser)
    for event, elem in parser:
        if event == "end" and elem.tag == "{%s}Envelope" % geoengine.NS["gml"]:
            envelope_crs = elem.attrib.get("srsName")
        if event != "end" or elem.tag != BUILDING:
            continue
        building_id = elem.attrib.get(GML_ID) or f"missing-gml-id-{observed}"
        observed += 1
        if building_id not in parser_ids:
            reason = "parser_file_error" if parser_error else classify_unmatched(elem, envelope_crs, area)
            counts[reason] += 1
            gaps.append({"id": building_id, "reason": reason})
        elem.clear()
        root.clear()
    return {
        "filename": path.name,
        "mesh_code": item.get("mesh_code"),
        "catalog_lod1_features": item.get("lod1_features"),
        "observed_building_elements": observed,
        "parser_matched_buildings": len(parser_ids),
        "unmatched_buildings": len(gaps),
        "reason_counts": dict(sorted(counts.items())),
        "unmatched_ids": gaps,
        "parser_error": parser_error,
    }


def build_report(source_dir=DEFAULT_SOURCE, manifest_path=DEFAULT_MANIFEST):
    manifest = geoengine.read_json(manifest_path)
    area = {"center_lat": 37.8004245, "center_lon": 140.3996455,
            "half_size_m": 50000, "projection": "JGD2011_JPRCS_IX_GRS80"}
    files = []
    reasons = collections.Counter()
    for index, item in enumerate(manifest["files"], 1):
        path = pathlib.Path(source_dir) / item["filename"]
        result = inspect_file(path, item, area)
        files.append(result)
        reasons.update(result["reason_counts"])
        if index == 1 or index % 10 == 0 or index == len(manifest["files"]):
            print(f"[{index}/{len(manifest['files'])}] {path.name}: "
                  f"observed={result['observed_building_elements']} "
                  f"matched={result['parser_matched_buildings']} "
                  f"unmatched={result['unmatched_buildings']}", flush=True)
    observed_total = sum(row["observed_building_elements"] for row in files)
    matched_total = sum(row["parser_matched_buildings"] for row in files)
    unmatched_total = sum(row["unmatched_buildings"] for row in files)
    expected = sum(row.get("lod1_features", 0) for row in manifest["files"])
    return {
        "schema": "therabby.geoengine.citywide-lod1-parser-gap-report.v0.1",
        "municipality_code": manifest.get("municipality_code"),
        "dataset_year": manifest.get("dataset_year"),
        "source_manifest": str(pathlib.Path(manifest_path).as_posix()),
        "catalog_lod1_features": expected,
        "observed_building_elements": observed_total,
        "parser_matched_buildings": matched_total,
        "unmatched_buildings": unmatched_total,
        "catalog_minus_observed": expected - observed_total,
        "reason_counts": dict(sorted(reasons.items())),
        "files": files,
        "interpretation": "Catalog LOD1 counts, XML Building elements, and parser-accepted footprints are reported separately; unmatched records are not treated as recoverable until their source geometry and CRS are verified.",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dir", type=pathlib.Path, default=DEFAULT_SOURCE)
    ap.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args(argv)
    report = build_report(args.source_dir, args.manifest)
    geoengine.write_json(args.out, report)
    print(f"Report: {args.out}")
    print(f"Catalog={report['catalog_lod1_features']} observed={report['observed_building_elements']} "
          f"parser={report['parser_matched_buildings']} unmatched={report['unmatched_buildings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
