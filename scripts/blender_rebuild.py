"""Rebuild a Fukushima facade from reference, without embedding source photographs.

Run inside Blender 3.1+:
blender --background --python scripts/blender_rebuild.py -- \
  --scene dist/real/fukushima-east/map.json \
  --output dist/real/fukushima-east/city_rebuilt.glb

The detailed facade is an artist's approximation of one real building. OSM road
widths and markings are illustrative, not surveyed driving geometry.
"""
import argparse
import hashlib
import json
import math
import pathlib
import sys
import zlib
from collections import defaultdict

import bpy
from mathutils import Vector, geometry


HERO_ID = "plateau-bldg_c21e382e-a296-4a99-aa62-2eaca866924c"
HERO_PHOTO = "56405306_bldg_6697_appearance/3905f0b5-a7aa-4d92-909e-8af0a253b622.jpg"


def make_material(name, color, roughness=0.8, metallic=0.0, color_image=None, normal_image=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if color_image:
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = color_image
        node.interpolation = 'Linear'
        mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    if normal_image:
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = normal_image
        tex.image.colorspace_settings.name = 'Non-Color'
        normal = mat.node_tree.nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = 0.35
        mat.node_tree.links.new(tex.outputs["Color"], normal.inputs["Color"])
        mat.node_tree.links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def random_grid(x, y, seed):
    n = ((x % 257) * 73856093) ^ ((y % 257) * 19349663) ^ (seed * 83492791)
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 65535) / 65535.0


def value_noise(x, y, period, seed):
    gx, gy = x / period, y / period
    ix, iy = math.floor(gx), math.floor(gy)
    fx, fy = gx - ix, gy - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    cycle = 256 // period
    a = random_grid(ix % cycle, iy % cycle, seed)
    b = random_grid((ix + 1) % cycle, iy % cycle, seed)
    c = random_grid(ix % cycle, (iy + 1) % cycle, seed)
    d = random_grid((ix + 1) % cycle, (iy + 1) % cycle, seed)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def painted_material_images(folder, name, base, amplitude, seed):
    """Make small seamless PBR maps from code, never from PLATEAU JPEG pixels."""
    size = 256
    heights = []
    colors = []
    for y in range(size):
        for x in range(size):
            n = (0.55 * value_noise(x, y, 32, seed) +
                 0.30 * value_noise(x, y, 8, seed + 1) +
                 0.15 * value_noise(x, y, 2, seed + 2))
            heights.append(n)
            delta = (n - .5) * amplitude
            colors.extend([max(0, min(1, c + delta)) for c in base] + [1.0])
    normals = []
    for y in range(size):
        for x in range(size):
            left = heights[y * size + (x - 1) % size]
            right = heights[y * size + (x + 1) % size]
            down = heights[((y - 1) % size) * size + x]
            up = heights[((y + 1) % size) * size + x]
            normal = Vector(((left - right) * 0.55, (down - up) * 0.55, 1.0)).normalized()
            normals.extend((normal.x * .5 + .5, normal.y * .5 + .5, normal.z * .5 + .5, 1.0))
    folder.mkdir(parents=True, exist_ok=True)
    outputs = []
    for suffix, pixels in (("color", colors), ("normal", normals)):
        image = bpy.data.images.new(f"Repaint_{name}_{suffix}", width=size, height=size, alpha=True)
        image.pixels[:] = pixels
        image.filepath_raw = str(folder / f"{name}_{suffix}.png")
        image.file_format = 'PNG'
        image.save()
        image.pack()
        outputs.append(image)
    return outputs


def make_mesh(name, vertices, faces, mat, uvs=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(mat)
    if uvs is not None:
        layer = mesh.uv_layers.new(name="Repaint tiled UV")
        for poly in mesh.polygons:
            for loop_index in poly.loop_indices:
                layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    return obj


def add_box(name, center, size, mat, angle=0.0, detail=False):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    obj.rotation_euler.z = angle
    obj.data.materials.append(mat)
    if detail:
        obj["rebuild_detail"] = True
    return obj


def polygon_contains(point, ring):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if ((a[1] > y) != (b[1] > y)) and (x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]):
            inside = not inside
    return inside


