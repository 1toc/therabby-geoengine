"""Identify the PLATEAU wall under sample rays from the road comparison camera."""
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector, geometry


def face_ranges(map_data, atlas_manifest, wall_manifest):
    atlas_by_uri = {item['uri']: Path(item['texture']).stem for item in atlas_manifest['atlases']}
    direct = {(item['building_id'], item['surface_index']): Path(item['texture']).stem
              for item in wall_manifest['walls']}
    ranges = {}
    counts = {}
    for building in map_data['buildings']:
        for index, surface in enumerate(building.get('lod2_surfaces', [])):
            uri = surface.get('texture_uri')
            if not uri:
                continue
            stem = direct.get((building['id'], index), atlas_by_uri.get(uri))
            if not stem:
                continue
            name = 'City_Texture_' + stem[:24]
            loops = [[Vector((float(x), -float(z), float(y))) for x, z, y in ring]
                     for ring in surface['rings']]
            count = len(geometry.tessellate_polygon(loops))
            start = counts.get(name, 0)
            ranges.setdefault(name, []).append((start, start + count, building['id'], index, surface))
            counts[name] = start + count
    return ranges


def main():
    root = Path(__file__).resolve().parents[1]
    asset = root / 'dist/real/fukushima-east'
    map_data = json.loads((asset / 'map.json').read_text(encoding='utf-8'))
    atlases = json.loads((asset / 'redraw_atlas_1536_q88.json').read_text(encoding='utf-8'))
    walls = json.loads((asset / 'redraw_manifest.json').read_text(encoding='utf-8'))
    ranges = face_ranges(map_data, atlases, walls)
    bpy.ops.wm.open_mainfile(filepath=str(asset / 'city_photo_optimized.blend'))
    camera = Vector((-70, -75, 1.7))
    target = Vector((-45, 80, 8))
    rotation = (target - camera).to_track_quat('-Z', 'Y')
    half_height = math.tan(math.radians(52 / 2))
    half_width = half_height * 16 / 9
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for u, v in ((u,v) for v in (.2,.35,.5,.65) for u in (.4,.5,.6,.7,.8,.82,.84,.86,.88,.9,.95,.98)):
        direction = rotation @ Vector(((2*u-1)*half_width, (1-2*v)*half_height, -1))
        hit, location, normal, face, obj, _ = bpy.context.scene.ray_cast(depsgraph, camera, direction.normalized())
        if not hit:
            print(f'{u:.2f},{v:.2f} empty')
            continue
        match = next(((bid, idx, s) for start, end, bid, idx, s in ranges.get(obj.name, [])
                      if start <= face < end), None)
        if match:
            bid, idx, surface = match
            print(f'{u:.2f},{v:.2f} {obj.name} face={face} {bid} surface={idx} type={surface["type"]} photo={surface.get("texture_uri")} hit={tuple(round(x,2) for x in location)}')
        else:
            print(f'{u:.2f},{v:.2f} {obj.name} face={face} hit={tuple(round(x,2) for x in location)}')


if __name__ == '__main__':
    main()
