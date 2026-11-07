"""Enhance two photographed facades within their actual mesh UV polygons.

Only the identified facade islands are edited. Requires Pillow at build time.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from station_facade_enhance import enhance_surface

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/derived/station-photo-pilot'


def build():
    manifest = json.loads((FOLDER / 'stream-full.json').read_text(encoding='utf-8'))
    for prefix in ('4a2330b6', '797d465f'):
        photo = next(p for p in manifest['photos'] if p['photo_id'].startswith(prefix))
        path = FOLDER / photo['jpeg']
        if hashlib.sha256(path.read_bytes()).hexdigest() != photo['sha256']:
            raise ValueError('Source JPEG hash mismatch: ' + photo['photo_id'])
        original = Image.open(path).convert('RGB')
        if original.size != (1024, 2048):
            raise ValueError('Unexpected dimensions: ' + photo['photo_id'])
        if prefix == '4a2330b6':
            polygon = [(784.8,183.7),(70.2,194.5),(3.4,13.7),(705.9,3.1)]
            crop = (20, 38, 780, 196)
        else:
            polygon = [(221.2,200.9),(184.9,576.3),(50.8,522.7),(61.0,186.4)]
            crop = (48, 190, 175, 560)
        result = enhance_surface(original, polygon)
        dest = FOLDER / f'redrawn-{prefix}.png'
        result.save(dest, optimize=True)
        source_crop, redraw_crop = original.crop(crop), result.crop(crop)
        out = Image.new('RGB', (source_crop.width*2, source_crop.height+25), (18, 32, 38))
        out.paste(source_crop, (0, 25)); out.paste(redraw_crop, (source_crop.width, 25))
        label = ImageDraw.Draw(out)
        label.text((5, 6), 'Original photo', fill='white')
        label.text((source_crop.width+5, 6), 'Photo detail enhancement', fill='white')
        out.save(ROOT / f'docs/evidence/station_redrawn_{prefix}_comparison.png')
        print(prefix, photo['building_ids'][0], photo['material'], dest.stat().st_size)


if __name__ == '__main__':
    build()
