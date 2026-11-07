"""Render a reproducible material view of a saved GeoEngine Blender city."""
import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blend', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--view', choices=('overview', 'street'), default='overview')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()))
    scene = bpy.context.scene
    if args.view == 'street':
        camera_data = bpy.data.cameras.new('Street QA Camera')
        camera = bpy.data.objects.new('Street QA Camera', camera_data)
        scene.collection.objects.link(camera)
        camera.location = (-70, -75, 1.7)
        target = Vector((-45, 80, 8))
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera_data.lens = 38
        scene.camera = camera
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(Path(args.output).resolve())
    scene.world.color = (.72, .76, .81)
    light_data = bpy.data.lights.new('City QA Sun', type='SUN')
    light = bpy.data.objects.new('City QA Sun', light_data)
    scene.collection.objects.link(light)
    light.rotation_euler = Vector((.5, -.6, -1)).to_track_quat('-Z', 'Y').to_euler()
    light_data.energy = 2
    bpy.ops.render.render(write_still=True)
    print('Saved', scene.render.filepath)


if __name__ == '__main__':
    main()
