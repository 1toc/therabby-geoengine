"""Record the 56 building photo-atlas redraws and their UV coverage QA."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path('dist/real/fukushima-east')
    jobs = json.loads((root / 'redraw_atlas_jobs.json').read_text(encoding='utf-8'))
    qa = json.loads((root / 'redraw_atlases_aligned/coverage.json').read_text(encoding='utf-8'))
    qa_by_building = {item['building_id']: item for item in qa}
    if len(jobs) != 56 or len(qa_by_building) != 56:
        raise ValueError('All 56 buildings must have a registered atlas')
    atlases = []
    for job in jobs:
        item = qa_by_building[job['building_id']]
        if item['black_gap_samples'] or not item['valid_samples']:
            raise ValueError(f"Atlas UV coverage failed: {job['building_id']}")
        source = Path(job['source'])
        aligned = Path(item['aligned'])
        generated = Path(job['destination'])
        encoded = Path(item['encoded'])
        if not all(p.is_file() for p in (source, aligned, generated, encoded)):
            raise FileNotFoundError(job['building_id'])
        atlases.append({
            'building_id': job['building_id'],
            'uri': job['uri'],
            'texture': 'redraw_atlases_aligned/' + encoded.name,
            'generated_texture': 'redraw_atlases/' + generated.name,
            'source_photo_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'aligned_sha256': hashlib.sha256(aligned.read_bytes()).hexdigest(),
            'encoded_sha256': hashlib.sha256(encoded.read_bytes()).hexdigest(),
            'pre_fill_black_gap_fraction': item['pre_fill_black_gap_fraction'],
            'fallback_pixel_fraction': item['fallback_pixel_fraction'],
            'valid_uv_samples': item['valid_samples'],
        })
    manifest = {
        'method': 'Built-in imagegen photo-reference edit of each official building UV atlas; spatially registered to source atlas and black gaps filled at boundaries from original photo.',
        'status': 'All 56 building atlases covered; inferred details are not surveyed or verified against current street photography.',
        'source_license': 'Official PLATEAU 2025 building photographs; see map.json provenance and dataset terms.',
        'imagegen_prompt': ('Edit the attached real PLATEAU CityGML building photographic UV atlas into a crisp, high-detail architectural texture atlas for the same 3D model. Keep the complete canvas aspect ratio, pure black unused background, and exact normalized positions, sizes, edges, orientations, and order of all non-black photo islands. Within those islands, redraw the actually visible windows, doors, walls, roofs, signs, railings, equipment, shadows, and colors with sharp realistic linework. Remove blur and JPEG noise. Do not invent a regular window grid, extra floors, new objects, signs, or legible text. Do not recompose the scene, crop, merge, move, or rotate islands. This must work as a direct UV atlas replacement.'),
        'atlases': atlases,
    }
    output = root / 'redraw_atlas_manifest.json'
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(output, 'atlases', len(atlases))


if __name__ == '__main__':
    main()
