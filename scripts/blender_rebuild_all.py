"""Photo-reference repaint of all 56 Fukushima-east LOD2 buildings.

This makes an approximate city-wide visual study. The source JPEG atlases are
read to classify wall appearance, but no source photo pixels are exported.
"""
import argparse
import hashlib
import json
import math
import pathlib
import sys
from collections import Counter, defaultdict

import bpy
from mathutils import Vector, geometry

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import blender_rebuild as pilot
import rebuild_streets
import rebuild_styles


TONE_COLORS = (
    (.32, .35, .38),  # reference-image dark group
    (.46, .49, .50),
    (.63, .61, .57),
    (.78, .76, .71),  # reference-image light group
)


def window_tile(folder, name, base, seed):
    """Paint a repeatable 3 m facade bay; all pixels are generated here."""
    size = 256
    pixels = []
    for y in range(size):
        py = (y + .5) / size
        for x in range(size):
            px = (x + .5) / size
            grain = (pilot.value_noise(x, y, 16, seed) - .5) * .04
            color = tuple(max(0, min(1, c + grain)) for c in base)
            # A recessed window, frame and narrow sill. Never copied from the JPEG.
            if .18 < px < .82 and .22 < py < .77:
                color = (.08, .11, .13)
            if .20 < px < .80 and .24 < py < .75:
                reflection = .06 * (1 - py) + .035 * px
                color = (.12 + reflection, .18 + reflection, .21 + reflection)
            if .18 < px < .82 and .20 < py < .23:
                color = tuple(min(1, c + .09) for c in base)
            if .49 < px < .51 and .24 < py < .75:
                color = (.31, .34, .35)
            pixels.extend((*color, 1.0))
    image = bpy.data.images.new(name, width=size, height=size, alpha=True)
    image.pixels[:] = pixels
    folder.mkdir(parents=True, exist_ok=True)
    image.filepath_raw = str(folder / (name + '.png'))
    image.file_format = 'PNG'
    image.save()
    image.pack()
    return image


def create_materials(folder):
    mats = {}
    for i, color in enumerate(TONE_COLORS):
        plain, normal = pilot.painted_material_images(folder, f"wall_{i}", color, .09, i + 51)
        windows = window_tile(folder, f"wall_windows_{i}", color, i + 51)
        mats[f"wall_plain_{i}"] = pilot.make_material(f"Repaint_Wall_Plain_{i}", color, .84,
                                                       color_image=plain, normal_image=normal)
        mats[f"wall_windows_{i}"] = pilot.make_material(f"Repaint_Wall_Window_Bay_{i}", color, .67,
                                                         color_image=windows, normal_image=normal)
    for i, color in enumerate(((.42, .44, .44), (.56, .57, .55))):
        roof, normal = pilot.painted_material_images(folder, f"roof_{i}", color, .08, i + 71)
        mats[f"roof_{i}"] = pilot.make_material(f"Repaint_Roof_{i}", color, .88,
                                                color_image=roof, normal_image=normal)
    asphalt, asphalt_normal = pilot.painted_material_images(folder, "asphalt", (.20, .23, .24), .11, 91)
    paving, paving_normal = pilot.painted_material_images(folder, "paving", (.49, .48, .45), .07, 96)
    mats["asphalt"] = pilot.make_material("Repaint_Street_Asphalt", (.20, .23, .24), .96,
                                         color_image=asphalt, normal_image=asphalt_normal)
    mats["paving"] = pilot.make_material("Repaint_Pedestrian_Paving", (.49, .48, .45), .93,
                                        color_image=paving, normal_image=paving_normal)
    mats["steps"] = pilot.make_material("Repaint_Steps_Flat_Proxy", (.55, .55, .52), .9)
    mats["kerb"] = pilot.make_material("Repaint_Road_Edge_Proxy", (.66, .64, .59), .88)
    mats["frame"] = pilot.make_material("Repaint_Window_Frame", (.10, .12, .14), .36, .25)
    mats["glass"] = pilot.make_material("Repaint_Window_Glass", (.11, .18, .21), .17, .15)
    mats["metal"] = pilot.make_material("Repaint_Window_Mullion", (.51, .54, .55), .3, .7)
    mats["trim"] = pilot.make_material("Repaint_Window_Sill", (.66, .66, .63), .72)
    return mats


