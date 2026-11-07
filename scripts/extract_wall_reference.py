"""Rectify a single PLATEAU photo mapped wall into a front-facing reference.

The output is an inspection/reference image, not a claim of recovered detail.
Requires Pillow and NumPy in the development Python runtime.
"""
import argparse
import json
import pathlib

import numpy as np
from PIL import Image


def perspective_coefficients(destination, source):
    rows = []
    values = []
    for (x, y), (u, v) in zip(destination, source):
        rows.append((x, y, 1, 0, 0, 0, -u * x, -u * y))
        values.append(u)
        rows.append((0, 0, 0, x, y, 1, -v * x, -v * y))
        values.append(v)
    return np.linalg.solve(np.asarray(rows), np.asarray(values))


def polygon_triangles(points):
    """Ear clip a simple projected wall ring for reference resampling."""
    signed = sum(points[i][0] * points[(i+1) % len(points)][1] -
                 points[(i+1) % len(points)][0] * points[i][1]
                 for i in range(len(points)))
    winding = 1 if signed > 0 else -1
    remaining = list(range(len(points)))
    triangles = []
    while len(remaining) > 3:
        found = False
        for slot in range(len(remaining)):
            a, b, c = (remaining[(slot-1) % len(remaining)], remaining[slot],
                       remaining[(slot+1) % len(remaining)])
            p, q, r = points[a], points[b], points[c]
            cross = (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
            if winding * cross <= 1e-8:
                continue
            def inside(t):
                a1 = ((q[0]-p[0])*(t[1]-p[1])-(q[1]-p[1])*(t[0]-p[0]))*winding
                a2 = ((r[0]-q[0])*(t[1]-q[1])-(r[1]-q[1])*(t[0]-q[0]))*winding
                a3 = ((p[0]-r[0])*(t[1]-r[1])-(p[1]-r[1])*(t[0]-r[0]))*winding
                return min(a1,a2,a3) >= -1e-8
            if any(inside(points[other]) for other in remaining if other not in (a,b,c)):
                continue
            triangles.append((a,b,c))
            remaining.pop(slot)
            found = True
            break
        if not found:
            raise ValueError('Wall polygon cannot be triangulated in elevation')
    triangles.append(tuple(remaining))
    return triangles


def rectify_complex_wall(photo, surface, width, height, axis):
    ring = surface['rings'][0]
    uv = surface['texture_uv_rings'][0]
    if len(ring) != len(uv) or len(ring) < 3:
        raise ValueError('Wall geometry/UV count mismatch')
    if axis == 'z' and max(p[0] for p in ring)-min(p[0] for p in ring) > 2:
        raise ValueError('Wall is not nearly planar in X; choose another projection')
    horizontal = [p[1] if axis == 'z' else p[0] for p in ring]
    vertical = [p[2] for p in ring]
    lo, hi = min(horizontal), max(horizontal)
    bottom, top = min(vertical), max(vertical)
    if hi-lo < .1 or top-bottom < .1:
        raise ValueError('Degenerate wall extent')
    dst = [((x-lo)/(hi-lo)*(width-1), (top-y)/(top-bottom)*(height-1))
           for x,y in zip(horizontal,vertical)]
    source = np.asarray(photo.convert('RGB'))
    output = np.zeros((height,width,3), dtype=np.uint8)
    for ia,ib,ic in polygon_triangles(dst):
        p,q,r = (np.asarray(dst[i]) for i in (ia,ib,ic))
        xmin = max(0, int(np.floor(min(p[0],q[0],r[0]))))
        xmax = min(width-1, int(np.ceil(max(p[0],q[0],r[0]))))
        ymin = max(0, int(np.floor(min(p[1],q[1],r[1]))))
        ymax = min(height-1, int(np.ceil(max(p[1],q[1],r[1]))))
        yy,xx = np.mgrid[ymin:ymax+1,xmin:xmax+1]
        denom = (q[1]-r[1])*(p[0]-r[0])+(r[0]-q[0])*(p[1]-r[1])
        if abs(denom) < 1e-8:
            continue
        wa = ((q[1]-r[1])*(xx-r[0])+(r[0]-q[0])*(yy-r[1]))/denom
        wb = ((r[1]-p[1])*(xx-r[0])+(p[0]-r[0])*(yy-r[1]))/denom
        wc = 1-wa-wb
        mask = (wa >= -1e-5) & (wb >= -1e-5) & (wc >= -1e-5)
        if not mask.any():
            continue
        us = np.asarray([uv[i][0] for i in (ia,ib,ic)])
        vs = np.asarray([uv[i][1] for i in (ia,ib,ic)])
        sx = np.clip((wa*us[0]+wb*us[1]+wc*us[2])*(photo.width-1),0,photo.width-1)
        sy = np.clip((1-(wa*vs[0]+wb*vs[1]+wc*vs[2]))*(photo.height-1),0,photo.height-1)
        x0,y0 = np.floor(sx).astype(int),np.floor(sy).astype(int)
        x1,y1 = np.minimum(x0+1,photo.width-1),np.minimum(y0+1,photo.height-1)
        fx,fy = (sx-x0)[mask,None],(sy-y0)[mask,None]
        pixels = (source[y0[mask],x0[mask]]*(1-fx)*(1-fy) +
                  source[y0[mask],x1[mask]]*fx*(1-fy) +
                  source[y1[mask],x0[mask]]*(1-fx)*fy +
                  source[y1[mask],x1[mask]]*fx*fy)
        output[yy[mask],xx[mask]] = np.clip(pixels,0,255).astype(np.uint8)
    return Image.fromarray(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', default='dist/real/fukushima-east/map.json')
    parser.add_argument('--texture-dir', default='data/raw/plateau')
    parser.add_argument('--atlas-manifest', help='Use a registered atlas variant instead of official JPEG')
    parser.add_argument('--projection', choices=('quad','z','x'), default='quad')
    parser.add_argument('--building-id', required=True)
    parser.add_argument('--surface-index', required=True, type=int)
    parser.add_argument('--output', required=True)
    parser.add_argument('--width', type=int, default=1400)
    parser.add_argument('--height', type=int, default=1075)
    args = parser.parse_args()
    scene = json.loads(pathlib.Path(args.scene).read_text(encoding='utf-8'))
    building = next(b for b in scene['buildings'] if b['id'] == args.building_id)
    surface = building['lod2_surfaces'][args.surface_index]
    if surface['type'] != 'WallSurface' or len(surface['rings']) != 1:
        raise ValueError('A single-ring WallSurface is required')
    if args.atlas_manifest:
        manifest_path = pathlib.Path(args.atlas_manifest)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        item = next(a for a in manifest['atlases'] if a['uri'] == surface['texture_uri'])
        photo_path = manifest_path.parent / item['texture']
    else:
        photo_path = pathlib.Path(args.texture_dir) / surface['texture_uri']
    photo = Image.open(photo_path).convert('RGB')
    if args.projection != 'quad':
        result = rectify_complex_wall(photo,surface,args.width,args.height,args.projection)
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.save(output)
        print(f'{output} ({args.width}x{args.height}); source {photo.size}; projection {args.projection}')
        return
    if len(surface['rings'][0]) != 4:
        raise ValueError('A four-corner WallSurface is required for quad projection')
    heights = [corner[2] for corner in surface['rings'][0]]
    if not (abs(heights[0] - heights[1]) < .2 and
            abs(heights[2] - heights[3]) < .2 and
            min(heights[:2]) > max(heights[2:]) + .2):
        raise ValueError('Wall corners must be ordered top-left, top-right, bottom-right, bottom-left')
    uv = surface['texture_uv_rings'][0]
    w, h = photo.size
    # The selected PLATEAU walls are ordered top-left, top-right, bottom-right,
    # bottom-left. The source JPEG uses top-left image coordinates.
    source = [(u * w, (1 - v) * h) for u, v in uv]
    dest = [(0, 0), (args.width, 0), (args.width, args.height), (0, args.height)]
    coeffs = perspective_coefficients(dest, source)
    result = photo.transform((args.width, args.height), Image.Transform.PERSPECTIVE,
                             coeffs, resample=Image.Resampling.BICUBIC)
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    print(f'{output} ({args.width}x{args.height}); source {photo.size}; UV {uv}')


if __name__ == '__main__':
    main()
