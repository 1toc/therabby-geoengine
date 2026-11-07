"""Run inside Blender to export prepared 1km LOD1/OSM/ortho GLB tiles."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector, geometry as blender_geometry

sys.path.insert(0,str(Path(__file__).resolve().parent))
from blender_export import create_mesh, image_material, material
from facade_geometry import PALETTE, build_facade_batches
from procedural_road_texture import asphalt_png
from terrain_grid import height_at


def building_mesh(buildings, source, origin, color, core_ids):
    vertices=[];faces=[]
    x0,z0=origin
    for building in buildings:
        if building['source']!=source:continue
        footprint=building['footprint']
        if len(footprint)<3:continue
        # Only exact source IDs are replaced by the detailed 200m model.
        if building['id'] in core_ids:continue
        height=float(building['height_m'])
        if not 1<=height<500:continue
        offset=len(vertices);count=len(footprint)
        vertices.extend((x-x0,-(z-z0),0) for x,z in footprint)
        vertices.extend((x-x0,-(z-z0),height) for x,z in footprint)
        faces.append(tuple(offset+count+i for i in range(count)))
        for i in range(count):
            j=(i+1)%count
            faces.append((offset+i,offset+j,offset+count+j,offset+count+i))
    if not faces:return None
    obj=create_mesh(source.replace(' ','_')+'_LOD1',vertices,faces,material(source,color))
    obj.location=(x0,-z0,0)
    obj['source']=source
    obj['visual_quality']='official_lod1_geometry_untextured' if source=='PLATEAU CityGML' else 'osm_footprint_estimated_height'
    return obj


def ground_mesh(bounds, photo, terrain_grid=None):
    x0,z0,x1,z1=bounds
    size=x1-x0
    if terrain_grid:
        step=terrain_grid['step_m'];count=int(size/step)
        vertices=[];faces=[];uvs=[]
        for iz in range(count+1):
            for ix in range(count+1):
                x,z=x0+ix*step,z0+iz*step
                vertices.append((x-x0,-(z-z0),height_at(terrain_grid,x,z)-.06))
                uvs.append((ix/count,1-iz/count))
        for iz in range(count):
            for ix in range(count):
                a=iz*(count+1)+ix;b=a+1;c=a+count+2;d=a+count+1
                faces.append((a,b,c,d))
    else:
        vertices=[(0,0,-.06),(size,0,-.06),(size,-size,-.06),(0,-size,-.06)]
        faces=[(0,1,2,3)];uvs=[(0,1),(1,1),(1,0),(0,0)]
    obj=create_mesh('PLATEAU_Ortho_2024',vertices,faces,
                    image_material('PLATEAU_Ortho_2024',photo),uvs)
    obj.location=(x0,-z0,0)
    obj['source']='PLATEAU Ortho 2024'
    obj['terrain_source']='GSI DEM5A ground' if terrain_grid else 'flat visual plane'
    return obj


def road_mesh(surfaces, origin, texture):
    vertices=[];faces=[];uvs=[];x0,z0=origin
    for surface in surfaces:
        if (surface.get('bridge','no')!='no' or surface.get('tunnel','no')!='no'
                or surface.get('layer','0')!='0'):
            continue
        polygon=surface['polygon']
        if len(polygon)<3:continue
        offset=len(vertices)
        heights=surface.get('vertex_ground_heights_m',[0]*len(polygon))
        vertices.extend((x-x0,-(z-z0),h+.018) for (x,z),h in zip(polygon,heights))
        uvs.extend((x/4,-z/4) for x,z in polygon)
        indices=tuple(offset+i for i in range(len(polygon)))
        signed=sum(vertices[indices[i]][0]*vertices[indices[(i+1)%len(indices)]][1]-
                   vertices[indices[(i+1)%len(indices)]][0]*vertices[indices[i]][1]
                   for i in range(len(indices)))
        faces.append(indices if signed>0 else tuple(reversed(indices)))
    if not faces:return None
    obj=create_mesh('Road_Drivable_Flat_Estimated_Width',vertices,faces,
                    image_material('Asphalt_Procedural_Not_Surveyed',texture),uvs)
    obj.location=(x0,-z0,0)
    obj['source']='OpenStreetMap centreline'
    obj['road_width_quality']='class-estimate'
    obj['road_elevation_quality']='flat-prototype-not-surveyed'
    obj['legal_access']='not-verified'
    return obj


def official_road_extent_mesh(extents,origin):
    """Official LOD1 road envelope; sidewalk/carriageway are not separated."""
    vertices=[];faces=[];x0,z0=origin
    for extent in extents:
        polygon=extent['polygon']
        if len(polygon)<3:continue
        heights=extent.get('drape_ground_heights_m',[0]*len(polygon))
        ring=[Vector((x-x0,-(z-z0),h+.004)) for (x,z),h in zip(polygon,heights)]
        triangles=blender_geometry.tessellate_polygon([ring])
        offset=len(vertices)
        vertices.extend(tuple(point) for point in ring)
        faces.extend(tuple(offset+index for index in triangle)
                     for triangle in triangles)
    if not faces:return None
    obj=create_mesh('PLATEAU_Road_LOD1_Extent_Not_Carriageway',vertices,faces,
                    material('PLATEAU_Road_Extent',(.32,.34,.33)))
    obj.location=(x0,-z0,0)
    obj['source']='PLATEAU CityGML transportation Road LOD1'
    obj['visual_quality']='official extent; carriageway, grade and lanes unknown'
    obj['collision_ready']=False
    return obj


def marking_mesh(roads,origin,terrain_grid=None):
    """Illustrative centre dashes on broad roads; no lane/legal semantics."""
    vertices=[];faces=[];x0,z0=origin
    def ground(x,z):
        if not terrain_grid:return 0
        left,top,right,bottom=terrain_grid['bounds']
        return height_at(terrain_grid,max(left,min(right,x)),max(top,min(bottom,z)))
    for road in roads:
        if (road.get('bridge','no')!='no' or road.get('tunnel','no')!='no'
                or road.get('layer','0')!='0'):
            continue
        if road['width_m']<7 or road['highway'] not in {'primary','secondary','tertiary'}:
            continue
        for a,b in zip(road['points'],road['points'][1:]):
            dx,dz=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dz)
            if length<.5:continue
            ux,uz=dx/length,dz/length
            nx,nz=-uz*.045,ux*.045
            start=0
            while start<length:
                end=min(start+2.2,length)
                if end-start>.35:
                    p=(a[0]+ux*start,a[1]+uz*start)
                    q=(a[0]+ux*end,a[1]+uz*end)
                    offset=len(vertices)
                    vertices.extend((x-x0,-(z-z0),
                                     ground(x,z)+.045)
                                    for x,z in
                                    ((p[0]+nx,p[1]+nz),(p[0]-nx,p[1]-nz),
                                     (q[0]-nx,q[1]-nz),(q[0]+nx,q[1]+nz)))
                    faces.append((offset,offset+1,offset+2,offset+3))
                start+=5.8
    if not faces:return None
    obj=create_mesh('Road_Marking_Illustrative_Not_Lanes',vertices,faces,
                    material('Road_Marking_Pale',(.72,.72,.65)))
    obj.location=(x0,-z0,0)
    obj['visual_quality']='illustrative centre dashes; no verified lane layout'
    return obj


def facade_meshes(buildings,origin,core_ids,roads,terrain_grid=None):
    edge_clamped=0
    if terrain_grid:
        x0,z0,x1,z1=terrain_grid['bounds']
        def fn(x,z):
            return height_at(terrain_grid,max(x0,min(x1,x)),max(z0,min(z1,z)))
        edge_clamped=sum(not x0<=sum(p[0] for p in b['footprint'])/len(b['footprint'])<=x1
                         or not z0<=sum(p[1] for p in b['footprint'])/len(b['footprint'])<=z1
                         for b in buildings if b['id'] not in core_ids)
    else:fn=None
    batches,stats=build_facade_batches(buildings,origin,core_ids,roads,fn)
    stats['terrain_base_edge_clamped_buildings']=edge_clamped
    objects=[]
    for kind,geometry in batches.items():
        obj=create_mesh('Facade_'+kind,geometry['vertices'],geometry['faces'],
                        material('Procedural_'+kind,PALETTE[kind]))
        obj.location=(origin[0],-origin[1],0)
        obj['geometry_source']='PLATEAU LOD1 or OSM footprint; see map building IDs'
        obj['visual_quality']='procedural facade estimate, not photo verified'
        obj['terrain_quality']='DEM ground base; out-of-area footprint bases clamped to grid edge'
        objects.append(obj)
    return objects,stats


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tiles-dir',required=True)
    parser.add_argument('--core-map',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    root=Path(args.tiles_dir).resolve()
    manifest_path=root/'tileset.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['schema']!='therabby.geoengine.tileset.wide.v0.1':
        raise ValueError('Wrong wide tileset schema')
    core_map=json.loads(Path(args.core_map).read_text(encoding='utf-8'))
    core_ids={building['id'] for building in core_map['buildings']}
    source_map_path=root.parent/manifest['source_map']
    if hashlib.sha256(source_map_path.read_bytes()).hexdigest()!=manifest['source_map_sha256']:
        raise ValueError('Wide source map hash mismatch')
    source_roads=json.loads(source_map_path.read_text(encoding='utf-8'))['roads']
    terrain_grid=None
    if manifest.get('terrain_grid'):
        terrain_path=root/manifest['terrain_grid']
        if hashlib.sha256(terrain_path.read_bytes()).hexdigest()!=manifest['terrain_grid_sha256']:
            raise ValueError('GSI DEM5A terrain grid hash mismatch')
        terrain_grid=json.loads(terrain_path.read_text(encoding='utf-8'))
    asphalt_path=root/'asphalt_procedural.png'
    asphalt_png(asphalt_path)
    manifest['road_visual_texture']=asphalt_path.name
    manifest['road_visual_texture_sha256']=hashlib.sha256(asphalt_path.read_bytes()).hexdigest()
    manifest['core_model']='../city_photo_crisp_projected.glb'
    manifest['core_low_model']='../core_lod1.glb'
    manifest['core_model_sha256']=hashlib.sha256((root/manifest['core_model']).read_bytes()).hexdigest()
    manifest['core_low_model_sha256']=hashlib.sha256((root/manifest['core_low_model']).read_bytes()).hexdigest()
    manifest['core_replaced_buildings']=len(core_ids)
    manifest['core_source_map_sha256']=hashlib.sha256(Path(args.core_map).read_bytes()).hexdigest()
    for record in manifest['tiles']:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        geometry=json.loads((root/record['geometry']).read_text(encoding='utf-8'))
        bounds=record['bounds'];origin=(bounds[0],bounds[1])
        road_lines=json.loads((root/record['roads']).read_text(encoding='utf-8'))['roads']
        facades,facade_stats=facade_meshes(geometry['buildings'],origin,core_ids,source_roads,terrain_grid)
        objects=[ground_mesh(bounds,root/record['ground'],terrain_grid),
            official_road_extent_mesh(geometry['official_road_extents'],origin),
            road_mesh(geometry['road_surfaces'],origin,asphalt_path),
            marking_mesh(road_lines,origin,terrain_grid),
            *facades]
        objects=[obj for obj in objects if obj]
        for obj in objects:
            obj['geoengine_schema']=manifest['schema']
            obj['geoengine_tile_id']=record['id']
            obj['geoengine_source_manifest']='tileset.json'
            obj['geoengine_attribution']='© OpenStreetMap contributors / ODbL 1.0 | Project PLATEAU / Fukushima City'
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:obj.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        path=root/record['glb']
        bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',
            export_apply=True,export_yup=True,export_cameras=False,
            export_lights=False,export_extras=True,use_selection=True)
        record['bytes']=path.stat().st_size
        record['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        record['mesh_count']=len(objects)
        record['triangles']=sum(max(1,len(face.vertices)-2)
                                for obj in objects for face in obj.data.polygons)
        record['core_replaced_buildings']=sum(b['id'] in core_ids for b in geometry['buildings'])
        record['facade_estimate']=facade_stats
        record['visual_quality']['buildings']='procedural windows and material colors; PLATEAU/OSM geometry, facade details estimated'
        record['visual_quality']['roads']='ground-level DEM drape with procedural asphalt; bridge/tunnel road deck omitted, width/lanes not surveyed'
        record['visual_quality']['official_road_extent']='PLATEAU LOD1 extent; carriageway and vertical position not identified'
        print(f'TILE {record["id"]}: {record["bytes"]} bytes, {record["building_count"]} source buildings',flush=True)
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        for mesh in list(bpy.data.meshes):bpy.data.meshes.remove(mesh)
        for mat in list(bpy.data.materials):bpy.data.materials.remove(mat)
        for image in list(bpy.data.images):bpy.data.images.remove(image)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'SUCCESS {len(manifest["tiles"])} GLB tiles at {root}',flush=True)


if __name__=='__main__':main()
