#!/usr/bin/env python3
"""Prepare 1km orthophoto crops, road sidecars and tile records for Blender.

Requires Pillow on the development PC; the browser client remains static.
"""
import argparse
import hashlib
import heapq
import json
import math
from pathlib import Path

from PIL import Image
from geoengine import METERS_PER_DEG_LAT, jprcs_ix, read_json, write_json
from fetch_ortho import world_pixel
from tile_math import tile_bounds, clip_roads
from road_tiles import annotate_official_extent, clip_polygon_rect, road_is_drivable, road_network, road_surfaces
from terrain_grid import height_at


def inverse_project(x, z, area):
    """Newton inverse of the fixed GRS80 TM forward formula, for ortho sampling."""
    if area.get('projection') != 'JGD2011_JPRCS_IX_GRS80':
        raise ValueError('Wide tile orthophoto warp requires JGD2011_JPRCS_IX_GRS80')
    e0, n0 = jprcs_ix(area['center_lat'], area['center_lon'])
    east, north = e0+x, n0-z
    lat = area['center_lat']-z/METERS_PER_DEG_LAT
    lon = area['center_lon']+x/(METERS_PER_DEG_LAT*math.cos(math.radians(lat)))
    for _ in range(4):
        e, n = jprcs_ix(lat, lon)
        el, nl = jprcs_ix(lat+1e-5, lon)
        eo, no = jprcs_ix(lat, lon+1e-5)
        a,b,c,d = (el-e)/1e-5,(eo-e)/1e-5,(nl-n)/1e-5,(no-n)/1e-5
        det = a*d-b*c
        de,dn = east-e,north-n
        lat += (d*de-b*dn)/det
        lon += (-c*de+a*dn)/det
    return lat, lon


def ortho_pixel(x, z, area, meta):
    lat, lon = inverse_project(x,z,area)
    half = meta['half_size_m']
    dlat = half/METERS_PER_DEG_LAT
    dlon = half/(METERS_PER_DEG_LAT*math.cos(math.radians(area['center_lat'])))
    left, top = world_pixel(area['center_lat']+dlat,area['center_lon']-dlon,meta['zoom'])
    right,bottom = world_pixel(area['center_lat']-dlat,area['center_lon']+dlon,meta['zoom'])
    px,py = world_pixel(lat,lon,meta['zoom'])
    return ((px-left)/(right-left)*meta['image_size'][0],
            (py-top)/(bottom-top)*meta['image_size'][1])


def crop_tile(image, bounds, area, meta, output):
    x0,z0,x1,z1 = bounds
    size = max(128, round(x1-x0))
    s0 = ortho_pixel(x0,z0,area,meta)
    sx = ortho_pixel(x1,z0,area,meta)
    sz = ortho_pixel(x0,z1,area,meta)
    coeff = ((sx[0]-s0[0])/size,(sz[0]-s0[0])/size,s0[0],
             (sx[1]-s0[1])/size,(sz[1]-s0[1])/size,s0[1])
    result = image.transform((size,size), Image.Transform.AFFINE, coeff,
                             resample=Image.Resampling.BICUBIC)
    result.save(output,'JPEG',quality=90,subsampling=0,optimize=True)


