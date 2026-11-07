"""Extract the rendered citywide DEM triangles covering the station preview.

These heights reproduce the displayed mesh, not measured road elevations.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/derived/fukushima-citywide-terrain-meshes'
ROAD = ROOT / 'data/derived/fukushima-station-roads-v02/road_extent.json'
OUT = ROAD.with_name('visual_terrain.json')


def build():
    data = json.loads(ROAD.read_text(encoding='utf-8'))
    manifest_path = SOURCE / 'tileset.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['vertical_datum'] != 'T.P. (Tokyo Peil)' or 'EPSG:6677' not in manifest['projected_crs']:
        raise ValueError('Unsupported rendered terrain coordinates')
    east, north = data['center_east_m'], data['center_north_m']
    triangles, sources = [], []
    for tile in manifest['tiles']:
        if abs(tile['tile_origin_east_m'] - east) > 1500 or abs(tile['tile_origin_north_m'] - north) > 1500:
            continue
        raw = (SOURCE / tile['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != tile['sha256']:
            raise ValueError('Terrain source hash mismatch: ' + tile['id'])
        mesh = json.loads(raw)
        n, vertices = mesh['grid_cells'], mesh['vertices_x_south_height']
        used = False
        for row in range(n):
            for col in range(n):
                a = row * (n + 1) + col
                for indices in ((a, a+n+2, a+1), (a, a+n+1, a+n+2)):
                    points = [vertices[i] for i in indices]
                    if any(point[2] is None for point in points):
                        continue
                    points = [[round(tile['tile_origin_east_m'] + x - east, 6),
                               round(north - tile['tile_origin_north_m'] + z, 6), h]
                              for x, z, h in points]
                    if max(p[0] for p in points) < -150 or min(p[0] for p in points) > 150 or \
                       max(p[1] for p in points) < -150 or min(p[1] for p in points) > 150:
                        continue
                    triangles.append(points)
                    used = True
        if used:
            sources.append({'tile_id': tile['id'], 'sha256': tile['sha256']})
    if not triangles:
        raise ValueError('No rendered terrain in station area')
    return {'schema': 'therabby.geoengine.station-visual-terrain.v1',
            'projected_crs': 'EPSG:6677', 'vertical_datum': 'T.P. (Tokyo Peil)',
            'center_east_m': east, 'center_north_m': north,
            'quality': 'rendered GSI DEM5A mesh; not measured road elevation',
            'sources': sources, 'triangles': triangles}


if __name__ == '__main__':
    OUT.write_text(json.dumps(build(), ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(OUT)
