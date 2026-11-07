"""Lightweight street surfaces for the photo-reference city rebuild.

`add_streets` takes the validated GeoEngine map and the mesh helpers from
`blender_rebuild.py`. The OSM road widths are class estimates. Path surfaces,
road edges and the background plane are visual proxies, never surveyed lane,
kerb, step-height or drivable geometry.
"""

import math


PEDESTRIAN_TYPES = frozenset(("footway", "pedestrian", "path"))
STEPS_TYPE = "steps"


def _batch():
    return {"vertices": [], "faces": [], "uvs": []}


def _append_strip(batch, start, end, width, height, lateral=0.0, uv_scale=3.0):
    """Append an upward-facing segment in Blender X east / Y north / Z up."""
    dx = end[0] - start[0]
    dy = -(end[1] - start[1])
    length = math.hypot(dx, dy)
    if length < 0.05:
        return False
    nx, ny = -dy / length, dx / length
    ax, ay = start[0] + nx * lateral, -start[1] + ny * lateral
    bx, by = end[0] + nx * lateral, -end[1] + ny * lateral
    half = width * 0.5
    corners = ((ax + nx * half, ay + ny * half),
               (ax - nx * half, ay - ny * half),
               (bx - nx * half, by - ny * half),
               (bx + nx * half, by + ny * half))
    offset = len(batch["vertices"])
    batch["vertices"].extend((x, y, height) for x, y in corners)
    batch["uvs"].extend((x / uv_scale, y / uv_scale) for x, y in corners)
    batch["faces"].append((offset, offset + 1, offset + 2, offset + 3))
    return True


def _append_kerb(batch, start, end, road_half_width, side):
    """Add a low visual road-edge strip, without asserting a measured kerb."""
    dx = end[0] - start[0]
    dy = -(end[1] - start[1])
    length = math.hypot(dx, dy)
    if length < 0.05:
        return
    nx, ny = -dy / length, dx / length
    lateral = side * (road_half_width + 0.04)
    width = 0.11
    ax, ay = start[0] + nx * lateral, -start[1] + ny * lateral
    bx, by = end[0] + nx * lateral, -end[1] + ny * lateral
    half = width * 0.5
    xy = ((ax + nx * half, ay + ny * half),
          (ax - nx * half, ay - ny * half),
          (bx - nx * half, by - ny * half),
          (bx + nx * half, by + ny * half))
    offset = len(batch["vertices"])
    batch["vertices"].extend((x, y, z) for z in (0.14, 0.025) for x, y in xy)
    batch["faces"].extend(((offset, offset + 1, offset + 2, offset + 3),
                           (offset, offset + 3, offset + 7, offset + 4),
                           (offset + 1, offset + 5, offset + 6, offset + 2)))


def add_streets(city, materials, make_mesh, add_box):
    """Build five batched surfaces and return their Blender mesh objects.

    Expected material keys: `asphalt`, `paving`; optional `steps` and `kerb`.
    `add_box` is accepted for the shared builder interface but unused: all
    geometry is batched to avoid a draw call for every OSM segment.
    """
    if city.get("schema") != "therabby.geoengine.map.v0.1":
        raise ValueError("Unsupported GeoEngine map schema")
    if "asphalt" not in materials or "paving" not in materials:
        raise ValueError("Street rebuild needs asphalt and paving materials")
    half = max(145.0, float(city["area"]["half_size_m"]) + 45.0)
    ground = make_mesh(
        "Repaint_Ground_Visual_Proxy_Not_Orthophoto",
        [(-half, -half, -0.08), (half, -half, -0.08),
         (half, half, -0.08), (-half, half, -0.08)],
        [(0, 1, 2, 3)], materials["paving"],
        [(-half / 4, -half / 4), (half / 4, -half / 4),
         (half / 4, half / 4), (-half / 4, half / 4)],
    )
    ground["geoengine_visual_accuracy"] = "illustrative flat ground"
    ground["geoengine_source"] = "GeoEngine area extent; no orthophoto pixels"

    batches = {"vehicle": _batch(), "pedestrian": _batch(),
               "steps": _batch(), "kerb": {"vertices": [], "faces": []}}
    road_counts = {"vehicle": 0, "pedestrian": 0, "steps": 0}
    for road in city["roads"]:
        width = float(road["width_m"])
        if not math.isfinite(width) or width <= 0:
            raise ValueError(f"Invalid road width for {road['id']}")
        points = road["points"]
        if road["highway"] == STEPS_TYPE:
            kind = "steps"
        elif road["highway"] in PEDESTRIAN_TYPES:
            kind = "pedestrian"
        else:
            kind = "vehicle"
        road_counts[kind] += 1
        height = {"vehicle": 0.025, "pedestrian": 0.045, "steps": 0.05}[kind]
        for start, end in zip(points, points[1:]):
            if not all(math.isfinite(float(v)) for v in (*start, *end)):
                raise ValueError(f"Invalid OSM road coordinate for {road['id']}")
            if not _append_strip(batches[kind], start, end, width, height):
                continue
            if kind == "vehicle":
                _append_kerb(batches["kerb"], start, end, width / 2, -1)
                _append_kerb(batches["kerb"], start, end, width / 2, 1)

    names = {
        "vehicle": "OSM_Vehicle_Roads_Class_Width_Proxy",
        "pedestrian": "OSM_Pedestrian_Paving_Class_Width_Proxy",
        "steps": "OSM_Steps_Flat_Footprint_Proxy",
        "kerb": "Road_Edge_Illustrative_Not_Surveyed",
    }
    material_for = {
        "vehicle": materials["asphalt"],
        "pedestrian": materials["paving"],
        "steps": materials.get("steps", materials["paving"]),
        "kerb": materials.get("kerb", materials.get("trim", materials["paving"])),
    }
    objects = [ground]
    for key in ("vehicle", "pedestrian", "steps", "kerb"):
        batch = batches[key]
        if not batch["faces"]:
            continue
        obj = make_mesh(names[key], batch["vertices"], batch["faces"],
                        material_for[key], batch.get("uvs"))
        obj["geoengine_visual_accuracy"] = "illustrative; not surveyed"
        obj["geoengine_source"] = "OpenStreetMap road centerlines"
        obj["geoengine_width_quality"] = "class-estimate"
        if key == "steps":
            obj["geoengine_vertical_quality"] = "flat footprint; no stair elevation"
        objects.append(obj)
    ground["geoengine_road_counts"] = str(road_counts)
    return objects