def add_lod2_shell(city, materials):
    batches = defaultdict(lambda: {"vertices": [], "faces": [], "uvs": []})
    hero = next(b for b in city["buildings"] if b["id"] == HERO_ID)
    for building in city["buildings"]:
        hero_building = building["id"] == HERO_ID
        tier = zlib.crc32(building["id"].encode()) % 4
        for surface in building.get("lod2_surfaces", []):
            kind = surface["type"]
            if kind not in ("WallSurface", "RoofSurface", "GroundSurface"):
                kind = "WallSurface"
            key = ("hero_" + ("roof" if kind == "RoofSurface" else "wall")) if hero_building else (
                "roof" if kind == "RoofSurface" else f"wall_{tier}")
            loops = [[Vector((float(x), -float(z), float(h))) for x, z, h in ring]
                     for ring in surface["rings"] if len(ring) >= 3]
            if not loops:
                continue
            triangles = geometry.tessellate_polygon(loops)
            if not triangles:
                continue
            flat = [v for loop in loops for v in loop]
            batch = batches[key]
            offset = len(batch["vertices"])
            batch["vertices"].extend(tuple(v) for v in flat)
            for v in flat:
                if kind == "RoofSurface":
                    batch["uvs"].append((v.x / 4, v.y / 4))
                else:
                    xs = [p.x for p in flat]
                    ys = [p.y for p in flat]
                    axis = v.x if max(xs) - min(xs) > max(ys) - min(ys) else v.y
                    batch["uvs"].append((axis / 3, v.z / 3))
            for i, j, k in triangles:
                normal = (flat[j] - flat[i]).cross(flat[k] - flat[i])
                if kind == "RoofSurface" and normal.z < 0:
                    j, k = k, j
                elif kind == "GroundSurface" and normal.z > 0:
                    j, k = k, j
                batch["faces"].append((offset + i, offset + j, offset + k))
    objects = []
    for key, batch in batches.items():
        obj = make_mesh("Rebuilt_LOD2_" + key, batch["vertices"], batch["faces"],
                        materials[key], batch["uvs"])
        objects.append(obj)
    return hero, objects


def add_lod1_fallback(city, materials):
    objects = []
    for building in city["buildings"]:
        if building.get("lod2_surfaces"):
            continue
        ring = building["footprint"]
        if len(ring) < 3:
            continue
        h = float(building["height_m"])
        verts = [(x, -z, 0) for x, z in ring] + [(x, -z, h) for x, z in ring]
        n = len(ring)
        faces = [tuple(n + i for i in range(n))]
        faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        objects.append(make_mesh("Rebuilt_LOD1_" + building["id"], verts, faces,
                                 materials["wall_0"]))
    return objects


def add_roads(city, materials):
    verts, faces, uvs = [], [], []
    for road in city["roads"]:
        half = float(road["width_m"]) / 2
        for a, b in zip(road["points"], road["points"][1:]):
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dz)
            if length < .1:
                continue
            nx, nz = -dz / length * half, dx / length * half
            offset = len(verts)
            for x, z in ((a[0] + nx, a[1] + nz), (a[0] - nx, a[1] - nz),
                         (b[0] - nx, b[1] - nz), (b[0] + nx, b[1] + nz)):
                verts.append((x, -z, .04))
                uvs.append((x / 3, z / 3))
            faces.append((offset, offset + 1, offset + 2, offset + 3))
    road_obj = make_mesh("OSM_Class_Width_Road_Proxy", verts, faces, materials["asphalt"], uvs)
    ground = make_mesh("Ground_Repainted_Not_Orthophoto",
                       [(-180, -180, -.08), (180, -180, -.08), (180, 180, -.08), (-180, 180, -.08)],
                       [(0, 1, 2, 3)], materials["paving"],
                       [(-45, -45), (45, -45), (45, 45), (-45, 45)])
    return [ground, road_obj]


