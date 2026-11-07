#!/usr/bin/env python3
"""Extract Fukushima's official PLATEAU LOD1 road extent for the 1km AOI.

LOD1 Road polygons include the road corridor, not a surveyed carriageway or
lane layout. EPSG:6697 zero Z is a placeholder and is never used as elevation.
"""
import argparse
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from geoengine import load_area, read_json, write_json, xy_of
from road_tiles import clip_polygon_rect

CORE='http://www.opengis.net/citygml/2.0'
TRAN='http://www.opengis.net/citygml/transportation/2.0'
GML='http://www.opengis.net/gml'
EPSG6697='http://www.opengis.net/def/crs/EPSG/0/6697'


def parse_poslist(element,area):
    if element is None or not element.text:
        raise ValueError('PLATEAU Road polygon has no gml:posList')
    dimension=element.get('srsDimension')
    if dimension not in (None,'3'):
        raise ValueError(f'Unsupported PLATEAU Road coordinate dimension: {dimension}')
    values=[float(value) for value in element.text.split()]
    if len(values)<12 or len(values)%3:
        raise ValueError('PLATEAU Road posList must be 3D lat/lon/height triples')
    ring=[]
    for lat,lon,height in zip(values[0::3],values[1::3],values[2::3]):
        if abs(height)>1e-6:
            raise ValueError(f'PLATEAU Road nonzero vertical coordinate {height}; datum handling required')
        x,z=xy_of(lat,lon,area)
        point=[round(x,3),round(z,3)]
        if not ring or point!=ring[-1]:ring.append(point)
    if len(ring)>1 and ring[0]==ring[-1]:ring.pop()
    return ring


def extract_roads(source,area,bounds):
    root=ET.parse(source).getroot()
    envelope=root.find(f'{{{GML}}}boundedBy/{{{GML}}}Envelope')
    if envelope is None or envelope.get('srsName')!=EPSG6697 or envelope.get('srsDimension')!='3':
        raise ValueError(f'{source}: unsupported/missing EPSG:6697 3D envelope')
    result=[]
    for road in root.iter(f'{{{TRAN}}}Road'):
        road_id=road.get(f'{{{GML}}}id')
        if not road_id:raise ValueError(f'{source}: Road missing gml:id')
        lod=road.find(f'{{{TRAN}}}lod1MultiSurface')
        if lod is None:continue
        road_class=road.findtext(f'{{{TRAN}}}class')
        function=road.findtext(f'{{{TRAN}}}function')
        for index,polygon in enumerate(lod.iter(f'{{{GML}}}Polygon')):
            srs=polygon.get('srsName')
            if srs and srs!=EPSG6697:
                raise ValueError(f'{source}: unsupported Road polygon CRS {srs}')
            exterior=polygon.find(f'{{{GML}}}exterior/{{{GML}}}LinearRing/{{{GML}}}posList')
            ring=parse_poslist(exterior,area)
            if len(ring)<3:continue
            min_x=min(p[0] for p in ring);max_x=max(p[0] for p in ring)
            min_z=min(p[1] for p in ring);max_z=max(p[1] for p in ring)
            if max_x<bounds[0] or min_x>bounds[2] or max_z<bounds[1] or min_z>bounds[3]:
                continue
            if polygon.find(f'{{{GML}}}interior') is not None:
                raise ValueError(f'{source}: Road polygon {road_id} has an unsupported interior ring')
            clipped=clip_polygon_rect(ring,bounds)
            if not clipped:continue
            result.append({'id':f'{road_id}:polygon:{index}','source_road_id':road_id,
                'polygon':clipped,'source_file':source.name,
                'road_class_code':road_class,'function_code':function,
                'source':'PLATEAU CityGML transportation Road LOD1',
                'geometry_quality':'official-road-extent-not-carriageway',
                'height_m':None,'height_quality':'zero-placeholder-not-surveyed',
                'drivable':None,'legal_access':'not-verified'})
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--area',default='config/fukushima_station_east_1km.json')
    parser.add_argument('--source-dir',default='data/raw/plateau/tran_1km')
    parser.add_argument('--output',default='dist/real/fukushima-east-1km/plateau_road_extent.json')
    args=parser.parse_args()
    area=load_area(args.area)
    if area.get('projection')!='JGD2011_JPRCS_IX_GRS80':
        raise ValueError('PLATEAU Road export requires JGD2011_JPRCS_IX_GRS80')
    root=Path(args.source_dir)
    source_manifest=read_json(root/'source_manifest.json')
    if source_manifest['city_code']!=area['plateau_city_code'] or source_manifest['year']!=area['plateau_year']:
        raise ValueError('PLATEAU Road source city/year mismatch')
    half=area['half_size_m'];bounds=[-half,-half,half,half]
    roads=[];sources=[]
    for item in source_manifest['files']:
        path=root/item['filename']
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=item['sha256']:
            raise ValueError(f'PLATEAU Road source hash mismatch: {path}')
        roads.extend(extract_roads(path,area,bounds))
        sources.append({'file':item['filename'],'sha256':digest,'bytes':path.stat().st_size})
    ids=[road['id'] for road in roads]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate PLATEAU Road polygon IDs')
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    write_json(output,{'schema':'therabby.geoengine.plateau-road-extent.v0.1',
        'area_id':area['id'],'coordinate_system':{
            'horizontal':'JGD2011_JPRCS_IX_GRS80','axes':'X east / Z south','unit':'metre',
            'vertical':'not-provided; source zero placeholder'},
        'bounds':bounds,'roads':roads,'source_files':sources,
        'attribution':'Project PLATEAU / Fukushima City; dataset-specific terms apply',
        'limitations':'LOD1 road extent includes non-carriageway space; no lane, legal access or elevation'})
    print(f'PLATEAU Road LOD1: {len(roads)} polygons in {bounds} -> {output}')


if __name__=='__main__':main()
