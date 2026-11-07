"""Reproject the existing crisp 200m Blender scene into the 1km projected grid."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from geoengine import METERS_PER_DEG_LAT, load_area, xy_of


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-blend',required=True)
    parser.add_argument('--source-area',required=True)
    parser.add_argument('--wide-area',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    source=load_area(args.source_area);wide=load_area(args.wide_area)
    if source['center_lat']!=wide['center_lat'] or source['center_lon']!=wide['center_lon']:
        raise ValueError('Core and wide origins differ')
    bpy.ops.wm.open_mainfile(filepath=str(Path(args.source_blend).resolve()))
    selected=[]
    for obj in bpy.data.objects:
        if obj.type!='MESH' or obj.get('geoengine_schema')!='therabby.geoengine.map.v0.1':
            continue
        transform=obj.matrix_world.copy()
        for vertex in obj.data.vertices:
            old=transform@vertex.co
            lat=source['center_lat']+old.y/METERS_PER_DEG_LAT
            lon=source['center_lon']+old.x/(METERS_PER_DEG_LAT*math.cos(math.radians(source['center_lat'])))
            x,z=xy_of(lat,lon,wide)
            vertex.co=(x,-z,old.z)
        obj.matrix_world=Matrix.Identity(4)
        obj['geoengine_projection']='JGD2011_JPRCS_IX_GRS80'
        selected.append(obj)
    if not selected:raise ValueError('No GeoEngine visual meshes in source blend')
    out=Path(args.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in selected:obj.select_set(True)
    bpy.context.view_layer.objects.active=selected[0]
    bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',
        export_apply=True,export_yup=True,export_cameras=False,
        export_lights=False,export_extras=True,use_selection=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out.with_suffix('.blend')))
    sidecar={'asset':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
        'source_blend':Path(args.source_blend).name,
        'method':'Inverse local equirectangular then GRS80 TM per vertex; UVs unchanged',
        'source_visual_quality':'PLATEAU LOD2 plus AI photo-reference repaint; fine details unverified',
        'vertical_datum':'local flattened zero; terrain elevation unavailable',
        'mesh_count':len(selected)}
    out.with_suffix('.provenance.json').write_text(json.dumps(sidecar,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'SUCCESS {out} {out.stat().st_size} bytes, {len(selected)} meshes',flush=True)


if __name__=='__main__':main()
