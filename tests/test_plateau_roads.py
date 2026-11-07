import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from fetch_plateau_tran import select_files
from geoengine import load_area
from prepare_plateau_roads import extract_roads
from road_tiles import annotate_official_extent, point_in_polygon, road_network


class TestPlateauRoads(unittest.TestCase):
    def setUp(self):
        self.area=load_area(ROOT/'config/fukushima_station_east_1km.json')

    def test_synthetic_lod1_road_and_vertical_guard(self):
        xml='''<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
          xmlns:gml="http://www.opengis.net/gml"
          xmlns:tran="http://www.opengis.net/citygml/transportation/2.0">
          <gml:boundedBy><gml:Envelope srsName="http://www.opengis.net/def/crs/EPSG/0/6697"
            srsDimension="3"/></gml:boundedBy>
          <core:cityObjectMember><tran:Road gml:id="synthetic-road">
            <tran:class>1040</tran:class><tran:function>3</tran:function>
            <tran:lod1MultiSurface><gml:MultiSurface><gml:surfaceMember>
              <gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>
              37.7544 140.4618 0 37.7544 140.4620 0
              37.7545 140.4620 0 37.7545 140.4618 0 37.7544 140.4618 0
              </gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>
            </gml:surfaceMember></gml:MultiSurface></tran:lod1MultiSurface>
          </tran:Road></core:cityObjectMember></core:CityModel>'''
        with TemporaryDirectory() as folder:
            source=Path(folder)/'synthetic-tran.gml'
            source.write_text(xml,encoding='utf-8')
            roads=extract_roads(source,self.area,[-500,-500,500,500])
            self.assertEqual(len(roads),1)
            self.assertEqual(roads[0]['height_m'],None)
            self.assertIsNone(roads[0]['drivable'])
            self.assertTrue(point_in_polygon((0,0),roads[0]['polygon']))
            source.write_text(xml.replace('EPSG/0/6697','EPSG/0/6668'),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'EPSG:6697'):
                extract_roads(source,self.area,[-500,-500,500,500])
            source.write_text(xml.replace('140.4618 0','140.4618 5',1),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'vertical coordinate'):
                extract_roads(source,self.area,[-500,-500,500,500])

    def test_official_catalog_rejects_wrong_host(self):
        item={'url':'https://assets.cms.plateau.reearth.io/56405306_tran_6697_op.gml',
              'fileSize':1234,'maxLod':1,'code':'56405306'}
        catalog={'cities':[{'cityCode':'07201','year':2025,'files':{'tran':[item]}}]}
        self.assertEqual(len(select_files(catalog,self.area)),1)
        item['url']='https://example.com/56405306_tran_6697_op.gml'
        with self.assertRaisesRegex(ValueError,'URL'):
            select_files(catalog,self.area)

    def test_synthetic_osm_edge_official_alignment_is_not_drivable_proof(self):
        roads=[{'id':'synthetic-osm','points':[[0,0],[10,0]],'width_m':6,
                'width_quality':'class-estimate','highway':'residential'}]
        network=road_network(roads,{'projection':'synthetic'})
        extent={'source_road_id':'synthetic-plateau',
                'polygon':[[0,-2],[10,-2],[10,2],[0,2]]}
        annotate_official_extent(network,[extent])
        edge=network['edges'][0]
        self.assertEqual(edge['official_extent_coverage_ratio'],1)
        self.assertEqual(edge['legal_access'],'not-verified')
        self.assertEqual(edge['elevation_m'],None)

    def test_real_extent_source_integrity(self):
        path=ROOT/'dist/real/fukushima-east-1km/plateau_road_extent.json'
        data=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(data['schema'],'therabby.geoengine.plateau-road-extent.v0.1')
        self.assertEqual(len(data['roads']),500)
        self.assertEqual(len(data['source_files']),6)
        for source in data['source_files']:
            file=ROOT/'data/raw/plateau/tran_1km'/source['file']
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),source['sha256'])
        self.assertTrue(all(road['height_m'] is None and road['drivable'] is None
                            for road in data['roads']))


if __name__=='__main__':unittest.main()
