#!/usr/bin/env python3
"""Preflight Fukushima-wide PLATEAU building data without downloading GML files."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import time

from geoengine import official_bldg_url, write_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOUNDARY = ROOT / "modules/city-boundary/data/fukushima_city_boundary_full.geojson"
DEFAULT_METADATA = ROOT / "modules/city-boundary/data/boundary_metadata.json"
DEFAULT_OUTPUT = ROOT / "data/derived/fukushima_citywide_plateau_plan.json"
CATALOG_BASE = "https://api.plateauview.mlit.go.jp/datacatalog/citygml"
MAX_CATALOG_BYTES = 15_000_000
REVIEW_THRESHOLD_BYTES = 1_000_000_000


def bbox_from_geojson(feature_collection):
    if feature_collection.get("type") != "FeatureCollection":
        raise ValueError("境界はGeoJSON FeatureCollectionで指定してください")
    features = feature_collection.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("境界GeoJSONにfeaturesがありません")
    bounds = [float("inf"), float("inf"), float("-inf"), float("-inf")]

    def visit(value):
        if not isinstance(value, list):
            return
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            lon, lat = value[:2]
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("境界座標が経度・緯度の範囲外です")
            bounds[0] = min(bounds[0], lon)
            bounds[1] = min(bounds[1], lat)
            bounds[2] = max(bounds[2], lon)
            bounds[3] = max(bounds[3], lat)
            return
        for child in value:
            visit(child)

    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
            raise ValueError("境界GeoJSON featureにgeometryがありません")
        visit(feature["geometry"].get("coordinates"))
    if not all(value != float("inf") and value != float("-inf") for value in bounds):
        raise ValueError("境界GeoJSONから座標を取得できません")
    west, south, east, north = bounds
    if west >= east or south >= north:
        raise ValueError("境界GeoJSONの範囲が不正です")
    return [round(value, 7) for value in bounds]


def catalog_url(bbox, feature_type="bldg"):
    west, south, east, north = bbox
    return (f"{CATALOG_BASE}/r:{west:.7f},{south:.7f},{east:.7f},{north:.7f}"
            f"?types={feature_type}")


def select_city_building_files(index, city_code, year):
    cities = index.get("cities")
    if not isinstance(cities, list):
        raise ValueError("PLATEAU catalogにcities配列がありません")
    matches = [city for city in cities
               if city.get("cityCode") == city_code and city.get("year") == year]
    if len(matches) != 1:
        raise ValueError(f"PLATEAU catalogで市コード{city_code}・年度{year}を一意に特定できません")
    files = matches[0].get("files", {}).get("bldg")
    if not isinstance(files, list):
        raise ValueError("PLATEAU catalogにfiles.bldg配列がありません")
    selected = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("PLATEAU building catalog entryが不正です")
        url = item.get("url", "")
        if not official_bldg_url(url):
            raise ValueError(f"公式PLATEAU building GML以外のURLを拒否しました: {url}")
        lod1 = item.get("lod1")
        size = item.get("fileSize")
        if not isinstance(lod1, int) or lod1 < 0:
            raise ValueError("PLATEAU building catalogのLOD1件数が不正です")
        if not isinstance(size, int) or size <= 0:
            raise ValueError("PLATEAU building catalogのfileSizeが不正です")
        if lod1 == 0:
            continue
        selected.append({"filename": Path(url.split("?", 1)[0]).name,
                         "mesh_code": item.get("code"), "url": url,
                         "file_size": size, "lod1_features": lod1,
                         "max_lod": item.get("maxLod")})
    if not selected:
        raise ValueError("対象区域にLOD1建物ファイルがありません")
    return selected


def make_plan(index, catalog_bytes, bbox, boundary_metadata, city_code="07201", year=2025):
    files = select_city_building_files(index, city_code, year)
    total_bytes = sum(item["file_size"] for item in files)
    total_lod1 = sum(item["lod1_features"] for item in files)
    status = "requires_operator_approval" if total_bytes > REVIEW_THRESHOLD_BYTES else "metadata_ready"
    return {
        "schema": "therabby.geoengine.plateau.citywide-preflight.v0.1",
        "status": status,
        "downloads_performed": False,
        "municipality_code": city_code,
        "dataset_year": year,
        "boundary_source": boundary_metadata.get("source"),
        "boundary_sha256": boundary_metadata.get("source_sha256"),
        "boundary_bbox_wgs84": bbox,
        "catalog_url": catalog_url(bbox),
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "file_count": len(files),
        "lod1_feature_count": total_lod1,
        "total_file_size_bytes": total_bytes,
        "operator_review_threshold_bytes": REVIEW_THRESHOLD_BYTES,
        "attribution": "Project PLATEAU / Fukushima City; verify dataset-specific license before redistribution",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }


def fetch_catalog(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "TherabbyGeoEngine/0.1 citywide metadata preflight",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise RuntimeError(f"PLATEAU catalog HTTP {response.status}")
            raw = response.read(MAX_CATALOG_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"PLATEAU catalog API error: {exc}") from exc
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError("PLATEAU catalog response exceeds 15 MB preflight cap")
    return raw, json.loads(raw)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_download_plan(plan, approved_over_1gb=False):
    files = plan.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("PLATEAU preflight plan has no files")
    total = 0
    seen = set()
    for item in files:
        name = item.get("filename", "")
        parsed = urllib.parse.urlsplit(item.get("url", ""))
        if not official_bldg_url(item.get("url", "")) or Path(parsed.path).name != name:
            raise ValueError(f"Unsafe PLATEAU building source entry: {name}")
        if name in seen:
            raise ValueError(f"Duplicate PLATEAU filename in plan: {name}")
        seen.add(name)
        size = item.get("file_size")
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"Invalid expected size for {name}")
        total += size
    if total != plan.get("total_file_size_bytes") or len(files) != plan.get("file_count"):
        raise ValueError("PLATEAU preflight plan totals do not match file list")
    if total > REVIEW_THRESHOLD_BYTES and not approved_over_1gb:
        raise PermissionError("PLATEAU data exceeds 1 GB; pass --approve-over-1gb after operator approval")
    if total > 2_000_000_000:
        raise ValueError("Preflight total exceeds the approved 2.0 GB maximum")
    return total


def download_one(item, out_dir):
    name = item["filename"]
    expected = item["file_size"]
    dest = out_dir / name
    if dest.exists():
        if dest.stat().st_size != expected:
            raise ValueError(f"Existing source size mismatch; refusing to overwrite: {dest}")
        with dest.open("rb") as source:
            prefix = source.read(65536)
        if b"CityModel" not in prefix:
            raise ValueError(f"Existing file is not CityGML; refusing to reuse: {dest}")
        return {**item, "sha256": sha256_file(dest), "status": "reused_existing"}

    part = dest.with_name(dest.name + ".part")
    part.unlink(missing_ok=True)
    request = urllib.request.Request(item["url"], headers={
        "User-Agent": "TherabbyGeoEngine/0.1 citywide PLATEAU source download",
        "Accept": "application/gml+xml, application/xml, */*",
    })
    for attempt in range(3):
        digest = hashlib.sha256()
        total = 0
        try:
            with urllib.request.urlopen(request, timeout=180) as response, part.open("wb") as output:
                declared = response.headers.get("Content-Length")
                if declared and int(declared) != expected:
                    raise ValueError(f"Content-Length differs from catalog for {name}: {declared} != {expected}")
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > expected:
                        raise ValueError(f"Downloaded file exceeds catalog size: {name}")
                    output.write(block)
                    digest.update(block)
            if total != expected:
                raise ValueError(f"Downloaded file size differs from catalog for {name}: {total} != {expected}")
            with part.open("rb") as source:
                prefix = source.read(65536)
            if b"CityModel" not in prefix:
                raise ValueError(f"Downloaded file is not CityGML: {name}")
            part.replace(dest)
            return {**item, "sha256": digest.hexdigest(), "status": "downloaded"}
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            part.unlink(missing_ok=True)
            if attempt == 2:
                raise RuntimeError(f"PLATEAU download failed after retries for {name}: {exc}") from exc
            time.sleep(2 ** attempt)
        except Exception:
            part.unlink(missing_ok=True)
            raise
    raise RuntimeError(f"PLATEAU download failed: {name}")


def download_plan(plan, out_dir, approved_over_1gb=False, max_workers=2):
    total = validate_download_plan(plan, approved_over_1gb)
    if not 1 <= max_workers <= 4:
        raise ValueError("--max-workers must be between 1 and 4")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = out_dir / "source_manifest.json"
    completed = {}
    common = {
        "schema": "therabby.geoengine.source.plateau-citywide.v0.1",
        "municipality_code": plan["municipality_code"],
        "dataset_year": plan["dataset_year"],
        "source_catalog_url": plan["catalog_url"],
        "catalog_sha256": plan["catalog_sha256"],
        "boundary_sha256": plan.get("boundary_sha256"),
        "total_planned_bytes": total,
        "operator_approved_over_1gb": bool(approved_over_1gb),
        "download_started_utc": datetime.now(timezone.utc).isoformat(),
        "attribution": plan["attribution"],
    }

    def save_checkpoint(final=False):
        payload = {**common, "status": "complete" if final else "downloading",
                   "completed_files": len(completed), "completed_bytes": sum(f["file_size"] for f in completed.values()),
                   "files": [completed[name] for name in sorted(completed)]}
        temp = checkpoint.with_suffix(".json.tmp")
        write_json(temp, payload)
        temp.replace(checkpoint)

    todo = []
    for item in plan["files"]:
        dest = out_dir / item["filename"]
        if dest.exists():
            completed[item["filename"]] = download_one(item, out_dir)
        else:
            todo.append(item)
    save_checkpoint()
    if todo:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(download_one, item, out_dir): item for item in todo}
            for future in as_completed(futures):
                result = future.result()
                completed[result["filename"]] = result
                save_checkpoint()
                print(f"PLATEAU {len(completed)}/{len(plan['files'])}: {result['filename']} "
                      f"({sum(f['file_size'] for f in completed.values()):,}/{total:,} bytes)", flush=True)
    if len(completed) != len(plan["files"]) or sum(item["file_size"] for item in completed.values()) != total:
        raise RuntimeError("Downloaded PLATEAU files do not match the approved plan")
    save_checkpoint(final=True)
    return checkpoint


def main(argv=None):
    parser = argparse.ArgumentParser(description="福島市全域PLATEAU建物データの容量調査（GML未取得）")
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--boundary-metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--index-file", type=Path, help="保存済みcatalog JSONを使う")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--city-code", default="07201")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--download", action="store_true", help="preflight planの建物GML本体を取得")
    parser.add_argument("--plan-file", type=Path, default=DEFAULT_OUTPUT, help="--downloadで使う容量調査JSON")
    parser.add_argument("--download-dir", type=Path, default=ROOT / "data/raw/plateau/fukushima_citywide_2025")
    parser.add_argument("--approve-over-1gb", action="store_true", help="1GB超の事前承認済みダウンロードを許可")
    parser.add_argument("--max-workers", type=int, default=2)
    args = parser.parse_args(argv)

    if args.download:
        plan = json.loads(args.plan_file.read_text(encoding="utf-8"))
        checkpoint = download_plan(plan, args.download_dir, args.approve_over_1gb, args.max_workers)
        print(f"Complete: {checkpoint}")
        return 0

    boundary = json.loads(args.boundary.read_text(encoding="utf-8"))
    metadata = json.loads(args.boundary_metadata.read_text(encoding="utf-8"))
    if metadata.get("status") != "official_2026" or metadata.get("municipality_code") != args.city_code:
        raise ValueError("公式2026境界と対象市コードが一致しません")
    bbox = bbox_from_geojson(boundary)
    url = catalog_url(bbox)
    if args.index_file:
        catalog_bytes = args.index_file.read_bytes()
        index = json.loads(catalog_bytes)
    else:
        catalog_bytes, index = fetch_catalog(url)
    plan = make_plan(index, catalog_bytes, bbox, metadata, args.city_code, args.year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, plan)
    print(f"PLATEAU citywide preflight: {plan['file_count']} files, "
          f"{plan['lod1_feature_count']} LOD1 features, {plan['total_file_size_bytes']:,} bytes")
    print(f"Status: {plan['status']} (metadata only; no GML downloaded)")
    print(f"Saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