def wall_span(surface):
    ring = surface["rings"][0]
    xs, zs, hs = zip(*ring)
    return math.hypot(max(xs) - min(xs), max(zs) - min(zs)), max(hs) - min(hs)


def select_geometry_walls(city, styles):
    """Keep 3D window work near the centre and cap it per building."""
    selected = {}
    for building in city["buildings"]:
        bid = building["id"]
        if bid == pilot.HERO_ID:
            selected[bid] = set()
            continue
        cx = sum(p[0] for p in building["footprint"]) / len(building["footprint"])
        cz = sum(p[1] for p in building["footprint"]) / len(building["footprint"])
        if math.hypot(cx, cz) > 90:
            selected[bid] = set()
            continue
        ranked = []
        for index in styles[bid]["window_surface_indices"]:
            surface = building["lod2_surfaces"][index]
            length, height = wall_span(surface)
            if length >= 7 and height >= 7:
                ranked.append((length * height, index))
        selected[bid] = {index for _, index in sorted(ranked, reverse=True)[:2]}
    return selected


def select_pattern_walls(city, styles):
    """Use a visibly estimated window bay on broad rectilinear facades."""
    patterned = {}
    for building in city["buildings"]:
        bid = building["id"]
        supported = set(styles[bid]["window_surface_indices"])
        chosen = set(supported)
        if bid != pilot.HERO_ID and float(building["height_m"]) >= 8:
            for index, surface in enumerate(building["lod2_surfaces"]):
                if surface["type"] != "WallSurface" or len(surface["rings"]) != 1:
                    continue
                if len(surface["rings"][0]) != 4:
                    continue
                length, height = wall_span(surface)
                if length >= 5 and height >= 4:
                    chosen.add(index)
        patterned[bid] = chosen
    return patterned


def add_city_shell(city, styles, mats, geometry_walls, pattern_walls):
    batches = defaultdict(lambda: {"vertices": [], "faces": [], "uvs": []})
    for building in city["buildings"]:
        bid = building["id"]
        tone = styles[bid]["tone_index"]
        for index, surface in enumerate(building["lod2_surfaces"]):
            kind = surface["type"]
            if kind == "RoofSurface":
                key = f"roof_{tone // 2}"
            else:
                use_pattern = (kind == "WallSurface" and index in pattern_walls[bid] and
                               index not in geometry_walls[bid] and bid != pilot.HERO_ID)
                key = f"wall_{'windows' if use_pattern else 'plain'}_{tone}"
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
            if kind == "RoofSurface":
                batch["uvs"].extend((v.x / 4, v.y / 4) for v in flat)
            else:
                xs, ys = [v.x for v in flat], [v.y for v in flat]
                use_x = max(xs) - min(xs) > max(ys) - min(ys)
                batch["uvs"].extend(((v.x if use_x else v.y) / 3, v.z / 3) for v in flat)
            for i, j, k in triangles:
                normal = (flat[j] - flat[i]).cross(flat[k] - flat[i])
                if kind == "RoofSurface" and normal.z < 0:
                    j, k = k, j
                elif kind == "GroundSurface" and normal.z > 0:
                    j, k = k, j
                batch["faces"].append((offset + i, offset + j, offset + k))
    return [pilot.make_mesh("City_Repaint_" + key, batch["vertices"], batch["faces"],
                            mats[key], batch["uvs"])
            for key, batch in batches.items() if batch["faces"]]


def append_box(batch, center, size, angle=0):
    cx, cy, cz = center
    sx, sy, sz = (v / 2 for v in size)
    c, s = math.cos(angle), math.sin(angle)
    offset = len(batch["vertices"])
    for z in (-sz, sz):
        for y in (-sy, sy):
            for x in (-sx, sx):
                batch["vertices"].append((cx + x * c - y * s,
                                          cy + x * s + y * c, cz + z))
    batch["faces"].extend((tuple(offset + i for i in face) for face in
                           ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                            (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))))


