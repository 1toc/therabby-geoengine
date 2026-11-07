"""Extract cautious facade style hints from PLATEAU JPEGs for a rebuilt city.

This module runs inside Blender at build time. Official images are read only as
references; loaded image datablocks are removed before returning, so a caller
can save a .blend without accidentally packing the source photographs.

The returned window candidates are visual hypotheses, never surveyed openings.
"""

from array import array
import hashlib
import math
from pathlib import Path, PurePosixPath
import statistics

import bpy


def _inside_polygon(x, y, ring):
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y):
            intersect_x = (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            if x < intersect_x:
                inside = not inside
    return inside


def _sample_pixel(pixels, width, height, u, v):
    # Blender's image.pixels starts at the lower-left, as do glTF UVs.
    x = max(0, min(width - 1, int(u * width)))
    y = max(0, min(height - 1, int(v * height)))
    offset = (y * width + x) * 4
    return (pixels[offset], pixels[offset + 1], pixels[offset + 2])


def _luminance(rgb):
    return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]


def _percentile(values, proportion):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * proportion))]


def _sample_uv_polygon(surface, pixels, width, height, steps=5):
    """Return valid wall colors from well inside each UV ring."""
    samples = []
    for uv_ring in surface.get("texture_uv_rings", []):
        if len(uv_ring) < 3:
            continue
        lo_u = min(p[0] for p in uv_ring)
        hi_u = max(p[0] for p in uv_ring)
        lo_v = min(p[1] for p in uv_ring)
        hi_v = max(p[1] for p in uv_ring)
        if hi_u - lo_u < 1 / width or hi_v - lo_v < 1 / height:
            continue
        for row in range(steps):
            for col in range(steps):
                u = lo_u + (col + .5) / steps * (hi_u - lo_u)
                v = lo_v + (row + .5) / steps * (hi_v - lo_v)
                if not _inside_polygon(u, v, uv_ring):
                    continue
                rgb = _sample_pixel(pixels, width, height, u, v)
                lum = _luminance(rgb)
                # Sparse JPEG atlases use black padding. Near-white is often
                # overexposed roof/sky, not a reliable facade material sample.
                if .05 < lum < .96:
                    samples.append((lum, rgb))
    return samples


def _wall_quad(surface):
    """Find physical rectangle corners and matching UVs for a simple wall."""
    if (surface.get("type") != "WallSurface" or len(surface.get("rings", [])) != 1 or
            len(surface["rings"][0]) != 4 or
            len(surface.get("texture_uv_rings", [])) != 1 or
            len(surface["texture_uv_rings"][0]) != 4):
        return None
    points = surface["rings"][0]
    uv = surface["texture_uv_rings"][0]
    low = min(p[2] for p in points)
    high = max(p[2] for p in points)
    height = high - low
    if height < 4:
        return None
    bottom = [i for i, p in enumerate(points) if abs(p[2] - low) < .2]
    top = [i for i, p in enumerate(points) if abs(p[2] - high) < .2]
    if len(bottom) != 2 or len(top) != 2:
        return None
    bottom.sort(key=lambda i: (points[i][0], points[i][1]))
    left, right = bottom
    dx = points[right][0] - points[left][0]
    dy = points[right][1] - points[left][1]
    width = math.hypot(dx, dy)
    if width < 5:
        return None
    ux, uy = dx / width, dy / width
    top.sort(key=lambda i: ((points[i][0] - points[left][0]) * ux +
                            (points[i][1] - points[left][1]) * uy))
    top_left, top_right = top
    top_width = math.hypot(points[top_right][0] - points[top_left][0],
                           points[top_right][1] - points[top_left][1])
    if abs(top_width - width) > max(.5, width * .08):
        return None
    # The upper corners must align above the lower corners. This rejects
    # sloped roof/step polygons even when they have four vertices.
    for bottom_i, top_i in ((left, top_left), (right, top_right)):
        delta = math.hypot(points[top_i][0] - points[bottom_i][0],
                           points[top_i][1] - points[bottom_i][1])
        if delta > .5:
            return None
    # Reject strongly non-planar quadrilaterals. The horizontal wall normal
    # derives from the lower edge and the wall must stay near that plane.
    nx, ny = -uy, ux
    for index in top:
        plane_distance = abs((points[index][0] - points[left][0]) * nx +
                             (points[index][1] - points[left][1]) * ny)
        if plane_distance > .3:
            return None
    return {
        "width": width,
        "height": height,
        "uv_bl": uv[left], "uv_br": uv[right],
        "uv_tl": uv[top_left], "uv_tr": uv[top_right],
    }


