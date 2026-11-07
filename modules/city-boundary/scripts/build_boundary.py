#!/usr/bin/env python3
"""Extract the real Fukushima City boundary from MLIT 2026 N03 Fukushima ZIP.

Install: pip install -r requirements.txt
Use: python scripts/build_boundary.py --download
  or python scripts/build_boundary.py --zip C:/Downloads/N03-20260101_07_GML.zip
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

SOURCE_URL = "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_07_GML.zip"
SOURCE_PAGE = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html"
ROOT = Path(__file__).resolve().parents[1]
CODE = "07201"


def extract_boundary(raw_zip: bytes, simplify_meters: float = 8.0, return_full: bool = False):
    try:
        import shapefile
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union, transform
        from pyproj import Transformer, Geod
    except ImportError as e:
        raise RuntimeError("pip install -r requirements.txt を実行してください") from e

    def try_read(zf):
        # 2026 MLIT N03 provides SHP inside the prefecture ZIP.
        names = zf.namelist()
        stem = next((n[:-4] for n in names if n.lower().endswith(".shp") and n[:-4]+".dbf" in names and n[:-4]+".shx" in names), None)
        if stem is None:
            raise ValueError("ZIP内に .shp / .shx / .dbf が見つかりません。2026年版N03福島県ZIPを指定してください")
        payload = dict(shp=io.BytesIO(zf.read(stem+".shp")), shx=io.BytesIO(zf.read(stem+".shx")), dbf=io.BytesIO(zf.read(stem+".dbf")))
        for enc in ("utf-8", "cp932"):
            try:
                with shapefile.Reader(**{k:io.BytesIO(v.getvalue()) for k,v in payload.items()}, encoding=enc) as sf:
                    keys = [f[0] for f in sf.fields[1:]]
                    if not {"N03_001", "N03_004"}.issubset(keys):
                        raise ValueError("N03属性列が不足しています")
                    geometries = []
                    for sr in sf.iterShapeRecords():
                        attr = dict(zip(keys, sr.record))
                        code = str(attr.get("N03_007", "")).strip()
                        if attr.get("N03_001") == "福島県" and (code in ("07201", "072010") or (not code and attr.get("N03_004") == "福島市")):
                            geometries.append(shape(sr.shape.__geo_interface__))
                    if not geometries:
                        raise ValueError("福島市 (07201) が見つかりません。N03_007を確認してください")
                    return geometries, stem, enc
            except UnicodeDecodeError:
                continue
        raise ValueError("属性ファイルのエンコーディングを判定できません")

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        geometries, stem, enc = try_read(zf)
    merged = unary_union(geometries)
    if not merged.is_valid:
        merged = merged.buffer(0)
    if merged.is_empty:
        raise ValueError("有効な境界ポリゴンがありません")
    # Compute simplification in a metric local CRS; do NOT simplify degrees.
    forward = Transformer.from_crs("EPSG:6668", "EPSG:6677", always_xy=True).transform  # JGD2011 geographic to Japan plane rectangular CRS zone IX
    backward = Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True).transform
    planar = transform(forward, merged)
    simplified = planar.simplify(simplify_meters, preserve_topology=True)
    if simplified.is_empty or not simplified.is_valid:
        raise ValueError("境界の簡略化に失敗しました")
    result_geom = transform(backward, simplified)
    full_geom = transform(Transformer.from_crs("EPSG:6668", "EPSG:4326", always_xy=True).transform, merged)
    if result_geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("期待しないジオメトリ種類: "+result_geom.geom_type)
    minx,miny,maxx,maxy = result_geom.bounds
    geod = Geod(ellps="GRS80")
    area_m2,_ = geod.geometry_area_perimeter(merged)
    area_km2 = abs(area_m2)/1e6
    if not (700 < area_km2 < 850 and 139 < minx < 141 and 37 < miny < 39):
        raise ValueError(f"市域の範囲・面積が想定外: {area_km2:.2f}km², {result_geom.bounds}")

    web_boundary = {
        "type":"FeatureCollection",
        "features":[{"type":"Feature", "properties":{"name":"福島市", "municipality_code":CODE, "source_year":2026, "data_status":"official_2026"}, "geometry":mapping(result_geom)}],
    }
    meta = {
        "name":"福島市", "municipality_code":CODE, "status":"official_2026", "source":"国土交通省 国土数値情報（行政区域データ）2026年版", "source_page":SOURCE_PAGE,
        "source_file":stem, "source_date":"2026-01-01", "source_license":"CC BY 4.0（原典と使用許諾条件を確認）",
        "source_sha256":hashlib.sha256(raw_zip).hexdigest(), "source_encoding":enc,
        "crs":"EPSG:4326", "original_crs":"JGD2011 EPSG:6668", "bbox":[round(v,7) for v in (minx,miny,maxx,maxy)],
        "area_km2_geodesic":round(area_km2,3), "component_count":len(geometries),
        "simplification_meters":simplify_meters, "generated_utc":datetime.now(timezone.utc).isoformat(),
        "attribution":"「国土数値情報（行政区域データ）」（国土交通省）を加工して作成",
    }
    if return_full:
        full_boundary = {"type":"FeatureCollection", "features":[{
            "type":"Feature", "properties":{"name":"福島市","municipality_code":CODE,"source_year":2026,"data_status":"official_2026","precision":"full"},
            "geometry":mapping(full_geom)}]}
        return web_boundary, meta, full_boundary
    return web_boundary, meta


def main():
    parser = argparse.ArgumentParser(description="福島市の2026年行政界抽出 → GeoJSON")
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--zip", type=Path, help="入手済みN03-20260101_07_GML.zip")
    group.add_argument("--download", action="store_true", help="国交省からダウンロード")
    parser.add_argument("--simplify-meters", type=float, default=8.0, help="表示向けの簡略化距離（メートル、0で無効）")
    parser.add_argument("--out", type=Path, default=ROOT/"data")
    args=parser.parse_args()
    if args.simplify_meters < 0 or args.simplify_meters > 300:
        parser.error("--simplify-meters は 0〜300m としてください")
    if args.zip:
        data=args.zip.read_bytes()
    else:
        request=urllib.request.Request(SOURCE_URL, headers={"User-Agent":"Therabby-GeoEngine/0.1 boundary-loader"})
        with urllib.request.urlopen(request, timeout=100) as response:
            data=response.read()
    boundary, meta, full_boundary=extract_boundary(data,args.simplify_meters, return_full=True)
    args.out.mkdir(parents=True,exist_ok=True)
    # Each file is atomically replaced. Keep originals untouched if extraction fails.
    for filename,payload in [("fukushima_city_boundary.geojson",boundary),("fukushima_city_boundary_full.geojson",full_boundary),("boundary_metadata.json",meta)]:
        dest=args.out/filename
        temporary=dest.with_name(dest.name+".tmp")
        temporary.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")), encoding="utf-8")
        temporary.replace(dest)
    # Keep the summary safe for the default Windows CP932 console encoding.
    print(f"OK: {meta['source']} / {meta['area_km2_geodesic']} km2 / {meta['component_count']} components")
    print("Saved to",args.out.resolve())

if __name__ == "__main__":
    main()
