import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StationVisualTerrainTests(unittest.TestCase):
    def test_generated_asset_matches_verified_meshes(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from build_station_visual_terrain import build
        saved = json.loads((ROOT / 'data/derived/fukushima-station-roads-v02/visual_terrain.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, build())
        self.assertGreater(len(saved['triangles']), 0)

    def test_triangle_interpolation_and_outside_bounds(self):
        module = ROOT / 'viewer/geoengine-station-roads-v02.js'
        js = r'''
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8').replace(/^import .*;\s*/,'').replace(/export /g,'');
const ctx={};vm.createContext(ctx);vm.runInContext(source+';this.stationGround=stationGround',ctx);
const data={visualTerrain:{triangles:[[[0,0,10],[10,0,20],[0,10,30]]]}};
if(Math.abs(ctx.stationGround(data,2,3)-18)>1e-8)throw Error('interpolation failed');
if(ctx.stationGround(data,151,0)!==null)throw Error('bounds failed');
if(ctx.stationGround(data,8,8)!==null)throw Error('gap failed');
'''
        subprocess.run(['node', '-e', js, str(module)], check=True)


if __name__ == '__main__':
    unittest.main()
