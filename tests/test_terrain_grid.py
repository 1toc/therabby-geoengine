import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from geoengine import load_area
from prepare_wide_tiles import inverse_project
from terrain_grid import decode_dem5a, height_at, load_source, sample_dem


class TestTerrainGrid(unittest.TestCase):
    def test_dem5a_encoding_and_missing_value(self):
        self.assertEqual(decode_dem5a((0,0,100)),1)
        self.assertEqual(decode_dem5a((255,255,156)),-1)
        self.assertIsNone(decode_dem5a((128,0,0)))

    def test_real_source_grid_and_relative_height(self):
        root=ROOT/'data/raw/gsi_dem5a_1km'
        manifest=json.loads((root/'source_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['tiles']),4)
        for item in manifest['tiles']:
            self.assertEqual(hashlib.sha256((root/item['file']).read_bytes()).hexdigest(),item['sha256'])
        path=ROOT/'dist/real/fukushima-east-1km/terrain_grid_5m.json'
        grid=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(grid['schema'],'therabby.geoengine.terrain-grid.v0.1')
        self.assertEqual(grid['step_m'],5)
        self.assertEqual(len(grid['heights_relative_m']),201)
        self.assertEqual(grid['heights_relative_m'][100][100],0)
        self.assertGreater(grid['max_relative_m']-grid['min_relative_m'],5)
        self.assertAlmostEqual(height_at(grid,0,0),0)
        area=load_area(ROOT/'config/fukushima_station_east_1km.json')
        _,tiles=load_source(root,area['id'])
        for x,z in ((0,0),(-250,125),(300,-300)):
            lat,lon=inverse_project(x,z,area)
            expected=sample_dem(tiles,lat,lon)-grid['height_origin_tp_m']
            self.assertAlmostEqual(height_at(grid,x,z),expected,delta=.005)
        with self.assertRaisesRegex(ValueError,'outside grid'):
            height_at(grid,501,0)


if __name__=='__main__':unittest.main()