def route_from_roads(roads,half=500):
    """Longest useful connected driving route, derived only from OSM lines."""
    graph = {}
    for road in roads:
        if (not road_is_drivable(road) or road.get('bridge','no')!='no'
                or road.get('tunnel','no')!='no' or road.get('layer','0')!='0'):
            continue
        for a,b in zip(road['points'],road['points'][1:]):
            if any(abs(point[0])>half or abs(point[1])>half for point in (a,b)):
                continue
            a,b = tuple(a),tuple(b)
            length = math.dist(a,b)
            if length < .1:
                continue
            graph.setdefault(a,[]).append((b,length,road['id']))
            graph.setdefault(b,[]).append((a,length,road['id']))
    if not graph:
        raise ValueError('No connected OSM driving roads')
    def search(start):
        distances={start:0}; parent={}; queue=[(0,start)]
        while queue:
            dist,node=heapq.heappop(queue)
            if dist!=distances[node]:continue
            for neighbor,length,road_id in graph[node]:
                candidate=dist+length
                if candidate<distances.get(neighbor,float('inf')):
                    distances[neighbor]=candidate
                    parent[neighbor]=(node,road_id)
                    heapq.heappush(queue,(candidate,neighbor))
        return distances,parent
    # Choose the largest connected component, then a two-sweep route in it.
    seen=set(); largest=[]
    for start in graph:
        if start in seen:continue
        distances,_=search(start)
        seen.update(distances)
        if len(distances)>len(largest):largest=list(distances)
    first=max(search(largest[0])[0],key=lambda point:math.dist(point,largest[0]))
    distances,parent=search(first)
    end=max(distances,key=distances.get)
    nodes=[end]; ids=[]
    while nodes[-1]!=first:
        prior,road_id=parent[nodes[-1]]
        ids.append(road_id);nodes.append(prior)
    nodes.reverse();ids.reverse()
    return {'schema':'therabby.geoengine.route.v0.1','points':[list(p) for p in nodes],
            'source_road_ids':ids,'length_m':round(distances[end],2),
            'quality':'OSM ground-level candidate centreline; legal direction, lanes and width not verified'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--map',required=True);parser.add_argument('--ortho',required=True)
    parser.add_argument('--output-dir',required=True);parser.add_argument('--tile-size',type=int,required=True)
    parser.add_argument('--plateau-roads',help='Verified official LOD1 road-extent JSON')
    parser.add_argument('--terrain-grid',help='Verified GSI DEM5A ground grid JSON')
    args=parser.parse_args()
    scene=read_json(args.map);area=scene['area'];half=area['half_size_m']
    if half!=500 or args.tile_size not in (100,250,500):
        raise ValueError('Wide comparison requires the 1km map and 100/250/500m tiles')
    ortho=Path(args.ortho)
    meta=read_json(ortho.with_suffix('.provenance.json'))
    if meta['area_id']!=area['id'] or hashlib.sha256(ortho.read_bytes()).hexdigest()!=meta['sha256']:
        raise ValueError('Orthophoto provenance mismatch')
    image=Image.open(ortho).convert('RGB')
    output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
    crop_tile(image,[-half,-half,half,half],area,meta,output/'overview.jpg')
    extent_source=Path(args.plateau_roads) if args.plateau_roads else None
    extent_data=read_json(extent_source) if extent_source else None
    if extent_data and (extent_data['schema']!='therabby.geoengine.plateau-road-extent.v0.1'
                        or extent_data['area_id']!=area['id'] or extent_data['bounds']!=[-half,-half,half,half]):
        raise ValueError('PLATEAU Road extent area/schema mismatch')
    extents=extent_data['roads'] if extent_data else []
    terrain_path=Path(args.terrain_grid) if args.terrain_grid else None
    terrain_grid=read_json(terrain_path) if terrain_path else None
    if terrain_grid and (terrain_grid['schema']!='therabby.geoengine.terrain-grid.v0.1'
                         or terrain_grid['area_id']!=area['id']
                         or terrain_grid['bounds']!=[-half,-half,half,half]
                         or not terrain_grid['vertical_datum'].startswith('T.P. (Tokyo Peil)')):
        raise ValueError('GSI DEM5A grid area/schema/vertical datum mismatch')
    network_path=output/'road-network.json'
    network=road_network(scene['roads'],scene['coordinate_system'])
    if extent_data:annotate_official_extent(network,extents)
    if terrain_grid:
        nodes={node['id']:node['position'] for node in network['nodes']}
        for edge in network['edges']:
            a,b=nodes[edge['from']],nodes[edge['to']]
            if all(-half<=p[0]<=half and -half<=p[1]<=half for p in (a,b)):
                ya,yb=height_at(terrain_grid,*a),height_at(terrain_grid,*b)
                edge['ground_height_from_m']=round(ya,3)
                edge['ground_height_to_m']=round(yb,3)
                grade_separated=(edge['bridge']!='no' or edge['tunnel']!='no' or edge['layer']!='0')
                edge['ground_grade_estimate']=(None if grade_separated else
                    round((yb-ya)/edge['length_m'],5))
                edge['ground_height_quality']=('GSI DEM5A ground; grade-separated road deck unknown'
                    if grade_separated else 'GSI DEM5A ground; road surface unverified')
            else:
                edge['ground_height_from_m']=None
                edge['ground_height_to_m']=None
                edge['ground_grade_estimate']=None
                edge['ground_height_quality']='outside DEM grid'
    write_json(network_path,network)
    records=[]
    for tile in tile_bounds(half,args.tile_size):
        tile_id=tile['id'];bounds=tile['bounds'];x0,z0,x1,z1=bounds
        photo=f'ground_{tile_id}.jpg'
        crop_tile(image,bounds,area,meta,output/photo)
        roads=clip_roads(scene['roads'],bounds,half,args.tile_size)
        roads_path=output/f'roads_{tile_id}.json'
        write_json(roads_path,{'schema':'therabby.geoengine.roads.tile.v0.1',
            'tile_id':tile_id,'bounds':bounds,'roads':roads})
        surfaces=road_surfaces(scene['roads'],bounds)
        if terrain_grid:
            for surface in surfaces:
                surface['vertex_ground_heights_m']=[round(height_at(terrain_grid,*p),3)
                                                     for p in surface['polygon']]
                surface['height_m']=None
                surface['height_quality']=('GSI DEM5A ground drape; bridge/tunnel height unknown'
                    if surface['bridge']!='no' or surface['tunnel']!='no' or surface['layer']!='0'
                    else 'GSI DEM5A ground drape; road surface unverified')
        tile_extents=[]
        for road in extents:
            polygon=clip_polygon_rect(road['polygon'],bounds)
            if polygon:
                item={**road,'polygon':polygon}
                if terrain_grid:
                    item['drape_ground_heights_m']=[round(height_at(terrain_grid,*p),3)
                                                     for p in polygon]
                tile_extents.append(item)
        extent_path=output/f'road-extents_{tile_id}.json'
        write_json(extent_path,{'schema':'therabby.geoengine.road-extents.tile.v0.1',
            'tile_id':tile_id,'bounds':bounds,'extents':tile_extents,
            'attribution':'Project PLATEAU / Fukushima City; dataset-specific terms apply',
            'quality':'LOD1 road extent; carriageway, lane, height and legal access unknown'})
        surface_path=output/f'road-surfaces_{tile_id}.json'
        write_json(surface_path,{'schema':'therabby.geoengine.road-surfaces.tile.v0.1',
            'tile_id':tile_id,'bounds':bounds,'elevation_quality':'flat-prototype-not-surveyed',
            'source':'OpenStreetMap road centreline',
            'attribution':'© OpenStreetMap contributors / ODbL 1.0',
            'derivation':'OSM highway class width estimate; segment quad clipped to tile',
            'surfaces':surfaces})
        buildings=[]
        for building in scene['buildings']:
            pts=building['footprint']
            cx=sum(p[0] for p in pts)/len(pts)
            cz=sum(p[1] for p in pts)/len(pts)
            # A single owner tile keeps the original footprint intact.
            cx=max(-half+1e-6,min(half-1e-6,cx))
            cz=max(-half+1e-6,min(half-1e-6,cz))
            if x0<=cx<x1 and z0<=cz<z1:
                buildings.append(building)
        record={**tile,'glb':f'tile_{tile_id}.glb','roads':f'roads_{tile_id}.json',
                'road_surfaces':surfaces,'official_road_extents':tile_extents,
                'ground':photo,'buildings':buildings}
        write_json(output/f'geometry_{tile_id}.json',record)
        records.append({key:value for key,value in record.items()
                        if key not in ('buildings','road_surfaces','official_road_extents')})
        records[-1].update({'geometry':f'geometry_{tile_id}.json',
                            'road_extent_file':extent_path.name,
                            'road_extent_sha256':hashlib.sha256(extent_path.read_bytes()).hexdigest(),
                            'road_extent_count':len(tile_extents),
                            'road_surface_file':surface_path.name,
                            'road_surface_sha256':hashlib.sha256(surface_path.read_bytes()).hexdigest(),
                            'road_surface_count':len(surfaces),
                            'ground_sha256':hashlib.sha256((output/photo).read_bytes()).hexdigest(),
                            'roads_sha256':hashlib.sha256(roads_path.read_bytes()).hexdigest(),
                            'building_count':len(buildings),'road_fragments':len(roads),
                            'plateau_lod1':sum(b['source']=='PLATEAU CityGML' for b in buildings),
                            'osm_fallback':sum(b['source']=='OpenStreetMap' for b in buildings)})
        records[-1]['source_coverage']={
            'plateau_lod1_buildings':records[-1]['plateau_lod1'],
            'osm_only_buildings':records[-1]['osm_fallback'],
            'dem':None}
        records[-1]['visual_quality']={'buildings':'untextured LOD1 or OSM estimated extrusion',
                                      'ground':'official PLATEAU Ortho 2024 resampled'}
    route=route_from_roads(scene['roads'],half)
    write_json(output/'route.json',route)
    manifest={'schema':'therabby.geoengine.tileset.wide.v0.1','scope':'Fukushima station east 1km visual preview',
        'area':area,'coordinate_system':scene['coordinate_system'],'tile_size_m':args.tile_size,
        'bounds':[-half,-half,half,half],'source_map':Path(args.map).name,
        'source_map_sha256':hashlib.sha256(Path(args.map).read_bytes()).hexdigest(),
        'source_ortho_sha256':meta['sha256'],'route':'route.json','route_length_m':route['length_m'],
        'road_network':network_path.name,
        'road_network_sha256':hashlib.sha256(network_path.read_bytes()).hexdigest(),
        'plateau_road_extent_source':extent_source.name if extent_source else None,
        'plateau_road_extent_sha256':hashlib.sha256(extent_source.read_bytes()).hexdigest() if extent_source else None,
        'plateau_road_extent_count':len(extents),
        'terrain_grid':f'../{terrain_path.name}' if terrain_path else None,
        'terrain_grid_sha256':hashlib.sha256(terrain_path.read_bytes()).hexdigest() if terrain_path else None,
        'overview_ground':'overview.jpg',
        'overview_sha256':hashlib.sha256((output/'overview.jpg').read_bytes()).hexdigest(),
        'provenance':scene['provenance']+[{'name':'PLATEAU Ortho 2024','source':meta['layer'],
                                          'zoom':meta['zoom'],'license':'See Project PLATEAU dataset terms'}]+
            ([{'name':'PLATEAU Road LOD1','source':extent_source.name,
               'sha256':hashlib.sha256(extent_source.read_bytes()).hexdigest(),
               'quality':'official road extent, not carriageway or surveyed elevation',
               'license':'See Project PLATEAU dataset terms'}] if extent_source else [])+
            ([{'name':'GSI DEM5A ground elevation','source':terrain_path.name,
               'sha256':hashlib.sha256(terrain_path.read_bytes()).hexdigest(),
               'vertical_datum':'T.P. (Tokyo Peil)',
               'quality':'interpolated ground; road decks and bridges not represented',
               'attribution':'Geospatial Information Authority of Japan'}] if terrain_path else []),
        'derived_visuals':[
            {'asset':'building facades','generator':'scripts/facade_geometry.py',
             'basis':'PLATEAU LOD1/OSM footprint and height; window/color/shop details estimated'},
            {'asset':'road asphalt and centre dashes','generator':'scripts/procedural_road_texture.py; scripts/blender_export_wide_tiles.py',
             'basis':'OpenStreetMap centreline and class width; texture/markings illustrative'}],
        'terrain':({'height_m':None,'origin_height_tp_m':terrain_grid['height_origin_tp_m'],
            'min_relative_m':terrain_grid['min_relative_m'],
            'max_relative_m':terrain_grid['max_relative_m'],
            'quality':'GSI DEM5A ground drape; roadway decks and collision unverified'}
            if terrain_grid else {'height_m':None,'quality':'unknown; flat visual plane only'}),
        'tiles':records}
    write_json(output/'tileset.json',manifest)
    print(f'Prepared {len(records)} tiles, {sum(r["building_count"] for r in records)} buildings, '
          f'route {route["length_m"]} m -> {output}')


if __name__=='__main__':main()
