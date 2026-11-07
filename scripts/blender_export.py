"""Run INSIDE Blender: blender --background --python scripts/blender_export.py -- --scene dist/demo/map.json --output dist/demo/city.glb

Blender axes: +X east, +Y north, +Z up.
GLB (Three.js) axes: +X east, +Y up, +Z south.
This script exports only visual geometry, not legal drivable lanes/collisions.
"""
import argparse
import hashlib
import json
import math
import pathlib
import sys
from collections import defaultdict

try:
    import bpy
    import bmesh
    from mathutils import Vector, geometry
except ImportError as exc:
    raise RuntimeError("Requires Blender's bundled Python. Run with blender --background --python ...") from exc


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_backface_culling = False
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    if node:
        node.inputs["Base Color"].default_value = (*color, 1)
        node.inputs["Roughness"].default_value = .93
    return mat


def image_material(name, image_path):
    mat = material(name, (1, 1, 1))
    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.pack()
    nodes = mat.node_tree.nodes
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = image
    image_node.interpolation = 'Linear'
    bsdf = nodes.get("Principled BSDF")
    mat.node_tree.links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def create_mesh(name, vertices, faces, mat, uvs=None):
    if not faces:
        return None
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name,mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(mat)
    # Recalculate normals for potentially reversed GIS polygon winding.
    bm=bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    if uvs is not None:
        if len(uvs) != len(vertices):
            raise ValueError(f"UV vertex count mismatch in {name}")
        uv_layer = mesh.uv_layers.new(name="PLATEAU photo UV")
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                loop = mesh.loops[loop_index]
                uv_layer.data[loop_index].uv = uvs[loop.vertex_index]
    return obj


def add_buildings(scene):
    vertices=[]
    faces=[]
    for building in scene["buildings"]:
        if building.get("lod2_surfaces"):
            continue
        raw = building["footprint"]
        clean=[]
        for x,z in raw:
            if not clean or math.dist([x,z],clean[-1])>.05:
                clean.append([x,z])
        if len(clean)>3 and math.dist(clean[0],clean[-1])<.05:clean.pop()
        if len(clean)<3:continue
        h=float(building["height_m"])
        if h <= 0:continue
        base=len(vertices)
        for x,z in clean:vertices.append((x,-z,0))
        for x,z in clean:vertices.append((x,-z,h))
        count=len(clean)
        faces.append(tuple(base+count+i for i in range(count)))
        for i in range(count):
            j=(i+1)%count
            faces.append((base+i,base+j,base+count+j,base+count+i))
    return create_mesh("City_Buildings_Batched",vertices,faces,material("Buildings",(.64,.70,.72)))