def window_frame(name, point, tangent, outward, width, height, mats):
    angle = math.atan2(tangent.y, tangent.x)
    add_box(name + "_frame", point + outward * .15, (width, .16, height),
            mats["frame"], angle, True)
    add_box(name + "_glass", point + outward * .25, (width - .22, .04, height - .22),
            mats["glass"], angle, True)
    add_box(name + "_mullion", point + outward * .29, (.045, .045, height - .22),
            mats["metal"], angle, True)
    add_box(name + "_sill", point + outward * .22 + Vector((0, 0, -height / 2 - .06)),
            (width + .18, .25, .09), mats["trim"], angle, True)


def add_hero_windows(hero, mats):
    footprint = hero["footprint"]
    center = Vector((sum(p[0] for p in footprint) / len(footprint),
                     -sum(p[1] for p in footprint) / len(footprint), 0))
    camera_side = Vector((95, -95, 0))
    count = 0
    for wall_index, surface in enumerate(hero["lod2_surfaces"]):
        if surface["type"] != "WallSurface" or len(surface["rings"]) != 1:
            continue
        ring = [Vector((x, -z, h)) for x, z, h in surface["rings"][0]]
        low, high = min(p.z for p in ring), max(p.z for p in ring)
        if high - low < 9:
            continue
        horizontal = [(a, b) for a, b in zip(ring, ring[1:] + ring[:1])
                      if abs(a.z - b.z) < .1]
        if not horizontal:
            continue
        a, b = max(horizontal, key=lambda ab: (ab[1] - ab[0]).length)
        tangent = Vector((b.x - a.x, b.y - a.y, 0)).normalized()
        mid = sum(ring, Vector()) / len(ring)
        outward = Vector((-tangent.y, tangent.x, 0))
        if outward.dot(mid - center) < 0:
            outward.negate()
        if outward.dot(camera_side - mid) < 0:
            continue
        projected = [((p - a).dot(tangent), p.z) for p in ring]
        min_u = min(p[0] for p in projected)
        max_u = max(p[0] for p in projected)
        if max_u - min_u < 7:
            continue
        for level in range(1, int(high / 3.3) + 1):
            z = level * 3.3 + .7
            if z + .85 > high - .4:
                continue
            u = min_u + 1.4
            while u < max_u - 1.2:
                width, height = 1.35, 1.65
                corners = [(u + sx * width * .55, z + sy * height * .55)
                           for sx in (-1, 1) for sy in (-1, 1)]
                if all(polygon_contains(c, projected) for c in corners):
                    point = a + tangent * u
                    point.z = z
                    window_frame(f"Hero_Window_{wall_index}_{count}", point, tangent,
                                 outward, width, height, mats)
                    count += 1
                u += 2.7
        # Shopfront glazing is an interpretation; its arrangement is not surveyed.
        if low < .3 and high > 10 and max_u - min_u > 15:
            u = min_u + 2
            while u < max_u - 1.6:
                corners = [(u + sx * 1.0, 2 + sy * 1.1)
                           for sx in (-1, 1) for sy in (-1, 1)]
                if all(polygon_contains(c, projected) for c in corners):
                    point = a + tangent * u
                    point.z = 2
                    window_frame(f"Hero_Shopfront_{wall_index}_{count}", point, tangent,
                                 outward, 2.0, 2.3, mats)
                    count += 1
                u += 3.0
    return count


def add_rooftop_equipment(hero, mats):
    candidates = []
    for surface in hero["lod2_surfaces"]:
        if surface["type"] != "RoofSurface" or not surface["rings"]:
            continue
        ring = surface["rings"][0]
        if max(p[2] for p in ring) - min(p[2] for p in ring) > .1:
            continue
        area = abs(sum(ring[i][0] * ring[(i + 1) % len(ring)][1] -
                       ring[(i + 1) % len(ring)][0] * ring[i][1]
                       for i in range(len(ring))) / 2)
        candidates.append((area, ring))
    if not candidates:
        return 0
    _, ring = max(candidates)
    cx = sum(p[0] for p in ring) / len(ring)
    cy = -sum(p[1] for p in ring) / len(ring)
    roof_z = sum(p[2] for p in ring) / len(ring)
    added = 0
    for i, (dx, dy) in enumerate(((-2.3, 0), (0, 0), (2.3, 0))):
        if not polygon_contains((cx + dx, -cy - dy), [(p[0], p[1]) for p in ring]):
            continue
        add_box(f"Hero_Rooftop_HVAC_{i}", (cx + dx, cy + dy, roof_z + .55),
                (1.5, 1.3, 1.1), mats["trim"], detail=True)
        add_box(f"Hero_Rooftop_HVAC_Grill_{i}", (cx + dx, cy + dy - .68, roof_z + .55),
                (1.2, .035, .7), mats["frame"], detail=True)
        added += 1
    return added


