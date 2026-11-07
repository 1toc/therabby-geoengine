import hashlib
import json
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from geoengine import jprcs_ix, load_area, xy_of
from prepare_wide_tiles import inverse_project
from tile_math import clip_roads, tile_bounds
from road_tiles import road_network, road_surfaces
from facade_geometry import build_facade_batches
from procedural_road_texture import asphalt_png
from terrain_grid import height_at
from tempfile import TemporaryDirectory


class TestWideTiles(unittest.TestCase):
    def test_projection_origin_and_inverse(self):
        east,north=jprcs_ix(36,139+50/60)
        self.assertAlmostEqual(east,0,delta=.0001)
        self.assertAlmostEqual(north,0,delta=.0001)
        area=load_area(ROOT/'config/fukushima_station_east_1km.json')
        for x,z in ((0,0),(-500,-500),(500,500),(245,-310)):
            lat,lon=inverse_project(x,z,area)
            actual=xy_of(lat,lon,area)
            self.assertAlmostEqual(actual[0],x,delta=.002)
            self.assertAlmostEqual(actual[1],z,delta=.002)

    def test_all_internal_road_seams(self):
        road={'id':'synthetic-road','points':[[-499,85],[499,85]],'width_m':6}
        for size in (100,250,500):
            pieces=[(tile,frag) for tile in tile_bounds(500,size)
                    for frag in clip_roads([road],tile['bounds'],500,size)]
            seams={}
            for tile,fragment in pieces:
                for point,node in zip((fragment['points'][0],fragment['points'][-1]),fragment['endpoint_nodes']):
                    if node:seams.setdefault(node,set()).add(tile['id'])
            self.assertEqual(len(seams),1000//size-1)
            self.assertTrue(all(len(owners)==2 for owners in seams.values()))

    def test_synthetic_road_surface_seams_and_metadata(self):
        road={'id':'synthetic-road','points':[[-499,85],[499,85]],
              'width_m':6,'width_quality':'class-estimate','highway':'residential'}
        for size in (100,250,500):
            tiles=list(tile_bounds(500,size))
            for boundary in range(-500+size,500,size):
                neighbors=[tile for tile in tiles if tile['bounds'][1]<=85<tile['bounds'][3]
                           and tile['bounds'][0] in (boundary-size,boundary)]
                self.assertEqual(len(neighbors),2)
                shared=[]
                for tile in neighbors:
                    surfaces=road_surfaces([road],tile['bounds'])
                    self.assertEqual(len(surfaces),1)
                    self.assertEqual(surfaces[0]['legal_access'],'not-verified')
                    self.assertEqual(surfaces[0]['height_quality'],'flat-prototype-not-surveyed')
                    shared.append({tuple(point) for point in surfaces[0]['polygon']
                                   if point[0]==boundary})
                self.assertEqual(shared[0],shared[1])
                self.assertEqual(shared[0],{(boundary,82.0),(boundary,88.0)})

    def test_network_and_facades_are_estimates(self):
        roads=[{'id':'synthetic-car','points':[[0,0],[10,0]],'width_m':8,
                'width_quality':'class-estimate','highway':'secondary','oneway':'yes'},
               {'id':'synthetic-foot','points':[[10,0],[10,10]],'width_m':2,
                'width_quality':'class-estimate','highway':'footway'}]
        network=road_network(roads,{'projection':'synthetic'})
        self.assertEqual([(edge['direction'],edge['drivable']) for edge in network['edges']],
                         [('forward',True),('both',False)])
        self.assertEqual(len(road_surfaces(roads,[-1,-1,12,12])),1)
        building={'id':'synthetic-building','source':'PLATEAU CityGML',
                  'footprint':[[1,3],[7,3],[7,8],[1,8]],'height_m':12}
        first,stats=build_facade_batches([building],(0,0),set(),roads)
        second,_=build_facade_batches([building],(0,0),set(),roads)
        self.assertEqual(first,second)
        self.assertEqual(stats['buildings'],1)
        self.assertGreater(stats['windows']+stats['shopfronts'],0)
        self.assertIn('trim',first)
        with TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'synthetic-asphalt.png'
            self.assertTrue(asphalt_png(path).startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(asphalt_png(path),path.read_bytes())

    def test_real_wide_assets_and_route(self):
        root=ROOT/'dist/real/fukushima-east-1km'
        scene=json.loads((root/'map_lod1.json').read_text(encoding='utf-8'))
        official_path=root/'plateau_road_extent.json'
        official=json.loads(official_path.read_text(encoding='utf-8'))
        terrain_path=root/'terrain_grid_5m.json'
        terrain=json.loads(terrain_path.read_text(encoding='utf-8'))
        def polygon_area(polygon):
            return abs(sum(a[0]*b[1]-b[0]*a[1]
                           for a,b in zip(polygon,polygon[1:]+polygon[:1])))/2
        official_area=sum(polygon_area(item['polygon']) for item in official['roads'])
        roads={road['id']:road for road in scene['roads']}
        self.assertEqual((len(scene['buildings']),len(roads)),(1849,366))
        self.assertEqual(sum(road.get('bridge')=='yes' for road in roads.values()),18)
        self.assertEqual(sum(road.get('tunnel')=='yes' for road in roads.values()),29)
        facade_counts=[]
        network_hashes=set()
        for size,expected in ((100,100),(250,16),(500,4)):
            directory=root/f'tiles-{size}'
            manifest=json.loads((directory/'tileset.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['schema'],'therabby.geoengine.tileset.wide.v0.1')
            self.assertEqual(manifest['source_map_sha256'],
                             hashlib.sha256((root/'map_lod1.json').read_bytes()).hexdigest())
            self.assertEqual(len(manifest['tiles']),expected)
            self.assertEqual(manifest['terrain']['height_m'],None)
            self.assertEqual(manifest['core_replaced_buildings'],56)
            self.assertEqual(manifest['plateau_road_extent_count'],500)
            self.assertEqual(manifest['terrain_grid_sha256'],
                             hashlib.sha256(terrain_path.read_bytes()).hexdigest())
            self.assertEqual(manifest['terrain']['origin_height_tp_m'],terrain['height_origin_tp_m'])
            self.assertEqual(manifest['plateau_road_extent_sha256'],
                             hashlib.sha256(official_path.read_bytes()).hexdigest())
            facade_counts.append((sum(t['facade_estimate']['windows'] for t in manifest['tiles']),
                                  sum(t['facade_estimate']['shopfronts'] for t in manifest['tiles'])))
            for asset,key in ((manifest['road_network'],'road_network_sha256'),
                              (manifest['road_visual_texture'],'road_visual_texture_sha256')):
                self.assertEqual(hashlib.sha256((directory/asset).read_bytes()).hexdigest(),manifest[key])
            network=json.loads((directory/manifest['road_network']).read_text(encoding='utf-8'))
            network_hashes.add(manifest['road_network_sha256'])
            self.assertEqual(network['schema'],'therabby.geoengine.road-network.v0.1')
            self.assertTrue({edge['source_road_id'] for edge in network['edges']}<=set(roads))
            self.assertGreater(network['official_extent_mean_sample_coverage'],.7)
            self.assertTrue(any(edge.get('ground_grade_estimate') is not None
                                for edge in network['edges'] if edge['drivable']))
            self.assertTrue(all(edge['ground_grade_estimate'] is None
                                for edge in network['edges']
                                if edge['bridge']!='no' or edge['tunnel']!='no' or edge['layer']!='0'))
            for asset,key in ((manifest['core_model'],'core_model_sha256'),
                              (manifest['core_low_model'],'core_low_model_sha256'),
                              (manifest['overview_ground'],'overview_sha256')):
                self.assertEqual(hashlib.sha256((directory/asset).read_bytes()).hexdigest(),manifest[key])
            owners=set();seams={};tiled_extent_area=0
            for tile in manifest['tiles']:
                owners.update(b['id'] for b in json.loads((directory/tile['geometry']).read_text(encoding='utf-8'))['buildings'])
                for file,key in ((tile['glb'],'sha256'),(tile['ground'],'ground_sha256'),
                                 (tile['roads'],'roads_sha256'),
                                 (tile['road_surface_file'],'road_surface_sha256'),
                                 (tile['road_extent_file'],'road_extent_sha256')):
                    self.assertEqual(hashlib.sha256((directory/file).read_bytes()).hexdigest(),tile[key])
                extents=json.loads((directory/tile['road_extent_file']).read_text(encoding='utf-8'))
                self.assertEqual(len(extents['extents']),tile['road_extent_count'])
                tiled_extent_area+=sum(polygon_area(item['polygon']) for item in extents['extents'])
                for extent in extents['extents']:
                    self.assertEqual(len(extent['polygon']),len(extent['drape_ground_heights_m']))
                    for point,high in zip(extent['polygon'],extent['drape_ground_heights_m']):
                        self.assertAlmostEqual(high,height_at(terrain,*point),delta=.001)
                surface_file=json.loads((directory/tile['road_surface_file']).read_text(encoding='utf-8'))
                self.assertEqual(len(surface_file['surfaces']),tile['road_surface_count'])
                x0,z0,x1,z1=tile['bounds']
                for surface in surface_file['surfaces']:
                    self.assertIn(surface['source_road_id'],roads)
                    self.assertEqual(len(surface['polygon']),len(surface['vertex_ground_heights_m']))
                    self.assertTrue(all(x0<=x<=x1 and z0<=z<=z1
                                        for x,z in surface['polygon']))
                sidecar=json.loads((directory/tile['roads']).read_text(encoding='utf-8'))
                for segment in sidecar['roads']:
                    for point,node in zip((segment['points'][0],segment['points'][-1]),segment['endpoint_nodes']):
                        if node:seams.setdefault(node,[]).append((tile['id'],tuple(point)))
            self.assertEqual(len(owners),1849)
            self.assertAlmostEqual(tiled_extent_area,official_area,delta=.5)
            self.assertTrue(any(len({owner for owner,_ in values})>1 for values in seams.values()))
            self.assertTrue(all(len({point for _,point in values})==1 for values in seams.values()))
            route=json.loads((directory/'route.json').read_text(encoding='utf-8'))
            self.assertGreater(route['length_m'],1000)
            qa=json.loads((root/f'driving_route_qa_{size}.json').read_text(encoding='utf-8'))
            self.assertEqual(qa['route_length_m'],route['length_m'])
            self.assertEqual(qa['counts']['samples'],294)
            self.assertEqual(qa['counts']['candidate_surface'],qa['counts']['samples'])
            self.assertEqual(qa['counts']['official_extent'],qa['counts']['samples'])
            self.assertEqual(qa['counts']['dem_ground'],qa['counts']['samples'])
            self.assertFalse(qa['excluded_structure_violations'])
            self.assertFalse(qa['collision_ready'])
            self.assertTrue(all(roads[road_id].get('bridge','no')=='no' and
                                roads[road_id].get('tunnel','no')=='no' and
                                roads[road_id].get('layer','0')=='0'
                                for road_id in route['source_road_ids']))
            self.assertEqual(len(route['source_road_ids']),len(route['points'])-1)
            for a,b,road_id in zip(route['points'],route['points'][1:],route['source_road_ids']):
                points=roads[road_id]['points']
                self.assertTrue(any((a==p and b==q) or (a==q and b==p)
                                    for p,q in zip(points,points[1:])))
        self.assertEqual(len(set(facade_counts)),1)
        self.assertEqual(len(network_hashes),1)


if __name__=='__main__':unittest.main()
