#!/usr/bin/env python3
"""STEP 1-2 — extract OSM ways into local, tiled, provenance-aware GeoJSON.

Usage (PowerShell, in city-boundary folder):
  py scripts/build_roads.py --overpass-station
  py scripts/build_roads.py --pbf "C:\\Downloads\\tohoku-latest.osm.pbf"
  py scripts/build_roads.py --download-pbf   # 300MB+; explicit opt-in

Full city-wide output requires a region PBF, not a public Overpass API query.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import urllib.parse
import urllib.error
import urllib.request
import math
import uuid

try:
    from shapely.geometry import LineString, box, mapping, shape
    from shapely.ops import unary_union
except ImportError as exc:  # Give a useful message when the selected Python lacks dependencies.
    print(
        f"依存パッケージを読み込めません: {exc}. "
        "このPython環境で `py -m pip install -r requirements.txt` を実行してください。",
        file=sys.stderr,
        flush=True,
    )
    raise SystemExit(2) from exc

LOG = logging.getLogger('build_roads')

ROOT = Path(__file__).resolve().parents[1]
GEODATA = ROOT / 'data'
ROADS_DIR = GEODATA / 'roads'
GEOFABRIK = 'https://download.geofabrik.de/asia/japan/tohoku-latest.osm.pbf'
OVERPASS = 'https://overpass-api.de/api/interpreter'
STEP_DEG = 0.025  # fixed WGS84 grid; approx 2.2km x 2.8km in Fukushima City
SUPPORTED = {
 'motorway','motorway_link','trunk','trunk_link','primary','primary_link',
 'secondary','secondary_link','tertiary','tertiary_link','residential',
 'unclassified','service','living_street','pedestrian','footway',
 'path','cycleway','steps','track','road'
}
ROAD_CLASSES = {
 'motorway':'major','motorway_link':'major','trunk':'major','trunk_link':'major',
 'primary':'major','primary_link':'major','secondary':'major','secondary_link':'major',
 'tertiary':'major','tertiary_link':'major',
 'residential':'local','unclassified':'local','service':'local',
 'living_street':'local','road':'local',
 'footway':'walk','path':'walk','pedestrian':'walk',
 'steps':'walk','track':'walk','cycleway':'walk'
}

def read_boundary(path: Path | None = None):
    full = GEODATA / 'fukushima_city_boundary_full.geojson'
    chosen = path or (full if full.exists() else GEODATA / 'fukushima_city_boundary.geojson')
    fc=json.loads(chosen.read_text(encoding='utf-8'))
    if fc.get('type')!='FeatureCollection' or not fc.get('features'):
        raise ValueError('福島市の境界GeoJSONがありません')
    for f in fc['features']:
        if f.get('properties',{}).get('municipality_code') not in (None,'07201'):
            raise ValueError('福島市(07201)以外の境界が含まれています')
    geom=unary_union([shape(f['geometry']) for f in fc['features']])
    if geom.is_empty or not geom.is_valid:
        raise ValueError('境界の形状が不正です')
    if not 139<geom.bounds[0]<142 or not 36<geom.bounds[1]<40:
        raise ValueError('境界の座標が福島市付近ではありません')
    meta_path=GEODATA/'boundary_metadata.json'
    meta=json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
    authoritative = (chosen.resolve()==full.resolve() and meta.get('status')=='official_2026')
    return geom, chosen, 'official_2026' if authoritative else 'preview'

def tile_key(lon,lat):
    return int(math.floor((lon+1e-11)/STEP_DEG)),int(math.floor((lat+1e-11)/STEP_DEG))

def segment_lines(geometry):
    if geometry.is_empty: return
    if geometry.geom_type=='LineString':
        if len(geometry.coords)>1 and geometry.length>1e-7: yield geometry
    elif geometry.geom_type in ('MultiLineString','GeometryCollection'):
        for child in geometry.geoms: yield from segment_lines(child)

def tags_to_props(way_id,tags):
    highway = str(tags.get('highway',''))
    if highway not in SUPPORTED: return None
    return {
        'osm_id':str(way_id),'highway':highway,
        'road_class':ROAD_CLASSES[highway],
        'name':str(tags.get('name',''))[:180],
        'ref':str(tags.get('ref',''))[:80],
        'oneway':str(tags.get('oneway',''))[:24],
        'maxspeed':str(tags.get('maxspeed',''))[:40],
        'lanes':str(tags.get('lanes',''))[:24],
        'bridge':str(tags.get('bridge',''))[:24],
        'tunnel':str(tags.get('tunnel',''))[:24],
        'surface':str(tags.get('surface',''))[:40],
        'sidewalk':str(tags.get('sidewalk',''))[:40],
        'access':str(tags.get('access',''))[:40],
    }

class Collector:
    def __init__(self,boundary):
        self.boundary=boundary
        self.city_bbox=box(*boundary.bounds)
        self.grid=defaultdict(list)
        self.total_ways=0
        self.kept_ways=0
        self.way_types=Counter()
        self.segments=0

    def add_way(self,way_id,tags,lonlats):
        self.total_ways += 1
        props=tags_to_props(way_id,tags)
        if not props or len(lonlats)<2:return
        try: line=LineString(lonlats)
        except (ValueError,TypeError): return
        if not line.intersects(self.city_bbox): return
        clipped=line.intersection(self.boundary)
        if clipped.is_empty: return
        retained=False
        for segment in segment_lines(clipped):
            west,south,east,north=segment.bounds
            gx0,gy0=tile_key(west,south)
            gx1,gy1=tile_key(east,north)
            for gx in range(gx0,gx1+1):
                for gy in range(gy0,gy1+1):
                    tilebox=box(gx*STEP_DEG,gy*STEP_DEG,(gx+1)*STEP_DEG,(gy+1)*STEP_DEG)
                    if not segment.intersects(tilebox): continue
                    for piece in segment_lines(segment.intersection(tilebox)):
                        # Preserve OSM polyline direction. Note clipping may not guarantee
                        # original traversal order: not a routing graph.
                        self.grid[(gx,gy)].append({'type':'Feature','geometry':mapping(piece),'properties':props})
                        self.segments+=1
                        retained=True
        if retained:
            self.kept_ways+=1
            self.way_types[props['highway']]+=1

    def write(self,out: Path,source,source_detail,boundary_file,boundary_quality,source_acquired_utc=None,tile_prefix='',source_metadata=None):
        out.mkdir(parents=True,exist_ok=True)
        tiles=[]
        for gx,gy in sorted(self.grid):
            items=self.grid[(gx,gy)]
            name=f'{gx}_{gy}.geojson'
            data={'type':'FeatureCollection','features':items}
            (out/name).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            tile_file=f'{tile_prefix}/{name}' if tile_prefix else name
            tiles.append({'id':f'{gx}_{gy}','file':tile_file,'bbox':[round(gx*STEP_DEG,8),round(gy*STEP_DEG,8),round((gx+1)*STEP_DEG,8),round((gy+1)*STEP_DEG,8)],'segments':len(items)})
        manifest={
            'schema':'therabby.geodata.roads.v1',
            'status':'ready' if tiles else 'empty',
            'coverage':'station_test_area' if source=='overpass_station' else ('municipality' if source=='geofabrik_pbf' else ('local_json_import' if source in ('osm_api_json','overpass_json') else 'unspecified_test_data')),
            'source':source,
            'source_detail':source_detail,
            'source_acquired_utc':source_acquired_utc,
            'source_metadata':source_metadata or {},
            'source_page':'https://www.openstreetmap.org/copyright',
            'license':'ODbL 1.0',
            'attribution':'© OpenStreetMap contributors',
            'generated_utc':datetime.now(timezone.utc).isoformat(),
            'boundary_file':boundary_file,
            'boundary_quality':boundary_quality,
            'warning':'暫定境界を用いて抽出しました。2026年正式N03での再抽出を推奨します。' if boundary_quality!='official_2026' else '',
            'coordinate_system':'EPSG:4326',
            'tile_step_deg':STEP_DEG,
            'way_count':self.kept_ways,
            'input_way_count':self.total_ways,
            'segment_count':self.segments,
            'classes':dict(self.way_types),
            'tiles':tiles,
        }
        (out/'index.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        return manifest

def process_overpass_data(data,collector):
    if data.get('elements') is None: raise ValueError('Overpass JSON の elements がありません')
    for e in data['elements']:
        if e.get('type')!='way' or not isinstance(e.get('geometry'),list): continue
        coords=[(p['lon'],p['lat']) for p in e['geometry'] if 'lon' in p and 'lat' in p]
        collector.add_way(e.get('id',''),e.get('tags',{}),coords)

def get_station_data(endpoint=OVERPASS):
    # One narrowly scoped interactive test, not a city-wide extraction.
    west,south,east,north=140.438,37.741,140.484,37.774
    q=f'[out:json][timeout:60];way["highway"]({south},{west},{north},{east});out tags geom;'
    req=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':q}).encode(),headers={'User-Agent':'TherabbyGeoEngine/0.1.2 (personal research; see https://www.openstreetmap.org/copyright)'})
    LOG.info('Overpassへ福島駅周辺の道路を問い合わせます: %s', endpoint)
    LOG.info('取得範囲: west=%s south=%s east=%s north=%s', west, south, east, north)
    try:
        with urllib.request.urlopen(req,timeout=90) as reply:
            if reply.status!=200:
                raise RuntimeError(f'Overpass HTTPエラー: status={reply.status} (endpoint={endpoint})')
            data=json.load(reply)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f'外部APIエラー: Overpass HTTP {exc.code} {exc.reason} '
            f'(endpoint={endpoint})。時間をおいて再試行するか、保存済みJSON/PBFを使用してください。'
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
        reason=getattr(exc,'reason',exc)
        raise RuntimeError(
            f'外部通信エラー: Overpassへ接続できません ({reason}; endpoint={endpoint})。'
            'ネットワーク/DNS/プロキシまたはAPI到達性を確認してください。'
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'外部API応答エラー: OverpassがJSON以外の応答を返しました ({exc}; endpoint={endpoint})') from exc
    if not isinstance(data,dict) or not isinstance(data.get('elements'),list):
        raise RuntimeError('外部API応答エラー: Overpass JSONにelements配列がありません')
    LOG.info('Overpass応答を受信しました: %s elements', len(data['elements']))
    return data

def download_pbf(target:Path):
    target.parent.mkdir(parents=True,exist_ok=True)
    print(f'Geofabrik東北PBF取得（約300MB）：{GEOFABRIK}',flush=True)
    tmp=target.with_suffix('.partial')
    request=urllib.request.Request(GEOFABRIK,headers={'User-Agent':'TherabbyGeoEngine/0.1.2'})
    try:
        with urllib.request.urlopen(request,timeout=90) as src,open(tmp,'wb') as dst:
            size=int(src.headers.get('Content-Length') or 0)
            if size>800*1024*1024:raise RuntimeError('ファイルサイズが想定より大きいため中断しました')
            total=0
            while True:
                block=src.read(2*1024*1024)
                if not block:break
                total+=len(block)
                if total>800*1024*1024:raise RuntimeError('上限800MBを超えました')
                dst.write(block)
                if total%(32*1024*1024)<2*1024*1024:print(f'  取得済み: {total//(1024*1024)} MB',flush=True)
        if total<10*1024*1024:raise RuntimeError('PBFが小さすぎます（ダウンロードエラーの可能性）')
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return target

def process_pbf(path,collector):
    if not path.is_file():raise FileNotFoundError(f'東北PBFが見つかりません: {path}')
    try:import osmium
    except ImportError as exc:raise RuntimeError('PBF処理には py -m pip install osmium が必要です') from exc
    class Extractor(osmium.SimpleHandler):
        def way(self,w):
            if 'highway' not in w.tags:return
            tags=dict(w.tags)
            if tags['highway'] not in SUPPORTED:return
            try:coords=[(n.lon,n.lat) for n in w.nodes if n.location.valid()]
            except Exception:return
            # Missing nodes are rejected: otherwise a fabricated straight segment forms.
            if len(coords)!=len(w.nodes):return
            collector.add_way(w.id,tags,coords)
    print('PBF読込・境界クリップ・タイル化を実行中…',flush=True)
    Extractor().apply_file(str(path),locations=True,idx='flex_mem')

def inspect_pbf_source(path:Path):
    """Return reproducible source metadata without treating the file mtime as its data date."""
    try:import osmium
    except ImportError as exc:raise RuntimeError('PBF処理には py -m pip install osmium が必要です') from exc
    path=Path(path)
    reader=osmium.io.Reader(str(path))
    try:
        header=reader.header()
        snapshot=header.get('osmosis_replication_timestamp') or None
    finally:
        reader.close()
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            digest.update(block)
    modified=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()
    return {'snapshot_timestamp_utc':snapshot,'file_mtime_utc':modified,'sha256':digest.hexdigest()}

def main(argv=None):
    p=argparse.ArgumentParser(description='Therabby GeoEngine STEP 1-2 / OSM Road Import')
    src=p.add_mutually_exclusive_group(required=True)
    src.add_argument('--overpass-station',action='store_true',help='福島駅付近のみ実道路の小範囲試験取得')
    src.add_argument('--overpass-json','--osm-json',dest='overpass_json',type=Path,help='保存済みOSM/Overpass JSONを利用')
    src.add_argument('--pbf',type=Path,help='Geofabrikの東北 .osm.pbf をローカル読込')
    src.add_argument('--download-pbf',action='store_true',help='300MB超の東北PBFをダウンロードして市全域を抽出')
    p.add_argument('--endpoint',default=OVERPASS,help=f'Overpass API endpoint (default: {OVERPASS})')
    p.add_argument('--boundary',type=Path,help='カスタム行政境界GeoJSON（通常省略）')
    p.add_argument('--out',type=Path,default=ROADS_DIR,help='道路タイル出力フォルダ')
    args=p.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',datefmt='%H:%M:%S',stream=sys.stdout)
    mode='Overpass station test' if args.overpass_station else ('saved OSM JSON' if args.overpass_json else 'Geofabrik PBF')
    LOG.info('STEP 1-2 道路生成を開始: mode=%s; Python=%s; version=%s',mode,sys.executable,sys.version.split()[0])
    try:
        region,boundary_file,boundary_quality=read_boundary(args.boundary)
        LOG.info('境界を読込: %s (%s)',boundary_file,boundary_quality)
        if boundary_quality!='official_2026':LOG.warning('正式N03未導入。暫定市域で道路をクリップします。')
        collector=Collector(region)
        source_acquired_utc=None
        source_metadata=None
        if args.overpass_station:
            source_data=get_station_data(args.endpoint)
            source_acquired_utc=datetime.now(timezone.utc).isoformat()
            process_overpass_data(source_data,collector)
            source='overpass_station';source_detail='OpenStreetMap Overpass API, Fukushima Station ~4km test'
        elif args.overpass_json:
            LOG.info('保存済みOSM JSONを読込: %s',args.overpass_json)
            source_data=json.loads(args.overpass_json.read_text(encoding='utf-8'))
            process_overpass_data(source_data,collector)
            source_url=str(source_data.get('source_url','')) if isinstance(source_data,dict) else ''
            osm_meta=source_data.get('osm3s') if isinstance(source_data,dict) else None
            source_acquired_utc=osm_meta.get('timestamp_osm_base') if isinstance(osm_meta,dict) else None
            source='osm_api_json' if 'api.openstreetmap.org' in source_url else 'overpass_json'
            source_detail=f"{source_url or 'source URL not recorded'} (local file: {args.overpass_json})"
        else:
            pbf=download_pbf(Path.home()/'GeoEngineSourceCache'/'tohoku-latest.osm.pbf') if args.download_pbf else args.pbf
            LOG.info('ローカルPBFを処理: %s',pbf)
            source_metadata=inspect_pbf_source(pbf)
            process_pbf(pbf,collector)
            source='geofabrik_pbf';source_detail=f'{GEOFABRIK} (source file: {pbf.name})'
        LOG.info('抽出結果: 入力way=%s、福島市内way=%s、出力線分=%s',collector.total_ways,collector.kept_ways,collector.segments)
        if collector.kept_ways==0:raise RuntimeError('道路が1件も抽出されませんでした。既存の道路データは保持します。')
        target=args.out.resolve();target.mkdir(parents=True,exist_ok=True)
        generation=f"tiles-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        with tempfile.TemporaryDirectory(dir=target.parent,prefix='.roads-next-') as tmp:
            staging=Path(tmp)/generation
            manifest=collector.write(staging,source,source_detail,boundary_file.name,boundary_quality,
                                     source_acquired_utc,tile_prefix=generation,source_metadata=source_metadata)
            # Keep each tile generation immutable. Only the small index pointer is
            # replaced, so active HTTP readers never block a directory rename.
            (staging/'index.json').unlink()
            staged_index=Path(tmp)/'index.json'
            staged_index.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            shutil.move(str(staging),str(target/generation))
            os.replace(staged_index,target/'index.json')
        print(json.dumps({k:manifest[k] for k in ('source','coverage','boundary_quality','way_count','segment_count')},ensure_ascii=False,indent=2))
        LOG.info('完了: %s/index.json。HTTPサーバーでブラウザを更新してください。',target)
        return 0
    except Exception as exc:
        LOG.error('道路生成に失敗しました: %s: %s',type(exc).__name__,exc)
        if isinstance(exc,(OSError,ValueError,RuntimeError)):
            return 1
        LOG.exception('内部エラーの詳細')
        return 1

if __name__=='__main__':raise SystemExit(main())
