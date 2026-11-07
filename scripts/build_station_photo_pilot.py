"""Extract exactly one official JPEG; retain the existing Low GLB as fallback."""
import hashlib
import json
from pathlib import Path
from audit_station_texture_v02 import glb_images

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/derived/fukushima-station-lod2-overlay'
OUT = ROOT / 'data/derived/station-photo-pilot'

def build():
    manifest = json.loads((SOURCE / 'tileset.json').read_text(encoding='utf-8'))
    tile = manifest['tiles'][0]
    high, images = glb_images(SOURCE / tile['lod2_high']['path'])
    low, low_images = glb_images(SOURCE / tile['lod2_low']['path'])
    candidates = []
    for material in high['materials']:
        texture = material.get('pbrMetallicRoughness', {}).get('baseColorTexture')
        if texture is None:
            continue
        image = high['images'][high['textures'][texture['index']]['source']]
        name = image['name']
        if max(images[name]['size']) > 1024 and any(m.get('name') == material.get('name') for m in low['materials']):
            mi = high['materials'].index(material)
            bounds = [high['accessors'][p['attributes']['POSITION']] for mesh in high['meshes'] for p in mesh['primitives'] if p.get('material') == mi]
            x = sum((a['min'][0]+a['max'][0])/2 for a in bounds)/len(bounds)
            z = sum((a['min'][2]+a['max'][2])/2 for a in bounds)/len(bounds)
            east, north = tile['tile_origin_east_m']+x, tile['tile_origin_north_m']-z
            distance = (east-manifest['area']['center_east_m'])**2+(north-manifest['area']['center_north_m'])**2
            candidates.append((distance, material['name'], name))
    _, material, name = min(candidates)
    raw = images[name]['bytes']
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'official.jpg').write_bytes(raw)
    result = {'schema':'therabby.station-photo-pilot.v0.3', 'material':material,
        'image_name':name, 'tile_id':tile['id'], 'jpeg':'official.jpg',
        'sha256':hashlib.sha256(raw).hexdigest(), 'byte_length':len(raw),
        'size':images[name]['size'], 'low_size':low_images[name]['size'],
        'near_m':35, 'far_m':55, 'area':{**manifest['area'], 'half_size_m':50},
        'source':'Project PLATEAU / Fukushima City 2025; same original bytes as source High GLB',
        'projected_crs':manifest['projected_crs'], 'vertical_frame':manifest['render_vertical_frame'],
        'fallback_glb':tile['lod2_low']['path']}
    (OUT / 'pilot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__ == '__main__':
    build()
