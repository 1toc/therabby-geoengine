#!/usr/bin/env python3
"""Sample the preview route against road candidates, official extents and DEM.

The report checks geographic coverage only. It never certifies a vehicle
collision mesh, legal direction, lanes or clinical driving suitability.
"""
import argparse
import hashlib
import math
from pathlib import Path

from geoengine import read_json, write_json
from road_tiles import point_in_polygon
from terrain_grid import height_at


def percentile(values,fraction):
    if not values:return None
    ordered=sorted(values)
    return ordered[min(len(ordered)-1,math.ceil(fraction*len(ordered))-1)]


def audit(directory,map_path):
    root=Path(directory)
    manifest=read_json(root/'tileset.json')
    route=read_json(root/manifest['route'])
    scene=read_json(map_path)
    grid=read_json(root/manifest['terrain_grid'])
    if hashlib.sha256(Path(map_path).read_bytes()).hexdigest()!=manifest['source_map_sha256']:
        raise ValueError('QA source map hash mismatch')
    if hashlib.sha256((root/manifest['terrain_grid']).read_bytes()).hexdigest()!=manifest['terrain_grid_sha256']:
        raise ValueError('QA terrain grid hash mismatch')
    roads={road['id']:road for road in scene['roads']}
    bad_route_ids=[road_id for road_id in route['source_road_ids']
                   if roads[road_id].get('bridge','no')!='no' or
                      roads[road_id].get('tunnel','no')!='no' or
                      roads[road_id].get('layer','0')!='0' or
                      roads[road_id].get('access')=='no' or
                      roads[road_id].get('motor_vehicle')=='no']
    by_tile={}
    for tile in manifest['tiles']:
        by_tile[tile['id']]=(
            read_json(root/tile['road_surface_file'])['surfaces'],
            read_json(root/tile['road_extent_file'])['extents'])
    counts={'samples':0,'candidate_surface':0,'official_extent':0,'dem_ground':0}
    missing={'candidate_surface':[],'official_extent':[],'dem_ground':[]}
    grades=[];previous=None
    for a,b,road_id in zip(route['points'],route['points'][1:],route['source_road_ids']):
        length=math.dist(a,b)
        steps=max(1,math.ceil(length/5))
        for index in range(steps):
            t=(index+.5)/steps
            x,z=a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t
            tile=next((item for item in manifest['tiles']
                       if item['bounds'][0]<=x<item['bounds'][2] and
                          item['bounds'][1]<=z<item['bounds'][3]),None)
            counts['samples']+=1
            location={'x':round(x,3),'z':round(z,3),'source_road_id':road_id}
            if tile:
                surfaces,extents=by_tile[tile['id']]
                for key,items in (('candidate_surface',surfaces),('official_extent',extents)):
                    if any(point_in_polygon((x,z),item['polygon']) for item in items):
                        counts[key]+=1
                    else:missing[key].append(location)
            else:
                missing['candidate_surface'].append(location)
                missing['official_extent'].append(location)
            try:
                ground=height_at(grid,x,z)
                counts['dem_ground']+=1
            except ValueError:
                ground=None;missing['dem_ground'].append(location)
            if previous and ground is not None:
                last_x,last_z,last_ground=previous
                distance=math.hypot(x-last_x,z-last_z)
                if distance>.01:grades.append(abs(ground-last_ground)/distance)
            previous=(x,z,ground) if ground is not None else None
    return {'schema':'therabby.geoengine.driving-route-qa.v0.1',
        'route_length_m':route['length_m'],'sample_spacing_max_m':5,
        'counts':counts,'coverage_ratio':{key:round(counts[key]/counts['samples'],4)
            for key in ('candidate_surface','official_extent','dem_ground')},
        'missing_samples':missing,'excluded_structure_violations':bad_route_ids,
        'ground_grade_p95_abs':round(percentile(grades,.95),4) if grades else None,
        'ground_grade_max_abs':round(max(grades),4) if grades else None,
        'road_surface_height_verified':False,'collision_ready':False,
        'limitations':'DEM is ground terrain, not bridge/tunnel road deck; candidate surface width and legal direction unverified'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tiles-dir',default='dist/real/fukushima-east-1km/tiles-250')
    parser.add_argument('--map',default='dist/real/fukushima-east-1km/map_lod1.json')
    parser.add_argument('--output',default='dist/real/fukushima-east-1km/driving_route_qa.json')
    args=parser.parse_args()
    report=audit(args.tiles_dir,args.map)
    write_json(args.output,report)
    print('Route QA',report['counts'],'grade p95/max',
          report['ground_grade_p95_abs'],report['ground_grade_max_abs'])


if __name__=='__main__':main()
