"""Render the same Fukushima wall from photo and redraw Blender projects."""
import argparse
import pathlib
import sys

import bpy
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blend', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    bpy.ops.wm.open_mainfile(filepath=str(pathlib.Path(args.blend).resolve()))
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            obj.hide_render = not (obj.name.startswith('City_Photo_a4fdf53b') or
                                   obj.name.startswith('City_Texture_a4fdf53b') or
                                   obj.name.startswith('City_Texture_bc117_wall12'))
    camera_data = bpy.data.cameras.new('Wall QA Camera')
    camera = bpy.data.objects.new('Wall QA Camera', camera_data)
    bpy.context.scene.collection.objects.link(camera)
    target = Vector((-11.7, -1.7, 13.4))
    camera.location = (45, -1.7, 13.4)
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = 37
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.use_gtao = True
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(pathlib.Path(args.output).resolve())
    scene.world.color = (0.8, 0.8, 0.8)
    light_data = bpy.data.lights.new('Wall QA Sun', type='SUN')
    light = bpy.data.objects.new('Wall QA Sun', light_data)
    bpy.context.scene.collection.objects.link(light)
    light.rotation_euler = (Vector((-1, 0, -1))).to_track_quat('-Z', 'Y').to_euler()
    light_data.energy = 2.0
    bpy.ops.render.render(write_still=True)
    print('Saved', scene.render.filepath)


if __name__ == '__main__':
    main()