def add_lod2_buildings(scene, texture_dir, redraws=None, atlas_redraws=None):
    redraws = redraws or {}
    atlas_redraws = atlas_redraws or {}
    batches = defaultdict(lambda: {"vertices": [], "faces": [], "uvs": [], "kind": None,
                                   "image_path": None, "is_redrawn": False})
    for building in scene["buildings"]:
        for surface_index, surface in enumerate(building.get("lod2_surfaces", [])):
            kind = surface["type"]
            if kind not in ("RoofSurface", "WallSurface", "GroundSurface"):
                kind = "WallSurface"
            uri = surface.get("texture_uri")
            override = redraws.get((building["id"], surface_index))
            override_path = override["texture"] if override else None
            if uri and not (texture_dir / pathlib.PurePosixPath(uri)).is_file():
                raise FileNotFoundError(f"Missing PLATEAU photo texture: {texture_dir / pathlib.PurePosixPath(uri)}")
            loops = []
            for ring in surface["rings"]:
                loop = [Vector((float(x), -float(z), float(y))) for x, z, y in ring]
                if len(loop) >= 3:
                    loops.append(loop)
            if not loops:
                continue
            triangles = geometry.tessellate_polygon(loops)
            if not triangles:
                continue
            image_path = (override_path or atlas_redraws.get(uri) or
                          (texture_dir / pathlib.PurePosixPath(uri) if uri else None))
            batch = batches[str(image_path) if image_path else kind]
            batch["kind"], batch["image_path"] = kind, image_path
            batch["is_redrawn"] = bool(override_path or atlas_redraws.get(uri))
            base = len(batch["vertices"])
            flat = [v for loop in loops for v in loop]
            batch["vertices"].extend(tuple(v) for v in flat)
            if image_path:
                if override and override["projection"] in ("horizontal_z", "horizontal_x"):
                    ring = surface["rings"][0]
                    axis = 1 if override["projection"] == "horizontal_z" else 0
                    lo_h, hi_h = min(p[axis] for p in ring), max(p[axis] for p in ring)
                    lo_y, hi_y = min(p[2] for p in ring), max(p[2] for p in ring)
                    uv_rings = [[((p[axis]-lo_h)/(hi_h-lo_h), (p[2]-lo_y)/(hi_y-lo_y)) for p in ring]]
                else:
                    uv_rings = ([[(0, 1), (1, 1), (1, 0), (0, 0)]] if override_path
                                else surface.get("texture_uv_rings", []))
                if len(uv_rings) != len(loops) or any(len(u) != len(loop) for u, loop in zip(uv_rings, loops)):
                    raise ValueError(f"Texture UV geometry mismatch: {uri}")
                batch["uvs"].extend(tuple(uv) for ring in uv_rings for uv in ring)
            for i, j, k in triangles:
                normal = (flat[j] - flat[i]).cross(flat[k] - flat[i])
                if (kind == "RoofSurface" and normal.z < 0 or
                    kind == "GroundSurface" and normal.z > 0):
                    j, k = k, j
                batch["faces"].append((base+i, base+j, base+k))
    colors = {"RoofSurface": (.43, .49, .53), "WallSurface": (.72, .75, .73),
              "GroundSurface": (.39, .45, .42)}
    objects = []
    for key, batch in batches.items():
        kind, image_path = batch["kind"], batch["image_path"]
        mat = (image_material(("Redrawn_" if batch["is_redrawn"] else "PLATEAU_Photo_") + image_path.stem[:24],
                              image_path) if image_path else
               material(kind, colors[kind]))
        name = "City_Texture_" + image_path.stem[:24] if image_path else "City_" + kind + "_LOD2"
        obj = create_mesh(name, batch["vertices"], batch["faces"], mat,
                          batch["uvs"] if image_path else None)
        if obj:
            objects.append(obj)
    return objects