def add_hero_street(mats):
    """Illustrative street dressing along the OSM road east of the pilot building."""
    details = []
    paving = make_material("Repaint_Sidewalk_Concrete", (.53, .53, .50), .9)
    marking = make_material("Repaint_Road_Marking", (.79, .78, .68), .92)
    drain = make_material("Repaint_Drain_Grating", (.18, .20, .21), .62, .3)
    for x, width in ((43.85, 1.4), (51.25, 1.4)):
        details.append(add_box("Sidewalk_OSM_Illustrative", (x, -1, .10),
                               (width, 52, .16), paving))
        curb_x = 44.62 if x < 47 else 50.48
        details.append(add_box("Kerb_OSM_Illustrative", (curb_x, -1, .16),
                               (.12, 52, .30), mats["trim"]))
    for y in range(-24, 25, 7):
        details.append(add_box("Centerline_OSM_Illustrative", (47.56, y, .085),
                               (.10, 3.2, .012), marking))
    for y in (-17, -1, 15):
        details.append(add_box("Drain_OSM_Illustrative", (44.9, y, .065),
                               (.32, .55, .025), drain))
    return details


def join_details_by_material():
    details = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.get("rebuild_detail")]
    groups = defaultdict(list)
    for obj in details:
        groups[obj.data.materials[0].name].append(obj)
    joined = []
    for mat_name, objects in groups.items():
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.join()
        objects[0].name = "Hero_Details_" + mat_name
        joined.append(objects[0])
    return joined