def _sample_rectified_wall(quad, pixels, width, height, columns=24, rows=20):
    """Map a physical wall grid through its four UV corners into the atlas."""
    grid = []
    valid_count = 0
    for row in range(rows):
        t = (row + .5) / rows
        values = []
        for col in range(columns):
            s = (col + .5) / columns
            bl, br = quad["uv_bl"], quad["uv_br"]
            tl, tr = quad["uv_tl"], quad["uv_tr"]
            u = ((1 - t) * ((1 - s) * bl[0] + s * br[0]) +
                 t * ((1 - s) * tl[0] + s * tr[0]))
            v = ((1 - t) * ((1 - s) * bl[1] + s * br[1]) +
                 t * ((1 - s) * tl[1] + s * tr[1]))
            lum = _luminance(_sample_pixel(pixels, width, height, u, v))
            values.append(lum)
            valid_count += lum > .05
        grid.append(values)
    return grid, valid_count / (rows * columns)


def _runs(mask):
    count = 0
    active = False
    for value in mask:
        if value and not active:
            count += 1
        active = value
    return count


def _is_window_candidate(quad, pixels, width, height):
    grid, valid_fraction = _sample_rectified_wall(quad, pixels, width, height)
    if valid_fraction < .85:
        return False
    values = [value for row in grid for value in row if value > .05]
    if len(values) < 100:
        return False
    q20 = _percentile(values, .2)
    q80 = _percentile(values, .8)
    contrast = q80 - q20
    dark_threshold = q80 * .65
    dark_fraction = sum(value < dark_threshold for value in values) / len(values)
    if contrast < .15 or not (.12 <= dark_fraction <= .65) or q80 < .28:
        return False
    # Windows usually repeat across a facade. Shadows, blank walls and atlas
    # seams can be high-contrast but should not create a window grid by fiat.
    column_density = [sum(grid[row][col] < dark_threshold for row in range(3, 17)) / 14
                      for col in range(24)]
    column_peaks = [density >= .22 for density in column_density]
    if _runs(column_peaks) < 3:
        return False
    if quad["height"] >= 8:
        row_density = [sum(grid[row][col] < dark_threshold for col in range(3, 21)) / 18
                       for row in range(20)]
        if _runs([density >= .20 for density in row_density]) < 2:
            return False
    return True


def _reference_path(texture_dir, uri):
    path = PurePosixPath(uri)
    if path.is_absolute() or not path.parts or any(part in (".", "..") for part in path.parts):
        raise ValueError(f"Unsafe texture URI: {uri}")
    root = Path(texture_dir).resolve()
    result = root.joinpath(*path.parts).resolve()
    if not result.is_relative_to(root) or not result.is_file():
        raise FileNotFoundError(f"Missing PLATEAU reference JPEG: {uri}")
    return result


def analyze_city_styles(city, texture_dir):
    """Return per-building colors and conservative window surface indices.

    `city` is a GeoEngine map dictionary; `texture_dir` is the root folder for
    `texture_uri` paths. Returned tone indices are ordered 0=darkest to
    3=lightest across the given city. Source images are never returned or kept
    in Blender datablocks.
    """
    styles = {}
    for building in city["buildings"]:
        uri_set = {surface["texture_uri"] for surface in building.get("lod2_surfaces", [])
                   if surface.get("texture_uri")}
        if len(uri_set) != 1:
            raise ValueError(f"Expected exactly one reference JPEG for {building['id']}: {len(uri_set)}")
        uri = next(iter(uri_set))
        photo_path = _reference_path(texture_dir, uri)
        image = bpy.data.images.load(str(photo_path), check_existing=False)
        try:
            w, h = image.size
            if max(w, h) > 1024:
                scale = 1024 / max(w, h)
                image.scale(max(1, round(w * scale)), max(1, round(h * scale)))
                w, h = image.size
            pixels = array('f', [0.0]) * (w * h * 4)
            image.pixels.foreach_get(pixels)
            wall_samples = []
            windows = []
            for index, surface in enumerate(building.get("lod2_surfaces", [])):
                if surface.get("type") != "WallSurface" or not surface.get("texture_uv_rings"):
                    continue
                wall_samples.extend(_sample_uv_polygon(surface, pixels, w, h))
                quad = _wall_quad(surface)
                if quad and _is_window_candidate(quad, pixels, w, h):
                    windows.append(index)
            if not wall_samples:
                raise ValueError(f"No valid wall color samples for {building['id']}")
            wall_samples.sort(key=lambda sample: sample[0])
            low = round(len(wall_samples) * .3)
            high = max(low + 1, round(len(wall_samples) * .8))
            selected = [rgb for _, rgb in wall_samples[low:high]]
            rgb = tuple(round(statistics.median(color[i] for color in selected), 4)
                        for i in range(3))
            styles[building["id"]] = {
                "tone_index": None,
                "wall_color": rgb,
                "window_surface_indices": windows,
                "reference_photo": uri,
                "reference_sha256": hashlib.sha256(photo_path.read_bytes()).hexdigest(),
                "wall_samples": len(wall_samples),
            }
        finally:
            bpy.data.images.remove(image)
    ranked = sorted(styles, key=lambda building_id: (_luminance(styles[building_id]["wall_color"]),
                                                      building_id))
    for rank, building_id in enumerate(ranked):
        styles[building_id]["tone_index"] = min(3, rank * 4 // len(ranked))
    return styles
