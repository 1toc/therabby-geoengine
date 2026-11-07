#!/usr/bin/env python3
"""Developer-only AOI overlay: OSM roads/buildings versus PLATEAU footprints.

Requires Pillow on the development PC. This is a visual sanity check, not a
surveyed georeferencing or clinical accuracy test.
"""
import argparse
import json
import pathlib

from PIL import Image, ImageDraw, ImageFont

import geoengine as geo


def make_overlay(map_path, osm_path, output):
    scene = geo.read_json(map_path)
    area = scene["area"]
    roads, osm_buildings = geo.parse_osm(geo.read_json(osm_path), area)
    plateau_buildings = scene["buildings"]
    if scene.get("buildings_source_selected") != "plateau":
        raise ValueError("QA overlay requires a PLATEAU-selected map")

    half = area["half_size_m"]
    scale, pad = 4, 88
    size = int(2 * half * scale + 2 * pad)

    def point(v):
        x, z = v
        return (round(pad + (x + half) * scale), round(pad + (z + half) * scale))

    base = Image.new("RGB", (size, size), "#f7f5ef")
    draw = ImageDraw.Draw(base)
    for meter in range(-int(half), int(half) + 1, 50):
        x = point((meter, 0))[0]
        z = point((0, meter))[1]
        draw.line((x, pad, x, size - pad), fill="#e1e0dc", width=1)
        draw.line((pad, z, size - pad, z), fill="#e1e0dc", width=1)
    draw.rectangle((pad, pad, size - pad, size - pad), outline="#5c6670", width=2)

    for road in roads:
        points = [point(p) for p in road["points"]]
        if len(points) > 1:
            draw.line(points, fill="#bbc1c3", width=max(2, round(road["width_m"] * scale)))
            draw.line(points, fill="#52616b", width=2)

    osm_mask = Image.new("1", (size, size))
    plateau_mask = Image.new("1", (size, size))
    for mask, buildings in ((osm_mask, osm_buildings), (plateau_mask, plateau_buildings)):
        mask_draw = ImageDraw.Draw(mask)
        for building in buildings:
            mask_draw.polygon([point(p) for p in building["footprint"]], fill=1)

    osm_pixels, plateau_pixels = osm_mask.load(), plateau_mask.load()
    pixels = base.load()
    overlap = osm_area = plateau_area = 0
    for z in range(pad, size - pad):
        for x in range(pad, size - pad):
            o, p = osm_pixels[x, z], plateau_pixels[x, z]
            osm_area += bool(o)
            plateau_area += bool(p)
            overlap += bool(o and p)
            if o and p:
                pixels[x, z] = (72, 138, 102)
            elif p:
                pixels[x, z] = (51, 117, 194)
            elif o:
                pixels[x, z] = (237, 147, 58)

    draw = ImageDraw.Draw(base)
    font = ImageFont.load_default()
    draw.text((pad, 20), "Fukushima Station East | real OSM + PLATEAU 2025", fill="#192b38", font=font)
    draw.text((pad, 39), "AOI 200 m square | X east, Z south | north up", fill="#3f5967", font=font)
    draw.rectangle((pad, size - 60, pad + 15, size - 45), fill="#3375c2")
    draw.text((pad + 22, size - 59), f"PLATEAU buildings {len(plateau_buildings)}", fill="#192b38", font=font)
    draw.rectangle((pad + 230, size - 60, pad + 245, size - 45), fill="#ed933a")
    draw.text((pad + 252, size - 59), f"OSM buildings {len(osm_buildings)}", fill="#192b38", font=font)
    draw.rectangle((pad + 460, size - 60, pad + 475, size - 45), fill="#488a66")
    draw.text((pad + 482, size - 59), "overlap", fill="#192b38", font=font)
    osm_fraction = overlap / osm_area if osm_area else 0
    plateau_fraction = overlap / plateau_area if plateau_area else 0
    draw.text((pad, size - 38), f"OSM roads {len(roads)} | overlap: {osm_fraction:.1%} of OSM footprint area; {plateau_fraction:.1%} of PLATEAU footprint area", fill="#3f5967", font=font)

    output = pathlib.Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output)
    result = {
        "source_map": str(map_path), "source_osm": str(osm_path),
        "aoi_half_size_m": half, "osm_roads": len(roads),
        "osm_buildings": len(osm_buildings), "plateau_buildings": len(plateau_buildings),
        "osm_footprint_area_m2_raster": round(osm_area / scale ** 2, 1),
        "plateau_footprint_area_m2_raster": round(plateau_area / scale ** 2, 1),
        "shared_area_m2_raster": round(overlap / scale ** 2, 1),
        "overlap_fraction_of_osm": round(osm_fraction, 3),
        "overlap_fraction_of_plateau": round(plateau_fraction, 3),
        "warning": "Visual/raster alignment check only; OSM coverage differs from PLATEAU. No surveyed anchors or terrain elevation verified."
    }
    geo.write_json(output.with_suffix(".json"), result)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    print("Saved", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True)
    parser.add_argument("--osm", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    make_overlay(args.map, args.osm, args.output)
