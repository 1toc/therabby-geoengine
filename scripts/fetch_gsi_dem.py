#!/usr/bin/env python3
"""Fetch a small official GSI DEM5A PNG subset for Fukushima station east."""
import argparse
import hashlib
from datetime import datetime, timezone
from math import floor
from pathlib import Path
from urllib import request

from fetch_ortho import world_pixel
from geoengine import bbox_of, load_area, write_json

ZOOM=15
MAX_TILES=16
MAX_TILE_BYTES=300_000


def tile_ids(area):
    south,west,north,east=bbox_of(area,margin=0)
    x0,y0=world_pixel(north,west,ZOOM)
    x1,y1=world_pixel(south,east,ZOOM)
    result=[(x,y) for y in range(floor(y0/256),floor(y1/256)+1)
                  for x in range(floor(x0/256),floor(x1/256)+1)]
    if not result or len(result)>MAX_TILES:
        raise ValueError('GSI DEM subset exceeds 16-tile cap; reduce area')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--area',default='config/fukushima_station_east_1km.json')
    parser.add_argument('--output-dir',default='data/raw/gsi_dem5a_1km')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    area=load_area(args.area)
    if area.get('projection')!='JGD2011_JPRCS_IX_GRS80':
        raise ValueError('GSI DEM subset requires JGD2011_JPRCS_IX_GRS80')
    ids=tile_ids(area)
    root=Path(args.output_dir)
    if not args.dry_run:root.mkdir(parents=True,exist_ok=True)
    entries=[]
    for x,y in ids:
        url=f'https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{ZOOM}/{x}/{y}.png'
        name=f'dem5a_{ZOOM}_{x}_{y}.png'
        path=root/name
        if args.dry_run:
            print('DRY RUN',url)
            continue
        if not path.exists():
            req=request.Request(url,headers={'User-Agent':'TherabbyGeoEngine/0.1'})
            with request.urlopen(req,timeout=30) as response:
                data=response.read(MAX_TILE_BYTES+1)
            if len(data)>MAX_TILE_BYTES or not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError(f'Invalid/oversized GSI DEM5A PNG: {url}')
            path.write_bytes(data)
        data=path.read_bytes()
        if len(data)>MAX_TILE_BYTES or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError(f'Invalid cached GSI DEM5A PNG: {path}')
        entries.append({'x':x,'y':y,'z':ZOOM,'file':name,'url':url,
                        'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        print('READY',path,len(data))
    if not args.dry_run:
        write_json(root/'source_manifest.json',{
            'schema':'therabby.geoengine.source.gsi-dem5a.v0.1',
            'area_id':area['id'],'source':'GSI DEM5A PNG elevation tile',
            'vertical_datum':'T.P. (Tokyo Peil), ground terrain elevation',
            'height_quality':'DEM5A interpolated ground height; structures excluded',
            'fetched_at_utc':datetime.now(timezone.utc).isoformat(),
            'attribution':'Geospatial Information Authority of Japan',
            'tiles':entries})


if __name__=='__main__':main()
