#!/usr/bin/env python3
"""Decode the bundled *preview* city geometry from Geolonia (unknown vintage)."""
import base64
import json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]

def main():
    buf=base64.b64decode((ROOT/'data'/'preview-geolonia.b64').read_text().strip())
    numbers=[]; val=0; shift=0
    for b in buf:
        val |= (b&127)<<shift
        if b&128:shift+=7
        else:
            numbers.append(val//2 if val%2==0 else -(val//2)-1)
            val=0;shift=0
    assert shift==0 and len(numbers)%2==0
    coords=[]; last=[0,0]
    for i in range(0,len(numbers),2):
        last[0]+=numbers[i];last[1]+=numbers[i+1]
        coords.append([last[0]/1e6,last[1]/1e6])
    assert len(coords)==753 and coords[0]==coords[-1]
    gj={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'福島市','municipality_code':'07201','data_status':'preview','source_year':None},'geometry':{'type':'Polygon','coordinates':[coords]}}]}
    xs=[c[0] for c in coords];ys=[c[1] for c in coords]
    meta={'name':'福島市','municipality_code':'07201','status':'preview','source':'Geolonia Japanese Admins（国土数値情報の加工物）／収録年代未確認','source_page':'https://github.com/geolonia/japanese-admins','source_date':None,'source_license':'原典：国土数値情報、公開条件は要確認','crs':'EPSG:4326','bbox':[min(xs),min(ys),max(xs),max(ys)],'vertex_count':len(coords),'area_km2_geodesic':None,'simplification_meters':30,'attribution':'「国土数値情報（行政区域データ）」（国土交通省）を加工したGeoloniaの資料を再加工','warning':'暫定プレビューです。正式版は2026年N03から生成してください。'}
    for file,obj in [('fukushima_city_boundary.geojson',gj),('boundary_metadata.json',meta)]:
        (ROOT/'data'/file).write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('OK preview:',len(coords),'boundary vertices; bbox',meta['bbox'])
if __name__=='__main__':main()
