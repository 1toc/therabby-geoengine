#!/usr/bin/env python3
"""Clip official Fukushima PLATEAU LOD1 footprints and write 1 km JSON tiles.

Requires Shapely on the development machine. Runtime/browser clients only consume
the generated JSON and need no Python packages. Source heights are preserved;
unknown ground elevation is deliberately kept null.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import geoengine  # noqa: E402

SCHEMA = "therabby.geoengine.citywide-lod1-tiles.v0.1"
TILE_SIZE = 1000
BOUNDARY = ROOT / "modules/city-boundary/data/fukushima_city_boundary.geojson"
SOURCE_DIR = ROOT / "data/raw/plateau/fukushima_citywide_2025"
SOURCE_MANIFEST = SOURCE_DIR / "source_manifest.json"
OUTPUT_DIR = ROOT / "data/derived/fukushima-citywide-lod1"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tile_index(east: float, north: float) -> tuple[int, int]:
    return math.floor(east / TILE_SIZE), math.floor(north / TILE_SIZE)


def output_xy(east: float, north: float, tx: int, ty: int) -> list[float]:
    return [round(east - tx * TILE_SIZE, 3), round((ty + 1) * TILE_SIZE - north, 3)]


def iter_rings(poly, tx: int, ty: int):
    outer = [output_xy(x, y, tx, ty) for x, y in poly.exterior.coords]
    holes = [[output_xy(x, y, tx, ty) for x, y in ring.coords] for ring in poly.interiors]
    return outer, holes


def verify_sources(manifest: dict, source_dir: pathlib.Path, verify_hashes: bool) -> list[dict]:
    if manifest.get("status") != "complete" or manifest.get("municipality_code") != "07201":
        raise ValueError("PLATEAU source manifest must be complete and for Fukushima City (07201)")
    files = manifest.get("files", [])
    if len(files) != manifest.get("completed_files") or len(files) != manifest.get("file_count", len(files)):
        raise ValueError("Source manifest file count is inconsistent")
    for item in files:
        path = source_dir / item["filename"]
        if not path.is_file() or path.stat().st_size != item["file_size"]:
            raise ValueError(f"Missing or incorrect source file size: {path.name}")
        if verify_hashes and sha256_file(path) != item["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {path.name}")
    return files


def load_boundary(shapely_shape, shapely_transform):
    metadata = geoengine.read_json(ROOT / "modules/city-boundary/data/boundary_metadata.json")
    if metadata.get("status") != "official_2026" or metadata.get("municipality_code") != "07201":
        raise ValueError("Refusing non-official/non-Fukushima boundary")
    raw = geoengine.read_json(BOUNDARY)
    geom = shapely_shape(raw["features"][0]["geometry"])
    if geom.geom_type not in ("Polygon", "MultiPolygon") or not geom.is_valid:
        raise ValueError("Official boundary must be a valid polygon")
    projected = shapely_transform(lambda lon, lat, z=None: geoengine.jprcs_ix(lat, lon), geom)
    if not projected.is_valid:
        raise ValueError("Projected official boundary is invalid")
    return projected, metadata, sha256_file(BOUNDARY)


def init_db(path: pathlib.Path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("CREATE TABLE IF NOT EXISTS processed (filename TEXT PRIMARY KEY, parsed INTEGER, clipped INTEGER)")
    for column in ("intersecting", "clipped_buildings", "invalid", "outside"):
        if column not in {row[1] for row in db.execute("PRAGMA table_info(processed)")}:
            db.execute(f"ALTER TABLE processed ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
    if "expected" not in {row[1] for row in db.execute("PRAGMA table_info(processed)")}:
        db.execute("ALTER TABLE processed ADD COLUMN expected INTEGER NOT NULL DEFAULT 0")
    db.execute("CREATE TABLE IF NOT EXISTS buildings (tile_x INTEGER, tile_y INTEGER, source_id TEXT, mesh TEXT, geom BLOB, height REAL, height_quality TEXT, PRIMARY KEY(tile_x,tile_y,source_id))")
    db.execute("CREATE INDEX IF NOT EXISTS building_tiles ON buildings(tile_x,tile_y)")
    return db


def build(source_manifest=SOURCE_MANIFEST, source_dir=SOURCE_DIR, output_dir=OUTPUT_DIR,
          verify_hashes=True, limit_files=None):
    try:
        from shapely.geometry import Polygon, shape
        from shapely.ops import transform
        from shapely import wkb
    except ImportError as exc:
        raise RuntimeError("Shapely is required for topology-safe boundary clipping (install in the development Python)") from exc

    manifest = geoengine.read_json(source_manifest)
    files = verify_sources(manifest, source_dir, verify_hashes)
    if limit_files is not None:
        files = files[:limit_files]
    boundary, boundary_meta, boundary_hash = load_boundary(shape, transform)
    if manifest.get("boundary_sha256") != boundary_meta.get("source_sha256"):
        raise ValueError("PLATEAU source download used a different boundary version")
    plan_path = ROOT / "data/derived/fukushima_citywide_plateau_plan.json"
    plan = geoengine.read_json(plan_path) if plan_path.is_file() else {}
    # Parser returns local east/north offsets around this stable origin.
    area = {"center_lat": 37.8004245, "center_lon": 140.3996455,
            "half_size_m": 50000, "projection": "JGD2011_JPRCS_IX_GRS80"}
    origin_e, origin_n = geoengine.jprcs_ix(area["center_lat"], area["center_lon"])
    output_dir.mkdir(parents=True, exist_ok=True)
    db = init_db(output_dir / "build.sqlite3")
    totals = {"files_processed": 0, "parsed_buildings": 0, "inside_or_intersecting": 0,
              "clipped_buildings": 0, "invalid_footprints": 0, "outside_boundary": 0}
    start = time.monotonic()
    for index, item in enumerate(files, 1):
        if db.execute("SELECT 1 FROM processed WHERE filename=?", (item["filename"],)).fetchone():
            continue
        gml_path = source_dir / item["filename"]
        parsed, _ = geoengine.plateau_buildings([gml_path], area, include_lod2=False)
        file_clipped = 0
        file_intersecting = file_clipped_buildings = file_invalid = file_outside = 0
        with db:
            for building in parsed:
                totals["parsed_buildings"] += 1
                coords = [(round(x + origin_e, 3), round(origin_n - z, 3)) for x, z in building["footprint"]]
                geom = Polygon(coords)
                if not geom.is_valid or geom.area <= 0:
                    totals["invalid_footprints"] += 1
                    file_invalid += 1
                    continue
                if not geom.intersects(boundary):
                    totals["outside_boundary"] += 1
                    file_outside += 1
                    continue
                clipped = geom.intersection(boundary)
                parts = [clipped] if clipped.geom_type == "Polygon" else list(getattr(clipped, "geoms", []))
                parts = [part for part in parts if part.geom_type == "Polygon" and part.area > 0.01]
                if not parts:
                    continue
                totals["inside_or_intersecting"] += 1
                file_intersecting += 1
                # Keep a complete building intact when fully inside; boundary-crossing
                # buildings are represented by clipped polygon parts and retain source ID.
                for part_no, part in enumerate(parts):
                    point = part.representative_point()
                    tx, ty = tile_index(point.x, point.y)
                    source_id = building["id"] if len(parts) == 1 else f"{building['id']}#part{part_no}"
                    db.execute("INSERT OR REPLACE INTO buildings VALUES(?,?,?,?,?,?,?)",
                               (tx, ty, source_id, item["mesh_code"], wkb.dumps(part),
                                building["height_m"], building["height_quality"]))
                    file_clipped += 1
                    if not geom.covers(part):
                        totals["clipped_buildings"] += 1
                        file_clipped_buildings += 1
            db.execute("INSERT INTO processed(filename,parsed,clipped,intersecting,clipped_buildings,invalid,outside,expected) VALUES(?,?,?,?,?,?,?,?)",
                       (item["filename"], len(parsed), file_clipped, file_intersecting,
                        file_clipped_buildings, file_invalid, file_outside, item.get("lod1_features", 0)))
        totals["files_processed"] += 1
        if index == 1 or index % 10 == 0 or index == len(files):
            print(f"[{index}/{len(files)}] {item['filename']}: parsed={len(parsed)} clipped={file_clipped}; elapsed={time.monotonic()-start:.0f}s", flush=True)
        del parsed

    tiles = []
    cursor = db.execute("SELECT DISTINCT tile_x,tile_y FROM buildings ORDER BY tile_x,tile_y")
    for tx, ty in cursor.fetchall():
        tile_name = f"{tx}_{ty}.json"
        tile_path = output_dir / "tiles" / tile_name
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with tile_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write('{"schema":"therabby.geoengine.building-tile.v0.1","tile_id":')
            stream.write(json.dumps(f"{tx}_{ty}"))
            stream.write(',"tile_size_m":1000,"buildings":[')
            rows = db.execute("SELECT source_id,mesh,geom,height,height_quality FROM buildings WHERE tile_x=? AND tile_y=? ORDER BY source_id", (tx, ty))
            for row in rows:
                geom = wkb.loads(row[2])
                footprint, holes = iter_rings(geom, tx, ty)
                record = {"id": row[0], "mesh_code": row[1], "footprint": footprint,
                          "height_m": row[3], "height_quality": row[4], "base_elevation_m": None,
                          "vertical_datum": None, "source": "PLATEAU CityGML 2025", "lod": "LOD1",
                          "visual_quality": "official LOD1 footprint/height; terrain elevation unknown"}
                if holes:
                    record["holes"] = holes
                if count:
                    stream.write(",")
                json.dump(record, stream, ensure_ascii=False, separators=(",", ":"))
                count += 1
            stream.write("]}\n")
        tiles.append({"id": f"{tx}_{ty}", "path": f"tiles/{tile_name}",
                      "tile_origin_east_m": tx * TILE_SIZE, "tile_origin_north_m": (ty + 1) * TILE_SIZE,
                      "tile_size_m": TILE_SIZE, "building_count": count,
                      "byte_length": tile_path.stat().st_size, "sha256": sha256_file(tile_path)})
    totals["files_processed"] = db.execute("SELECT COUNT(*) FROM processed").fetchone()[0]
    totals["parsed_buildings"] = db.execute("SELECT COALESCE(SUM(parsed),0) FROM processed").fetchone()[0]
    totals["inside_or_intersecting"] = db.execute("SELECT COALESCE(SUM(intersecting),0) FROM processed").fetchone()[0]
    totals["clipped_buildings"] = db.execute("SELECT COALESCE(SUM(clipped_buildings),0) FROM processed").fetchone()[0]
    totals["invalid_footprints"] = db.execute("SELECT COALESCE(SUM(invalid),0) FROM processed").fetchone()[0]
    totals["outside_boundary"] = db.execute("SELECT COALESCE(SUM(outside),0) FROM processed").fetchone()[0]
    # A one-file preview build may have written the first row before diagnostics
    # columns were added; all footprints in that mesh were successfully tiled.
    db.execute("UPDATE processed SET intersecting=parsed-outside-invalid WHERE intersecting=0 AND parsed>0 AND clipped>0")
    db.commit()
    totals["inside_or_intersecting"] = db.execute("SELECT COALESCE(SUM(intersecting),0) FROM processed").fetchone()[0]
    totals["tiled_buildings"] = db.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
    db.close()
    totals["expected_lod1_features"] = plan.get("lod1_feature_count")
    totals["parser_feature_gap"] = max(0, (totals["expected_lod1_features"] or totals["parsed_buildings"]) - totals["parsed_buildings"])
    all_files_done = totals["files_processed"] == len(manifest["files"])
    result = {"schema": SCHEMA, "status": ("complete_with_gaps" if all_files_done and totals["parser_feature_gap"] else
                                                   "complete" if all_files_done else "partial"),
              "processing_complete": all_files_done,
              "municipality_code": "07201", "dataset_year": 2025, "projected_crs": "JGD2011 / Japan Plane Rectangular CS IX (EPSG:6677)",
              "vertical_datum": None, "tile_size_m": TILE_SIZE, "grid_origin": {"east_m": 0, "north_m": 0},
              "boundary_source": boundary_meta.get("source", "MLIT N03-2026 official boundary"),
              "boundary_sha256": boundary_meta.get("source_sha256"), "processed_boundary_geojson_sha256": boundary_hash,
              "source_manifest": str(source_manifest.relative_to(ROOT)),
              "source_manifest_sha256": sha256_file(source_manifest),
              "attribution": "Project PLATEAU / Fukushima City; check dataset license before redistribution",
              "height_semantics": "official PLATEAU measuredHeight or LOD1 geometry-derived height; base elevation unknown",
              "tile_assignment": "Each whole clipped building polygon is assigned to the 1 km tile containing its representative point; footprints can extend beyond that tile's nominal bounds.",
              "statistics": {**totals, "expected_source_files": len(manifest["files"])}, "tiles": tiles,
              "limitations": (["Catalog LOD1 feature count exceeds extracted footprints; unmatched source features need diagnostics."]
                              if totals["parser_feature_gap"] else []) + [
                              "Building base elevation and vertical datum are unknown and remain null.",
                              "LOD1 tiles are data output; citywide GLB export is not completed."]}
    geoengine.write_json(output_dir / "tileset.json", result)
    print(json.dumps(result["statistics"], ensure_ascii=False, indent=2))
    print(f"Wrote {len(tiles)} tiles to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=pathlib.Path, default=SOURCE_MANIFEST)
    parser.add_argument("--source-dir", type=pathlib.Path, default=SOURCE_DIR)
    parser.add_argument("--output-dir", type=pathlib.Path, default=OUTPUT_DIR)
    parser.add_argument("--skip-hash-verification", action="store_true", help="Skip 2 GB source SHA-256 pass for trusted already-verified downloads")
    parser.add_argument("--limit-files", type=int, help="Process only the first N files (development preview; leaves partial tileset)")
    args = parser.parse_args()
    build(args.source_manifest, args.source_dir, args.output_dir,
          verify_hashes=not args.skip_hash_verification, limit_files=args.limit_files)


if __name__ == "__main__":
    main()