def load_redraws(path, scene):
    if not path:
        return {}
    manifest_path = pathlib.Path(path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    buildings = {b["id"]: b for b in scene["buildings"]}
    redraws = {}
    for item in manifest["walls"]:
        key = (item["building_id"], item["surface_index"])
        if key in redraws:
            raise ValueError(f"Duplicate redrawn wall: {key}")
        surface = buildings[key[0]]["lod2_surfaces"][key[1]]
        projection = item.get("projection", "quad")
        if surface["type"] != "WallSurface" or len(surface["rings"]) != 1:
            raise ValueError(f"Redrawn wall must have one WallSurface ring: {key}")
        ring = surface["rings"][0]
        heights = [corner[2] for corner in ring]
        if projection == "quad":
            if len(ring) != 4 or not (abs(heights[0] - heights[1]) < .2 and
                    abs(heights[2] - heights[3]) < .2 and
                    min(heights[:2]) > max(heights[2:]) + .2):
                raise ValueError(f"Redrawn quad wall corner order unsupported: {key}")
        elif projection == "horizontal_z":
            if len(ring) < 3 or max(p[0] for p in ring)-min(p[0] for p in ring) > 2 or \
                    max(p[1] for p in ring)-min(p[1] for p in ring) < .1 or max(heights)-min(heights) < .2:
                raise ValueError(f"Redrawn wall cannot use horizontal_z projection: {key}")
        elif projection == "horizontal_x":
            if len(ring) < 3 or max(p[1] for p in ring)-min(p[1] for p in ring) > 2 or \
                    max(p[0] for p in ring)-min(p[0] for p in ring) < .1 or max(heights)-min(heights) < .2:
                raise ValueError(f"Redrawn wall cannot use horizontal_x projection: {key}")
        else:
            raise ValueError(f"Unsupported wall projection: {projection}")
        texture = (manifest_path.parent / item["texture"]).resolve()
        if not texture.is_file():
            raise FileNotFoundError(texture)
        redraws[key] = {"texture": texture, "projection": projection}
    return redraws


def load_atlas_redraws(path, scene):
    if not path:
        return {}
    manifest_path = pathlib.Path(path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {s["texture_uri"] for b in scene["buildings"]
                for s in b.get("lod2_surfaces", []) if s.get("texture_uri")}
    atlas_redraws = {}
    for item in manifest["atlases"]:
        uri = item["uri"]
        if uri in atlas_redraws:
            raise ValueError(f"Duplicate atlas redraw: {uri}")
        texture = (manifest_path.parent / item["texture"]).resolve()
        if not texture.is_file():
            raise FileNotFoundError(texture)
        atlas_redraws[uri] = texture
    if set(atlas_redraws) != expected:
        raise ValueError(f"Atlas redraws must cover all {len(expected)} source photos; got {len(atlas_redraws)}")
    return atlas_redraws


def add_roads(scene):
    verts=[]
    faces=[]
    for road in scene["roads"]:
        ps=road["points"]
        half=float(road["width_m"])/2
        for a,b in zip(ps,ps[1:]):
            dx,dz=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dz)
            if length<.1:continue
            nx,nz=-dz/length*half,dx/length*half
            base=len(verts)
            for x,z in ((a[0]+nx,a[1]+nz),(a[0]-nx,a[1]-nz),
                        (b[0]-nx,b[1]-nz),(b[0]+nx,b[1]+nz)):
                verts.append((x,-z,.035))
            faces.append((base,base+1,base+2,base+3))
    return create_mesh("Roads_ClassWidth_NotMeasured",verts,faces,material("Asphalt",(.19,.25,.29)))


def add_ortho_ground(scene, path):
    metadata_path = path.with_suffix(".provenance.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["area_id"] != scene["area"]["id"] or metadata["source_year"] != 2024:
        raise ValueError("Orthophoto metadata does not match this Fukushima area")
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("Orthophoto SHA-256 mismatch")
    half = float(metadata["half_size_m"])
    vertices = [(-half, -half, -.06), (half, -half, -.06),
                (half, half, -.06), (-half, half, -.06)]
    mat = image_material("PLATEAU_Ortho_2024", path)
    return create_mesh("Ground_PLATEAU_Ortho_2024", vertices, [(0, 1, 2, 3)], mat,
                       [(0, 0), (1, 0), (1, 1), (0, 1)])


def add_blender_preview():
    ground = bpy.data.meshes.new("Preview_Ground_Mesh")
    ground.from_pydata([(-350,-350,-.12),(350,-350,-.12),(350,350,-.12),(-350,350,-.12)],
                       [],[(0,1,2,3)])
    obj = bpy.data.objects.new("Preview_Ground_Not_Exported", ground)
    bpy.context.scene.collection.objects.link(obj)
    ground.materials.append(material("Preview Ground",(.43,.57,.47)))
    camera_data = bpy.data.cameras.new("GeoEngine Camera")
    camera = bpy.data.objects.new("GeoEngine Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (165, -190, 160)
    target = Vector((0, 0, 12))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = 390
    bpy.context.scene.camera = camera
    bpy.context.scene.render.resolution_x = 1920
    bpy.context.scene.render.resolution_y = 1080
    bpy.context.scene.render.resolution_percentage = 100
    # Multisampling keeps façade lines clear; the previous FXAA viewport setting softened them.
    bpy.context.scene.display.viewport_aa = '16'
    bpy.context.scene.display.render_aa = '32'
    for screen in bpy.data.screens:
        if screen.name != 'Layout':
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                view = area.spaces.active
                view.region_3d.view_perspective = 'CAMERA'
                view.shading.type = 'SOLID'
                view.shading.color_type = 'TEXTURE'
                view.shading.light = 'STUDIO'
                view.shading.show_cavity = True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--scene",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--render-preview",action="store_true",help="Also render a Blender Workbench PNG")
    parser.add_argument("--texture-dir",default="data/raw/plateau",help="Directory containing official PLATEAU JPEGs")
    parser.add_argument("--ortho",help="Georeferenced PLATEAU-Ortho image with .provenance.json sidecar")
    parser.add_argument("--redraw-manifest", help="JSON manifest of photo-reference wall redraws")
    parser.add_argument("--atlas-manifest", help="JSON manifest of registered redrawn PLATEAU atlases")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    scene=json.loads(pathlib.Path(args.scene).read_text(encoding="utf-8"))
    if scene.get("schema")!="therabby.geoengine.map.v0.1":
        raise ValueError("Invalid scene schema")
    redraws = load_redraws(args.redraw_manifest, scene)
    atlas_redraws = load_atlas_redraws(args.atlas_manifest, scene)
    asset_provenance = list(scene.get("provenance", []))
    if atlas_redraws:
        asset_provenance.append({
            "name": "All-building photo-reference atlas redraw",
            "type": "AI-assisted derived visual texture",
            "source": "56 official PLATEAU 2025 building photo atlases",
            "manifest": pathlib.Path(args.atlas_manifest).name,
            "coverage": "All photo UV surfaces; generated boundaries registered with original photo fallback",
            "accuracy": "Fine details are interpretive and not surveyed",
        })
    if redraws:
        asset_provenance.append({
            "name": "Photo-reference facade redraw",
            "type": "AI-assisted derived visual texture",
            "source": "PLATEAU 2025 official building photo UV; see redraw manifest",
            "manifest": pathlib.Path(args.redraw_manifest).name,
            "wall_ids": [f"{building_id}:{surface_index}" for building_id, surface_index in redraws],
            "accuracy": "Fine details are interpretive and not surveyed",
        })
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    visual_ground = (add_ortho_ground(scene, pathlib.Path(args.ortho).resolve()) if args.ortho
                     else add_roads(scene))
    city_objects = [add_buildings(scene), *add_lod2_buildings(scene, pathlib.Path(args.texture_dir).resolve(), redraws, atlas_redraws),
                    visual_ground]
    city_objects = [obj for obj in city_objects if obj]
    for obj in city_objects:
        obj["geoengine_data_quality"] = scene.get("data_quality", "UNKNOWN")
        obj["geoengine_provenance"] = json.dumps(asset_provenance, ensure_ascii=False)
        obj["geoengine_schema"] = scene["schema"]
    outfile=pathlib.Path(args.output).resolve()
    outfile.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in city_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = city_objects[0]
    bpy.ops.export_scene.gltf(filepath=str(outfile),export_format="GLB", export_apply=True, export_yup=True,
                              export_cameras=False,export_lights=False,export_extras=True,
                              use_selection=True)
    if not outfile.exists() or outfile.stat().st_size<20:
        raise RuntimeError("GLB export failed")
    sidecar = outfile.with_suffix(".provenance.json")
    sidecar.write_text(json.dumps({
        "asset": outfile.name,
        "bytes": outfile.stat().st_size,
        "sha256": hashlib.sha256(outfile.read_bytes()).hexdigest(),
        "source_map": pathlib.Path(args.scene).name,
        "data_quality": scene.get("data_quality", "UNKNOWN"),
        "provenance": asset_provenance,
        "limitations": scene.get("status", {}),
        "lod2_buildings": sum(bool(b.get("lod2_surfaces")) for b in scene["buildings"]),
        "lod2_surfaces": sum(len(b.get("lod2_surfaces", [])) for b in scene["buildings"]),
        "textured_surfaces": sum(bool(s.get("texture_uri")) for b in scene["buildings"]
                                 for s in b.get("lod2_surfaces", [])),
        "texture_images": len({s["texture_uri"] for b in scene["buildings"]
                               for s in b.get("lod2_surfaces", []) if s.get("texture_uri")}),
        "ground_imagery": "PLATEAU-Ortho 2024" if args.ortho else None,
        "road_visual": "orthophoto (2024)" if args.ortho else "OSM class-width strips",
        "redrawn_surfaces": (len(redraws) + sum(
            bool(s.get("texture_uri") in atlas_redraws) and (b["id"], i) not in redraws
            for b in scene["buildings"] for i, s in enumerate(b.get("lod2_surfaces", [])))),
        "direct_redrawn_surfaces": len(redraws),
        "redrawn_atlases": len(atlas_redraws),
        "redraw_manifest": pathlib.Path(args.redraw_manifest).name if args.redraw_manifest else None,
        "atlas_manifest": pathlib.Path(args.atlas_manifest).name if args.atlas_manifest else None,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    add_blender_preview()
    bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
    bpy.context.scene.display.shading.color_type = 'TEXTURE' if any(
        s.get("texture_uri") for b in scene["buildings"] for s in b.get("lod2_surfaces", [])) else 'MATERIAL'
    bpy.context.scene.display.shading.light = 'STUDIO'
    bpy.context.scene.display.shading.show_cavity = True
    bpy.ops.object.select_all(action="DESELECT")
    blend_file = outfile.with_suffix(".blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_file))
    if args.render_preview:
        bpy.context.scene.render.filepath = str(outfile.with_name(outfile.stem + "_blender_preview.png"))
        bpy.ops.render.render(write_still=True)
    print(f"SUCCESS exported {outfile} ({outfile.stat().st_size:,} bytes)")
    print(f"SUCCESS saved Blender scene {blend_file} ({blend_file.stat().st_size:,} bytes)")

if __name__ == "__main__":main()