def set_preview_camera(hero):
    footprint = hero["footprint"]
    cx = sum(p[0] for p in footprint) / len(footprint)
    cy = -sum(p[1] for p in footprint) / len(footprint)
    target = Vector((cx, cy, 11))
    camera_data = bpy.data.cameras.new("Rebuild comparison camera")
    camera = bpy.data.objects.new("Rebuild comparison camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (cx + 54, cy - 61, 37)
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.lens = 43
    camera_data.clip_end = 650
    bpy.context.scene.camera = camera
    sun_data = bpy.data.lights.new("Rebuild daylight", 'SUN')
    sun = bpy.data.objects.new("Rebuild daylight", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-25), math.radians(-35))
    sun_data.energy = 3.2
    sun_data.angle = math.radians(4)
    world = bpy.context.scene.world or bpy.data.worlds.new("Rebuild sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (.46, .62, .75, 1)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = .65
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'
    bpy.context.scene.eevee.use_gtao = True
    bpy.context.scene.eevee.gtao_distance = 3
    bpy.context.scene.eevee.gtao_factor = 1.1
    bpy.context.scene.eevee.use_soft_shadows = True
    bpy.context.scene.eevee.taa_render_samples = 64
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 720
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.view_settings.view_transform = 'Filmic'
    bpy.context.scene.view_settings.look = 'Medium High Contrast'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference-photo", default="data/raw/plateau/" + HERO_PHOTO)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    scene_path = pathlib.Path(args.scene).resolve()
    city = json.loads(scene_path.read_text(encoding="utf-8"))
    if city.get("schema") != "therabby.geoengine.map.v0.1" or city.get("data_quality") == "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("Expected real GeoEngine map with known schema")
    if not any(b["id"] == HERO_ID for b in city["buildings"]):
        raise ValueError("Hero building is not in this map")
    reference_photo = pathlib.Path(args.reference_photo).resolve()
    if not reference_photo.is_file() or reference_photo.name != pathlib.PurePosixPath(HERO_PHOTO).name:
        raise ValueError("Expected PLATEAU reference photo for hero building")
    output = pathlib.Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    texture_folder = output.parent / "rebuild_textures"
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    concrete, concrete_normal = painted_material_images(texture_folder, "concrete", (.72, .73, .70), .10, 7)
    asphalt, asphalt_normal = painted_material_images(texture_folder, "asphalt", (.22, .25, .26), .11, 19)
    roof, roof_normal = painted_material_images(texture_folder, "roof", (.46, .47, .45), .08, 31)
    mats = {
        "hero_wall": make_material("Photo_Reference_Repaint_Concrete", (.72, .73, .70), .88,
                                   color_image=concrete, normal_image=concrete_normal),
        "hero_roof": make_material("Repaint_Roof", (.46, .47, .45), .9,
                                   color_image=roof, normal_image=roof_normal),
        "roof": make_material("Context_Roof_Proxy", (.46, .47, .45), .9),
        "asphalt": make_material("Repaint_Asphalt_OSM_Proxy", (.22, .25, .26), .96,
                                 color_image=asphalt, normal_image=asphalt_normal),
        "paving": make_material("Repaint_Paving_Proxy", (.43, .44, .42), .94,
                                color_image=concrete, normal_image=concrete_normal),
        "frame": make_material("Repaint_Charcoal_Window_Frame", (.10, .13, .15), .38, .25),
        "glass": make_material("Repaint_Blue_Grey_Glass", (.11, .19, .23), .16, .18),
        "metal": make_material("Repaint_Aluminium_Mullion", (.52, .56, .56), .3, .75),
        "trim": make_material("Repaint_Light_Concrete_Trim", (.67, .68, .67), .72),
    }
    for index, color in enumerate(((.62, .64, .63), (.72, .70, .65),
                                   (.55, .59, .60), (.69, .66, .62))):
        mats[f"wall_{index}"] = make_material(f"Context_Wall_Proxy_{index}", color, .86)
    hero, objects = add_lod2_shell(city, mats)
    objects.extend(add_lod1_fallback(city, mats))
    objects.extend(add_roads(city, mats))
    window_count = add_hero_windows(hero, mats)
    hvac_count = add_rooftop_equipment(hero, mats)
    objects.extend(add_hero_street(mats))
    objects.extend(join_details_by_material())
    for obj in objects:
        obj["geoengine_data_quality"] = city["data_quality"]
        obj["geoengine_rebuild_scope"] = "one photo-referenced building; context proxy"
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', export_apply=True,
                              export_yup=True, export_cameras=False, export_lights=False,
                              export_extras=True, use_selection=True)
    if output.stat().st_size < 1000:
        raise RuntimeError("GLB export failed")
    sidecar = output.with_suffix('.provenance.json')
    sidecar.write_text(json.dumps({
        "asset": output.name,
        "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "source_map": scene_path.name,
        "source_map_sha256": hashlib.sha256(scene_path.read_bytes()).hexdigest(),
        "model_type": "photo_reference_rebuild_pilot",
        "hero_building_id": HERO_ID,
        "reference_photo": HERO_PHOTO,
        "reference_photo_sha256": hashlib.sha256(reference_photo.read_bytes()).hexdigest(),
        "reference_photo_embedded": False,
        "generated_textures": [p.name for p in sorted(texture_folder.glob('*.png'))],
        "windows_modeled": window_count,
        "roof_units_modeled": hvac_count,
        "context": "other PLATEAU LOD2 buildings with generic material proxies",
        "road_visual": "OSM centerlines with estimated class widths; one street has illustrative markings and kerbs",
        "limitations": ["Facade windows and storefronts approximate the photograph, not surveyed",
                        "Rooftop equipment placement approximate",
                        "No street-level reference for signs, trees, traffic furniture or kerbs",
                        "Ground is repainted proxy, not georeferenced surface imagery"],
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    set_preview_camera(hero)
    bpy.ops.object.select_all(action='DESELECT')
    blend = output.with_suffix('.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.context.scene.render.filepath = str(output.with_name(output.stem + '_preview.png'))
    bpy.ops.render.render(write_still=True)
    print(f"SUCCESS {output.name}: {output.stat().st_size:,} bytes; windows={window_count}, HVAC={hvac_count}")
    print(f"SUCCESS {blend.name} and {output.stem}_preview.png")


if __name__ == '__main__':
    main()
