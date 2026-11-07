import hashlib
import json
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PhotoPilotTests(unittest.TestCase):
    def test_full_stream_materials_are_in_low_glb(self):
        folder=ROOT/'data/derived/fukushima-station-lod2-overlay'
        tiles=json.loads((folder/'tileset.json').read_text(encoding='utf-8'))['tiles']
        config=json.loads((ROOT/'data/derived/station-photo-pilot/stream-full.json').read_text(encoding='utf-8'))
        material_names={}
        for tile in tiles:
            raw=(folder/tile['lod2_low']['path']).read_bytes()
            length=struct.unpack_from('<I',raw,12)[0]
            data=json.loads(raw[20:20+length])
            material_names[tile['id']]={m['name'] for m in data['materials']
                                        if 'baseColorTexture' in m.get('pbrMetallicRoughness',{})}
        self.assertEqual(len(config['photos']),117)
        for photo in config['photos']:
            self.assertIn(photo['material'],material_names[photo['tile_id']])

    def test_station_style_profiles_cover_official_materials(self):
        manifest=json.loads((ROOT/'data/derived/station-photo-pilot/stream-full.json').read_text(encoding='utf-8'))
        source=(ROOT/'viewer/station-style-profiles.js').read_text(encoding='utf-8')
        profiles=json.loads(source.split('export const stationStyleProfiles = ',1)[1].rstrip().removesuffix(';'))
        self.assertEqual(set(profiles),{photo['material'] for photo in manifest['photos']})
        for photo in manifest['photos']:
            profile=profiles[photo['material']]
            self.assertEqual(profile['photo_id'],photo['photo_id'])
            self.assertEqual(profile['building_ids'],photo['building_ids'])
            self.assertTrue(all(0<=v<=255 for v in profile['color']))
            self.assertGreater(profile['floor_m'],0)
            self.assertGreater(profile['bay_m'],0)

    def test_one_external_original_and_low_fallback(self):
        folder=ROOT/'data/derived/station-photo-pilot'
        config=json.loads((folder/'pilot.json').read_text(encoding='utf-8'))
        self.assertTrue((folder/'official.jpg').is_file())
        self.assertEqual(hashlib.sha256((folder/config['jpeg']).read_bytes()).hexdigest(),config['sha256'])
        self.assertLessEqual(max(config['low_size']),512)
        self.assertGreater(max(config['size']),1024)
        self.assertGreater(config['far_m'],config['near_m'])
        self.assertEqual(config['area']['half_size_m']*2,100)
        self.assertIn('EPSG:6677',config['projected_crs'])

    def test_ten_official_photos_match_materials_and_source_hashes(self):
        folder=ROOT/'data/derived/station-photo-pilot'
        config=json.loads((folder/'stream.json').read_text(encoding='utf-8'))
        self.assertEqual(len(config['photos']),10)
        self.assertEqual(len({p['photo_id'] for p in config['photos']}),10)
        self.assertGreaterEqual(len({i for p in config['photos'] for i in p['building_ids']}),10)
        self.assertEqual(config['area']['half_size_m'],50)
        self.assertLessEqual(sum(p['size'][0]*p['size'][1]*4*4/3 for p in config['photos']),config['budget_mib']*1048576)
        for photo in config['photos']:
            self.assertEqual(hashlib.sha256((folder/photo['jpeg']).read_bytes()).hexdigest(),photo['sha256'])
            self.assertTrue(photo['building_ids'])
            self.assertTrue(photo['material'].startswith('PLATEAU_Photo_'))
            self.assertLessEqual(max(photo['low_size']),512)

    def test_full_stream_maps_all_official_photos_without_preloading_them(self):
        folder=ROOT/'data/derived/station-photo-pilot'
        config=json.loads((folder/'stream-full.json').read_text(encoding='utf-8'))
        source_folder=ROOT/'data/derived/fukushima-station-lod2-overlay'
        source_manifest=json.loads((source_folder/'source_photos.json').read_text(encoding='utf-8'))
        source_hashes={p['sha256'] for p in source_manifest['files']}
        self.assertEqual(len(config['photos']),len(source_hashes))
        self.assertEqual(len({p['photo_id'] for p in config['photos']}),117)
        self.assertEqual(config['area']['half_size_m'],150)
        self.assertEqual(sum(p['size']!=p['low_size'] for p in config['photos']),66)
        self.assertGreater(config['far_m'],config['near_m'])
        self.assertGreater(sum(p['size'][0]*p['size'][1]*4*4/3 for p in config['photos']),
                           config['budget_mib']*1048576)
        for photo in config['photos']:
            self.assertIn(photo['sha256'],source_hashes)
            self.assertEqual(hashlib.sha256((folder/photo['jpeg']).read_bytes()).hexdigest(),photo['sha256'])
            self.assertLessEqual(max(photo['low_size']),512)

    def test_streamed_material_geometry_and_uv_equal_high_glb(self):
        folder=ROOT/'data/derived/fukushima-station-lod2-overlay'
        stream=json.loads((ROOT/'data/derived/station-photo-pilot/stream.json').read_text(encoding='utf-8'))
        tiles=json.loads((folder/'tileset.json').read_text(encoding='utf-8'))

        def material_geometry(path,material_name):
            blob=path.read_bytes()
            length=struct.unpack_from('<I',blob,12)[0]
            data=json.loads(blob[20:20+length])
            start=28+length
            material_id=next(i for i,m in enumerate(data['materials']) if m['name']==material_name)
            results=[]
            for mesh in data['meshes']:
                for primitive in mesh['primitives']:
                    if primitive.get('material')!=material_id:
                        continue
                    chunks=[]
                    for key in ('POSITION','TEXCOORD_0','indices'):
                        accessor_id=primitive['indices'] if key=='indices' else primitive['attributes'][key]
                        accessor=data['accessors'][accessor_id]
                        view=data['bufferViews'][accessor['bufferView']]
                        offset=start+view.get('byteOffset',0)
                        chunks.append(blob[offset:offset+view['byteLength']])
                    results.append(tuple(hashlib.sha256(c).hexdigest() for c in chunks))
            return results

        for photo in stream['photos']:
            tile=next(t for t in tiles['tiles'] if t['id']==photo['tile_id'])
            low=material_geometry(folder/tile['lod2_low']['path'],photo['material'])
            high=material_geometry(folder/tile['lod2_high']['path'],photo['material'])
            self.assertTrue(low,photo['photo_id'])
            self.assertEqual(low,high,photo['photo_id'])

