"""Split an existing Fukushima 200m Blender city into four UV-preserving GLB tiles.

Run inside Blender. This prototype keeps the existing local coordinates in every
tile. Citywide production needs a projected CRS and tile-local float32 origins.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tile_math import tile_bounds, clip_roads


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clip_polygon(vertices, bounds):
    """Clip (position, UV) tuples in map X/Z, interpolating all attributes."""
    x0,z0,x1,z1 = bounds
    def coordinate(item, axis):
        return item[0].x if axis == 'x' else -item[0].y
    for axis,limit,keep_above in (('x',x0,True),('x',x1,False),('z',z0,True),('z',z1,False)):
        if not vertices:
            break
        out = []
        previous = vertices[-1]
        p_value = coordinate(previous,axis)
        p_inside = p_value >= limit-1e-8 if keep_above else p_value <= limit+1e-8
        for current in vertices:
            c_value = coordinate(current,axis)
            c_inside = c_value >= limit-1e-8 if keep_above else c_value <= limit+1e-8
            if p_inside != c_inside:
                t = (limit-p_value)/(c_value-p_value)
                position = previous[0].lerp(current[0],t)
                uv = previous[1].lerp(current[1],t)
                if axis == 'x':
                    position.x = limit
                else:
                    position.y = -limit
                out.append((position,uv))
            if c_inside:
                out.append(current)
            previous,p_value,p_inside = current,c_value,c_inside
        vertices = out
    return vertices


def clipped_mesh_object(source, tile):
    mesh = source.data
    uv_layer = mesh.uv_layers.active
    vertices,uvs,faces = [],[],[]
    for polygon in mesh.polygons:
        if polygon.material_index != 0:
            raise ValueError(f'Multiple materials on {source.name} are not supported by prototype')
        original = [(source.matrix_world @ mesh.vertices[mesh.loops[i].vertex_index].co,
                     uv_layer.data[i].uv.copy() if uv_layer else Vector((0,0)))
                    for i in polygon.loop_indices]
        for i in range(1,len(original)-1):
            clipped = clip_polygon([original[0],original[i],original[i+1]],tile['bounds'])
            if len(clipped)<3:
                continue
            for j in range(1,len(clipped)-1):
                triangle = (clipped[0],clipped[j],clipped[j+1])
                if (triangle[1][0]-triangle[0][0]).cross(triangle[2][0]-triangle[0][0]).length < 1e-7:
                    continue
                offset = len(vertices)
                vertices.extend(tuple(point[0]) for point in triangle)
                uvs.extend(tuple(point[1]) for point in triangle)
                faces.append((offset,offset+1,offset+2))
    if not faces:
        return None
    result_mesh = bpy.data.meshes.new(f'{source.name}_tile_{tile["id"]}')
    result_mesh.from_pydata(vertices,[],faces)
    result_mesh.update()
    if source.material_slots and source.material_slots[0].material:
        result_mesh.materials.append(source.material_slots[0].material)
    if uv_layer:
        result_uv = result_mesh.uv_layers.new(name=uv_layer.name)
        for polygon in result_mesh.polygons:
            for loop_index in polygon.loop_indices:
                index = result_mesh.loops[loop_index].vertex_index
                result_uv.data[loop_index].uv = uvs[index]
    result = bpy.data.objects.new(result_mesh.name,result_mesh)
    bpy.context.scene.collection.objects.link(result)
    for key,value in source.items():
        result[key] = value
    result['geoengine_tile_id'] = tile['id']
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-blend',required=True)
    parser.add_argument('--source-map',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--tile-size',type=int,default=100)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    source_blend = Path(args.source_blend).resolve()
    map_path = Path(args.source_map).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir == source_blend.parent or output_dir == map_path.parent:
        raise ValueError('Tile outputs must be in a separate directory')
    map_data = json.loads(map_path.read_text(encoding='utf-8'))
    if map_data.get('schema') != 'therabby.geoengine.map.v0.1':
        raise ValueError('Unsupported source map schema')
    half_size = map_data['area']['half_size_m']
    if half_size != 100 or args.tile_size != 100:
        raise ValueError('This prototype is validated only for the current 200m area and 100m tiles')
    bpy.ops.wm.open_mainfile(filepath=str(source_blend))
    visual_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH' and
                      obj.get('geoengine_schema') == map_data['schema']]
    if not visual_objects:
        raise ValueError('No GeoEngine visual objects in source .blend')
    source_glb = source_blend.with_suffix('.glb')
    if not source_glb.is_file():
        raise FileNotFoundError(source_glb)
    output_dir.mkdir(parents=True,exist_ok=True)
    tiles = []
    for tile in tile_bounds(half_size,args.tile_size):
        created = [item for source in visual_objects if (item := clipped_mesh_object(source,tile))]
        if not created:
            raise ValueError(f'Empty tile {tile["id"]}')
        bpy.ops.object.select_all(action='DESELECT')
        for obj in created:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = created[0]
        glb = output_dir / f'tile_{tile["id"]}.glb'
        bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',export_apply=True,
                                  export_yup=True,export_cameras=False,export_lights=False,
                                  export_extras=True,use_selection=True)
        roads = clip_roads(map_data['roads'],tile['bounds'],half_size)
        roads_path = output_dir / f'roads_{tile["id"]}.json'
        roads_path.write_text(json.dumps({'schema':'therabby.geoengine.roads.tile.v0.1',
            'tile_id':tile['id'],'bounds':tile['bounds'],'roads':roads},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        tile_record = {'id':tile['id'],'ix':tile['ix'],'iz':tile['iz'],
            'bounds':tile['bounds'],'glb':glb.name,'roads':roads_path.name,
            'bytes':glb.stat().st_size,'sha256':sha256(glb),
            'mesh_count':len(created),'triangles':sum(len(obj.data.polygons) for obj in created),
            'road_fragments':len(roads),
            'visual_quality':'photo-reference-repaint-inferred',
            'geometry_source':'PLATEAU 2025 LOD2',
            'ground_source':'PLATEAU-Ortho 2024'}
        tiles.append(tile_record)
        for obj in created:
            mesh = obj.data
            bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.meshes.remove(mesh)
        print(f'TILE {tile["id"]}: {glb.stat().st_size:,} bytes, {tile_record["triangles"]} triangles, {len(roads)} road fragments')
    manifest = {'schema':'therabby.geoengine.tileset.prototype.v0.1',
        'scope':'Fukushima Station east 200m only; not citywide projected CRS',
        'area':map_data['area'],'coordinate_system':map_data['coordinate_system'],
        'tile_size_m':args.tile_size,'bounds':[-half_size,-half_size,half_size,half_size],
        'source_model':source_glb.name,'source_model_sha256':sha256(source_glb),
        'source_map':map_path.name,'source_map_sha256':sha256(map_path),
        'provenance':map_data.get('provenance',[]),'tiles':tiles}
    (output_dir/'tileset.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'SUCCESS {len(tiles)} tiles in {output_dir}')


if __name__ == '__main__':
    main()