def wall_window_grid(building, surface, batches, count_cap):
    ring = [Vector((x, -z, h)) for x, z, h in surface["rings"][0]]
    horizontal = [(a, b) for a, b in zip(ring, ring[1:] + ring[:1])
                  if abs(a.z - b.z) < .1 and (a - b).length > .5]
    if not horizontal:
        return 0
    a, b = max(horizontal, key=lambda ab: (ab[1] - ab[0]).length)
    tangent = Vector((b.x - a.x, b.y - a.y, 0)).normalized()
    footprint = building["footprint"]
    center = Vector((sum(p[0] for p in footprint) / len(footprint),
                     -sum(p[1] for p in footprint) / len(footprint), 0))
    mid = sum(ring, Vector()) / len(ring)
    outward = Vector((-tangent.y, tangent.x, 0))
    if outward.dot(mid - center) < 0:
        outward.negate()
    projected = [((p - a).dot(tangent), p.z) for p in ring]
    min_u, max_u = min(p[0] for p in projected), max(p[0] for p in projected)
    low, high = min(p[1] for p in projected), max(p[1] for p in projected)
    angle = math.atan2(tangent.y, tangent.x)
    count = 0
    z = max(low + 2.3, 4.0)
    while z + .8 < high - .35 and count < count_cap:
        u = min_u + 1.3
        while u < max_u - 1.2 and count < count_cap:
            width, height = 1.25, 1.55
            corners = [(u + sx * width * .56, z + sy * height * .56)
                       for sx in (-1, 1) for sy in (-1, 1)]
            if all(pilot.polygon_contains(p, projected) for p in corners):
                point = a + tangent * u
                point.z = z
                frame = point + outward * .15
                glass = point + outward * .25
                sill = point + outward * .23 + Vector((0, 0, -.84))
                append_box(batches["frame"], frame, (width, .15, height), angle)
                append_box(batches["glass"], glass, (width - .18, .04, height - .18), angle)
                append_box(batches["trim"], sill, (width + .12, .22, .08), angle)
                count += 1
            u += 2.8
        z += 3.25
    return count


def add_geometry_windows(city, geometry_walls, mats):
    batches = defaultdict(lambda: {"vertices": [], "faces": []})
    counts = {}
    for building in city["buildings"]:
        bid = building["id"]
        if bid == pilot.HERO_ID:
            continue
        total = 0
        for index in sorted(geometry_walls[bid]):
            if total >= 24:
                break
            total += wall_window_grid(building, building["lod2_surfaces"][index],
                                      batches, 24 - total)
        counts[bid] = total
    objects = [pilot.make_mesh("City_3D_Windows_" + key, batch["vertices"],
                               batch["faces"], mats[key])
               for key, batch in batches.items() if batch["faces"]]
    return counts, objects


