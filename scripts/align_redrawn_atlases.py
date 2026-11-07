"""Register AI-repainted PLATEAU atlases to the immutable source UV layout.

This performs spatial registration only. Creative repainting is done by imagegen.
Generated atlases and official JPEGs remain untouched; aligned copies are saved
separately. A coverage report flags atlases whose UV islands have black gaps.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def occupied_bbox(image, ignore_white=False):
    rgb = np.asarray(image.convert('RGB'))
    mask = np.max(rgb, axis=2) > 25
    if ignore_white:
        mask &= np.min(rgb, axis=2) < 230
    fraction = .01 if ignore_white else .002
    floor = 8 if ignore_white else 2
    rows = np.flatnonzero(np.sum(mask, axis=1) > max(floor, round(image.width * fraction)))
    cols = np.flatnonzero(np.sum(mask, axis=0) > max(floor, round(image.height * fraction)))
    if not len(rows) or not len(cols):
        raise ValueError('Atlas has no visible texture islands')
    return (int(cols[0]), int(rows[0]), int(cols[-1] + 1), int(rows[-1] + 1))


def remove_white_border_background(image):
    """Imagegen occasionally changes the atlas's black margin to white."""
    image = image.copy().convert('RGB')
    for point in ((0, 0), (image.width - 1, 0),
                  (0, image.height - 1), (image.width - 1, image.height - 1)):
        if min(image.getpixel(point)) > 235:
            ImageDraw.floodfill(image, point, (0, 0, 0), thresh=12)
    return image


def register(source, generated, ignore_white=False):
    source_bbox = occupied_bbox(source)
    generated_bbox = occupied_bbox(generated, ignore_white)
    # More pixels than both the source and generated image add memory, not detail.
    desired_edge = min(2048, max(max(source.size), max(generated.size)))
    scale = min(4, desired_edge / max(source.size))
    target_size = (round(source.width * scale), round(source.height * scale))
    target_bbox = tuple(round(value * scale) for value in source_bbox)
    crop = generated.crop(generated_bbox).resize(
        (target_bbox[2] - target_bbox[0], target_bbox[3] - target_bbox[1]),
        Image.Resampling.LANCZOS)
    aligned = Image.new('RGB', target_size, (0, 0, 0))
    aligned.paste(crop, target_bbox[:2])
    return aligned, source_bbox, generated_bbox


def fill_black_gaps(source, aligned):
    """Keep original pixels only where the generated island misses a source UV."""
    original = np.asarray(source.resize(aligned.size, Image.Resampling.BICUBIC))
    result = np.asarray(aligned).copy()
    fallback = (np.max(original, axis=2) > 25) & (np.max(result, axis=2) <= 25)
    result[fallback] = original[fallback]
    return Image.fromarray(result), round(float(np.mean(fallback)), 5)


def uv_color(image, uv):
    x = max(0, min(image.width - 1, round(uv[0] * (image.width - 1))))
    y = max(0, min(image.height - 1, round((1 - uv[1]) * (image.height - 1))))
    return image.getpixel((x, y))


def coverage(scene_building, source, aligned):
    valid = lost = 0
    missing_surfaces = []
    for index, surface in enumerate(scene_building['lod2_surfaces']):
        surface_valid = surface_lost = 0
        for ring in surface.get('texture_uv_rings', []):
            if len(ring) < 3:
                continue
            # Interior barycentric samples across the polygon's triangle fan.
            for corner in range(1, len(ring) - 1):
                a, b, c = ring[0], ring[corner], ring[corner + 1]
                for u, v in ((.15, .15), (.5, .15), (.15, .5), (.3, .3)):
                    uv = (a[0] * (1 - u - v) + b[0] * u + c[0] * v,
                          a[1] * (1 - u - v) + b[1] * u + c[1] * v)
                    if max(uv_color(source, uv)) <= 25:
                        continue
                    surface_valid += 1
                    surface_lost += max(uv_color(aligned, uv)) <= 25
        valid += surface_valid
        lost += surface_lost
        if surface_valid and surface_lost / surface_valid > .05:
            missing_surfaces.append(index)
    return {'valid_samples': valid, 'black_gap_samples': lost,
            'black_gap_fraction': round(lost / valid, 5) if valid else 0,
            'surfaces_with_gaps': missing_surfaces}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', default='dist/real/fukushima-east/map.json')
    parser.add_argument('--jobs', default='dist/real/fukushima-east/redraw_atlas_jobs.json')
    parser.add_argument('--output-dir', default='dist/real/fukushima-east/redraw_atlases_aligned')
    args = parser.parse_args()
    scene = json.loads(Path(args.scene).read_text(encoding='utf-8'))
    buildings = {b['id']: b for b in scene['buildings']}
    jobs = json.loads(Path(args.jobs).read_text(encoding='utf-8'))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = []
    for job in jobs:
        generated_path = Path(job['destination'])
        if not generated_path.is_file():
            continue
        source = Image.open(job['source']).convert('RGB')
        generated_input = Image.open(generated_path).convert('RGB')
        corner_points = ((0, 0), (generated_input.width - 1, 0),
                         (0, generated_input.height - 1),
                         (generated_input.width - 1, generated_input.height - 1))
        white_border = any(min(generated_input.getpixel(point)) > 235 for point in corner_points)
        generated = remove_white_border_background(generated_input)
        aligned, source_bbox, generated_bbox = register(source, generated, white_border)
        before_fill = coverage(buildings[job['building_id']], source, aligned)
        aligned, fallback_fraction = fill_black_gaps(source, aligned)
        aligned_path = output / generated_path.name
        aligned.save(aligned_path)
        encoded_path = aligned_path.with_suffix('.jpg')
        aligned.save(encoded_path, format='JPEG', quality=91, subsampling=0, optimize=True)
        quality = coverage(buildings[job['building_id']], source, aligned)
        report.append({'building_id': job['building_id'], 'uri': job['uri'],
                       'generated': str(generated_path), 'aligned': str(aligned_path),
                       'encoded': str(encoded_path),
                       'source_size': source.size, 'generated_size': generated.size,
                       'aligned_size': aligned.size, 'source_bbox': source_bbox,
                       'generated_bbox': generated_bbox,
                       'pre_fill_black_gap_fraction': before_fill['black_gap_fraction'],
                       'fallback_pixel_fraction': fallback_fraction, **quality})
        print(f"{job['building_id'][13:21]} {before_fill['black_gap_fraction']:.2%} initial gaps; "+
              f"{quality['black_gap_fraction']:.2%} after source-edge fallback")
    (output / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('registered', len(report), 'of', len(jobs))


if __name__ == '__main__':
    main()
