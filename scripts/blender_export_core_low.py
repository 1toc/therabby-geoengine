"""Export the 56 central PLATEAU buildings as a compact LOD1 fallback."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parent))
from blender_export_wide_tiles import facade_meshes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wide-map',required=True)
    parser.add_argument('--core-map',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--terrain-grid',help='GSI DEM5A ground grid for building base heights')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    wide=json.loads(Path(args.wide_map).read_text(encoding='utf-8'))
    core=json.loads(Path(args.core_map).read_text(encoding='utf-8'))
    ids={b['id'] for b in core['buildings']}
    selected=[b for b in wide['buildings'] if b['id'] in ids]
    if len(selected)!=len(ids):raise ValueError('Core IDs absent from wide map')
    terrain_grid=json.loads(Path(args.terrain_grid).read_text(encoding='utf-8')) if args.terrain_grid else None
    if terrain_grid and (terrain_grid['schema']!='therabby.geoengine.terrain-grid.v0.1'
                         or terrain_grid['area_id']!=wide['area']['id']):
        raise ValueError('Core low terrain grid area/schema mismatch')
    objects,stats=facade_meshes(selected,(0,0),set(),wide['roads'],terrain_grid)
    if not objects:raise ValueError('Empty core')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj['geoengine_schema']='therabby.geoengine.tileset.wide.v0.1'
        obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    out=Path(args.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',
        export_apply=True,export_yup=True,export_cameras=False,
        export_lights=False,export_extras=True,use_selection=True)
    out.with_suffix('.provenance.json').write_text(json.dumps({
        'asset':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
        'source':'PLATEAU LOD1','buildings':len(selected),
        'facade_estimate':stats,
        'terrain_source':'GSI DEM5A ground' if terrain_grid else 'flat visual plane',
        'visual_quality':'procedural facade estimates, not photographic'},indent=2)+'\n',encoding='utf-8')
    print(f'SUCCESS {out}: {len(selected)} buildings, {out.stat().st_size} bytes')


if __name__=='__main__':main()
