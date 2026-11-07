"""Extract official JPEGs for ten-photo trial and station-wide lazy loading."""
import hashlib
import json
from pathlib import Path
from audit_station_texture_v02 import glb_images

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/derived/fukushima-station-lod2-overlay'
OUT = ROOT / 'data/derived/station-photo-pilot'


def build():
    manifest = json.loads((SOURCE / 'tileset.json').read_text(encoding='utf-8'))
    area = {**manifest['area'], 'half_size_m': 50}
    sources = {Path(p['uri']).stem: p for p in json.loads((SOURCE / manifest['source_photos']).read_text(encoding='utf-8'))['files']}
    candidates = []
    for tile in manifest['tiles']:
        high, images = glb_images(SOURCE / tile['lod2_high']['path'])
        low, low_images = glb_images(SOURCE / tile['lod2_low']['path'])
        low_materials = {m['name'] for m in low['materials']}
        scene = json.loads((SOURCE / tile['scene']).read_text(encoding='utf-8'))
        building_ids = {}
        for building in scene['buildings']:
            for surface in building['lod2_surfaces']:
                uri = surface.get('texture_uri')
                if uri:
                    building_ids.setdefault(Path(uri).stem, set()).add(building['id'])
        for material_id, material in enumerate(high['materials']):
            texture = material.get('pbrMetallicRoughness', {}).get('baseColorTexture')
            if texture is None or material['name'] not in low_materials:
                continue
            name = high['images'][high['textures'][texture['index']]['source']]['name']
            if name not in building_ids or name not in sources or name not in low_images:
                continue
            accessors = [high['accessors'][primitive['attributes']['POSITION']]
                         for mesh in high['meshes'] for primitive in mesh['primitives']
                         if primitive.get('material') == material_id]
            if not accessors:
                continue
            x0 = min(a['min'][0] for a in accessors) + tile['tile_origin_east_m']
            x1 = max(a['max'][0] for a in accessors) + tile['tile_origin_east_m']
            n0 = tile['tile_origin_north_m'] - max(a['max'][2] for a in accessors)
            n1 = tile['tile_origin_north_m'] - min(a['min'][2] for a in accessors)
            center = ((x0+x1)/2, (n0+n1)/2)
            distance = (center[0]-area['center_east_m'])**2 + (center[1]-area['center_north_m'])**2
            candidates.append((distance, name, material['name'], tile['id'], (x0,n0,x1,n1),
                               sorted(building_ids[name]), images[name], low_images[name], tile['lod2_low']['path']))
    candidates.sort(key=lambda c: c[0])
    def select(full):
        photos, selected_buildings, selected_names = [], set(), set()
        for unique_only in (True, False):
            for _, name, material, tile_id, bounds, ids, image, low, low_glb in candidates:
                if not full and len(photos) == 10:
                    break
                if not full and (bounds[2] < area['center_east_m'] - 50 or bounds[0] > area['center_east_m'] + 50 or
                                 bounds[3] < area['center_north_m'] - 50 or bounds[1] > area['center_north_m'] + 50):
                    continue
                if name in selected_names or unique_only and all(i in selected_buildings for i in ids):
                    continue
                source = sources[name]
                raw = image['bytes']
                if hashlib.sha256(raw).hexdigest() != source['sha256']:
                    raise ValueError(f'Official JPEG differs from source: {name}')
                filename = f'{name}.jpg'
                OUT.mkdir(parents=True, exist_ok=True)
                (OUT / filename).write_bytes(raw)
                photos.append({'photo_id': name, 'building_ids': ids, 'material': material,
                               'tile_id': tile_id, 'jpeg': filename, 'sha256': source['sha256'],
                               'byte_length': len(raw), 'size': image['size'], 'low_size': low['size'],
                               'bbox_east_north_m': bounds, 'source_uri': source['uri'],
                               'low_glb': low_glb})
                selected_names.add(name)
                selected_buildings.update(ids)
            if full or len(photos) == 10:
                break
        expected = len(sources) if full else 10
        if len(photos) != expected:
            raise ValueError(f'Only {len(photos)} of {expected} photos mapped to an independent material')
        result = {'schema': 'therabby.station-photo-stream.v0.3',
                  'area': manifest['area'] if full else area,
                  'projected_crs': manifest['projected_crs'], 'vertical_frame': manifest['render_vertical_frame'],
                  'source': 'Project PLATEAU / Fukushima City 2025',
                  'near_m': 90 if full else 35, 'far_m': 130 if full else 55,
                  'max_concurrent': 3, 'budget_mib': 128,
                  'photos': photos}
        (OUT / ('stream-full.json' if full else 'stream.json')).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'mode': 'full' if full else 'ten', 'photos': len(photos),
                          'buildings': len(selected_buildings), 'bytes': sum(p['byte_length'] for p in photos),
                          'estimated_mib': round(sum(p['size'][0]*p['size'][1]*4*4/3 for p in photos)/1048576, 2)},
                         ensure_ascii=False))
        return result
    pilot = select(False)
    select(True)
    return pilot


if __name__ == '__main__':
    build()
