#!/usr/bin/env python3
"""Fetch only official PLATEAU road CityGML files intersecting a small AOI.

The catalog may return whole mesh files. The default 100 MB cap prevents an
unexpectedly broad download; DEM and other feature types are not requested.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib import parse, request

from geoengine import bbox_of, load_area, read_json, write_json

MAX_FILE_BYTES=25_000_000
MAX_TOTAL_BYTES=100_000_000


def catalog_url(area):
    south,west,north,east=bbox_of(area,margin=0)
    return ("https://api.plateauview.mlit.go.jp/datacatalog/citygml/"
            f"r:{west:.7f},{south:.7f},{east:.7f},{north:.7f}?types=tran")


def select_files(index,area):
    cities=index.get('cities')
    if not isinstance(cities,list):raise ValueError('PLATEAU catalog missing cities[]')
    matches=[city for city in cities if city.get('cityCode')==area.get('plateau_city_code')
             and city.get('year')==area.get('plateau_year')]
    if len(matches)!=1:raise ValueError('Expected exactly one Fukushima/year catalog entry')
    files=matches[0].get('files',{}).get('tran')
    if not isinstance(files,list) or not files:
        raise ValueError('No PLATEAU tran files for this area/year')
    selected=[]
    for item in files:
        url=item.get('url','')
        parts=parse.urlsplit(url)
        name=Path(parts.path).name
        if (parts.scheme!='https' or parts.netloc!='assets.cms.plateau.reearth.io'
                or not re.fullmatch(r'\d{8}_tran_\d+_op\.gml',name)):
            raise ValueError(f'Unexpected PLATEAU tran URL: {url}')
        size=item.get('fileSize')
        if not isinstance(size,int) or not 0<size<=MAX_FILE_BYTES:
            raise ValueError(f'PLATEAU tran file size invalid/exceeds cap: {name}')
        if not isinstance(item.get('maxLod'),int) or item['maxLod']<1:
            raise ValueError(f'PLATEAU tran has no LOD1: {name}')
        selected.append({'filename':name,'mesh_code':item.get('code'),
                         'url':url,'file_size':size,'max_lod':item['maxLod']})
    if sum(item['file_size'] for item in selected)>MAX_TOTAL_BYTES:
        raise ValueError('PLATEAU tran files exceed 100 MB default cap')
    return selected


def fetch_bytes(url,limit):
    req=request.Request(url,headers={'User-Agent':'TherabbyGeoEngine/0.1'})
    with request.urlopen(req,timeout=90) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError(f'Response exceeds {limit:,} byte cap')
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--area',default='config/fukushima_station_east_1km.json')
    parser.add_argument('--output-dir',default='data/raw/plateau/tran_1km')
    parser.add_argument('--index-file',help='Previously saved official catalog JSON')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    area=load_area(args.area)
    url=catalog_url(area)
    index=(read_json(args.index_file) if args.index_file else
           json.loads(fetch_bytes(url,2_000_000)))
    files=select_files(index,area)
    print(f'PLATEAU tran: {len(files)} files, {sum(f["file_size"] for f in files):,} bytes')
    if args.dry_run:
        for item in files:print('DRY RUN',item['file_size'],item['filename'])
        return
    root=Path(args.output_dir)
    root.mkdir(parents=True,exist_ok=True)
    write_json(root/'catalog.json',index)
    for item in files:
        path=root/item['filename']
        if not path.exists() or path.stat().st_size!=item['file_size']:
            data=fetch_bytes(item['url'],item['file_size'])
            if len(data)!=item['file_size']:
                raise ValueError(f'PLATEAU tran size mismatch: {path.name}')
            if b'<core:CityModel' not in data[:5000] and b'<CityModel' not in data[:5000]:
                raise ValueError(f'PLATEAU tran is not CityGML: {path.name}')
            pending=path.with_suffix('.part')
            pending.write_bytes(data)
            pending.replace(path)
        item['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        print('READY',path,item['file_size'])
    write_json(root/'source_manifest.json',{
        'schema':'therabby.geoengine.source.plateau-tran.v0.1',
        'catalog_url':url,'catalog_sha256':hashlib.sha256((root/'catalog.json').read_bytes()).hexdigest(),
        'fetched_at_utc':datetime.now(timezone.utc).isoformat(),
        'city_code':area['plateau_city_code'],'year':area['plateau_year'],
        'attribution':'Project PLATEAU / Fukushima City; check dataset-specific redistribution terms',
        'files':files})


if __name__=='__main__':main()
