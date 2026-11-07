"""Build a photo-based facade enhancement with unchanged atlas dimensions.

The mask follows the actual mesh UV polygon. Requires Pillow at build time.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from station_facade_enhance import enhance_surface

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/derived/station-photo-pilot'
PHOTO_ID = 'a4fdf53b-4765-4cbc-ae1b-92f25562ddc1'


def build():
    manifest = json.loads((FOLDER / 'stream-full.json').read_text(encoding='utf-8'))
    item = next(p for p in manifest['photos'] if p['photo_id'] == PHOTO_ID)
    original = FOLDER / item['jpeg']
    if hashlib.sha256(original.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('Source JPEG does not match the official manifest')
    source = Image.open(original).convert('RGB')
    if source.size != (1024, 2048):
        raise ValueError('Unexpected atlas dimensions')
    # Exact facade UV corners from lod2_low_55_194.glb, scaled to pixels.
    result = enhance_surface(source, [(2.5,14.2),(31.5,261.9),(734.2,251.0),(720.8,3.0)])
    destination = FOLDER / 'redrawn-a4fdf53b.png'
    result.save(destination, optimize=True)
    crop=(130, 45, 665, 225)
    comparison=Image.new('RGB', (1070, 205), (18, 32, 38))
    comparison.paste(source.crop(crop), (0, 25))
    comparison.paste(result.crop(crop), (535, 25))
    text=ImageDraw.Draw(comparison)
    text.text((8, 6), 'Official photo - original', fill='white')
    text.text((543, 6), 'Photo-based detail enhancement', fill='white')
    comparison.save(ROOT / 'docs/evidence/station_redrawn_pilot_source_comparison.png')
    print(f'{destination}: building {item["building_ids"][0]}, material {item["material"]}')


if __name__ == '__main__':
    build()