def set_overview_camera():
    camera_data = bpy.data.cameras.new("Whole city comparison camera")
    camera = bpy.data.objects.new("Whole city comparison camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (165, -190, 160)
    target = Vector((0, 0, 12))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = 315
    bpy.context.scene.camera = camera
    sun_data = bpy.data.lights.new("Whole city daylight", 'SUN')
    sun = bpy.data.objects.new("Whole city daylight", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-25), math.radians(-35))
    sun_data.energy = 2.6
    sun_data.angle = math.radians(5)
    world = bpy.context.scene.world or bpy.data.worlds.new("Whole city sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (.52, .62, .70, 1)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = .62
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'
    bpy.context.scene.eevee.use_gtao = True
    bpy.context.scene.eevee.gtao_distance = 3
    bpy.context.scene.eevee.gtao_factor = 1.15
    bpy.context.scene.eevee.use_soft_shadows = True
    bpy.context.scene.eevee.taa_render_samples = 64
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 900
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.view_settings.view_transform = 'Filmic'
    bpy.context.scene.view_settings.look = 'Medium High Contrast'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--texture-dir', default='data/raw/plateau')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    scene_path = pathlib.Path(args.scene).resolve()
    output = pathlib.Path(args.output).resolve()
    texture_dir = pathlib.Path(args.texture_dir).resolve()
    city = json.loads(scene_path.read_text(encoding='utf-8'))
    if city.get('schema') != 'therabby.geoengine.map.v0.1' or city.get('data_quality') == 'SYNTHETIC_TEST_FIXTURE':
        raise ValueError('Expected real GeoEngine map with known schema')
    if len(city['buildings']) != 56:
        raise ValueError('This visual study is calibrated for the 56-building Fukushima-east map')
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    styles = rebuild_styles.analyze_city_styles(city, texture_dir)
    if set(styles) != {b['id'] for b in city['buildings']}:
        raise ValueError('Reference-photo style analysis did not cover every building')
    mats = create_materials(output.parent / 'rebuild_all_textures')
    geometry_walls = select_geometry_walls(city, styles)
    pattern_walls = select_pattern_walls(city, styles)
    objects = add_city_shell(city, styles, mats, geometry_walls, pattern_walls)
    objects.extend(rebuild_streets.add_streets(city, mats, pilot.make_mesh, pilot.add_box))
    window_counts, window_objects = add_geometry_windows(city, geometry_walls, mats)
    objects.extend(window_objects)
    hero = next(b for b in city['buildings'] if b['id'] == pilot.HERO_ID)
    hero_windows = pilot.add_hero_windows(hero, mats)
    roof_units = pilot.add_rooftop_equipment(hero, mats)
    objects.extend(pilot.join_details_by_material())
    for obj in objects:
        obj['geoengine_data_quality'] = city['data_quality']
        obj['geoengine_visual_quality'] = 'photo-referenced approximate redraw; no source photo texture'
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', export_apply=True,
                              export_yup=True, export_cameras=False, export_lights=False,
                              export_extras=True, use_selection=True)
    raw = output.read_bytes()
    if len(raw) < 1000:
        raise RuntimeError('GLB export failed')
    counts = Counter(s['tone_index'] for s in styles.values())
    sidecar = {
        'asset': output.name,
        'bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'source_map': scene_path.name,
        'source_map_sha256': hashlib.sha256(scene_path.read_bytes()).hexdigest(),
        'model_type': 'photo_reference_rebuild_all_approximate',
        'building_count': len(city['buildings']),
        'reference_photo_count': len({s['reference_photo'] for s in styles.values()}),
        'reference_photos_embedded': False,
        'wall_tone_distribution_dark_to_light': dict(sorted(counts.items())),
        'window_candidate_walls': sum(len(s['window_surface_indices']) for s in styles.values()),
        'estimated_window_pattern_walls': sum(
            len(indices - geometry_walls[bid]) for bid, indices in pattern_walls.items()
            if bid != pilot.HERO_ID),
        'geometry_window_walls': sum(len(v) for v in geometry_walls.values()),
        'geometry_windows_modeled': sum(window_counts.values()) + hero_windows,
        'hero_roof_units_modeled': roof_units,
        'roads': len(city['roads']),
        'road_width_quality': 'class-estimate',
        'generated_textures': [p.name for p in sorted((output.parent / 'rebuild_all_textures').glob('*.png'))],
        'reference_photo_uri_by_building': {bid: s['reference_photo'] for bid, s in sorted(styles.items())},
        'reference_photo_sha256_by_building': {bid: s['reference_sha256'] for bid, s in sorted(styles.items())},
        'wall_tone_index_by_building': {bid: s['tone_index'] for bid, s in sorted(styles.items())},
        'window_candidate_surface_indices_by_building': {
            bid: s['window_surface_indices'] for bid, s in sorted(styles.items())},
        'limitations': [
            'Photo classification is approximate; windows are neither surveyed nor verified individually',
            'Window-pattern textures are synthetic and may disagree with individual facades',
            'Street surfaces use OSM class-estimated widths; kerbs and stair elevation are approximate',
            'Signs, trees, utility poles, and drivable-lane boundaries are not reconstructed',
            'No ground orthophoto pixels or PLATEAU JPEG pixels are embedded',
        ],
    }
    output.with_suffix('.provenance.json').write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    set_overview_camera()
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
    bpy.context.scene.render.filepath = str(output.with_name(output.stem + '_overview.png'))
    bpy.ops.render.render(write_still=True)
    print('SUCCESS whole city', len(city['buildings']), 'buildings',
          sidecar['geometry_windows_modeled'], 'modeled windows', len(raw), 'GLB bytes')


if __name__ == '__main__':
    main()
