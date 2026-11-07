#!/usr/bin/env python3
"""Fetch a small, georeferenced PLATEAU-Ortho photo patch for Blender.

The Fukushima coverage is the 2024 aerial survey; buildings use 2025 CityGML.
Only the configured AOI plus a 30 m visual margin is downloaded.
"""
import argparse
import hashlib
import io
import math
import pathlib
import urllib.request

from PIL import Image
from geoengine import METERS_PER_DEG_LAT, load_area, write_json

LAYER = "plateau-ortho-2024"
BASE = "https://tile.plateauview.mlit.go.jp/tiles"
ZOOM = 19
TILE = 256


def world_pixel(lat, lon, zoom=ZOOM):
    scale = (2 ** zoom) * TILE
    return ((lon + 180) / 360 * scale,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * scale)


def fetch(area_path, output, cache_dir, zoom=ZOOM, image_size=1024):
    area = load_area(area_path)
    if area.get("plateau_city_code") != "07201":
        raise ValueError("Pinned ortho layer is verified only for Fukushima city code 07201")
    half = area["half_size_m"] + 30
    dlat = half / METERS_PER_DEG_LAT
    dlon = half / (METERS_PER_DEG_LAT * math.cos(math.radians(area["center_lat"])))
    nw = (area["center_lat"] + dlat, area["center_lon"] - dlon)
    se = (area["center_lat"] - dlat, area["center_lon"] + dlon)
    if zoom not in (16, 17, 18, 19) or not 256 <= image_size <= 4096:
        raise ValueError("Supported zoom is 16-19 and image size is 256-4096")
    left, top = world_pixel(*nw, zoom)
    right, bottom = world_pixel(*se, zoom)
    xmin, xmax = math.floor(left / TILE), math.floor(right / TILE)
    ymin, ymax = math.floor(top / TILE), math.floor(bottom / TILE)
    count = (xmax - xmin + 1) * (ymax - ymin + 1)
    if count > 36:
        raise ValueError(f"Too many ortho tiles ({count}); reduce AOI")
    mosaic = Image.new("RGB", ((xmax - xmin + 1) * TILE, (ymax - ymin + 1) * TILE))
    sources = []
    cache_dir = pathlib.Path(cache_dir)
    for y in range(ymin, ymax + 1):
        for x in range(xmin, xmax + 1):
            url = f"{BASE}/{LAYER}/{zoom}/{x}/{y}.png"
            path = cache_dir / LAYER / str(zoom) / str(x) / f"{y}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                raw = path.read_bytes()
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "TherabbyGeoEngine-M1/0.1",
                                                        "Accept": "image/png"})
                with urllib.request.urlopen(req, timeout=45) as response:
                    if response.status != 200 or not response.headers.get("Content-Type", "").startswith("image/png"):
                        raise RuntimeError(f"No official ortho tile at {url}")
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise RuntimeError(f"Ortho tile too large at {url}")
                path.write_bytes(raw)
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            if image.size != (TILE, TILE):
                raise ValueError(f"Unexpected ortho tile size at {url}: {image.size}")
            mosaic.paste(image, ((x - xmin) * TILE, (y - ymin) * TILE))
            sources.append({"url": url, "sha256": hashlib.sha256(raw).hexdigest()})
    # EXTENT maps the precise Web Mercator crop into a square local-meter plane.
    crop = (left - xmin * TILE, top - ymin * TILE,
            right - xmin * TILE, bottom - ymin * TILE)
    patch = mosaic.transform((image_size, image_size), Image.Transform.EXTENT, crop,
                             resample=Image.Resampling.BICUBIC)
    output = pathlib.Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    patch.save(output, format="PNG", optimize=True)
    metadata = {"image": output.name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "source": "Project PLATEAU Ortho", "source_year": 2024,
                "building_data_year": area.get("plateau_year"), "layer": LAYER,
                "area_id": area["id"], "center_lat": area["center_lat"], "center_lon": area["center_lon"],
                "half_size_m": half, "projection": "Web Mercator tiles cropped to local equirectangular AOI",
                "image_size": list(patch.size), "zoom": zoom, "tiles": sources}
    write_json(output.with_suffix(".provenance.json"), metadata)
    print(f"Saved {output} ({output.stat().st_size:,} bytes) from {count} official tiles")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache-dir", default="data/raw/ortho")
    parser.add_argument("--zoom", type=int, default=ZOOM)
    parser.add_argument("--size", type=int, default=1024)
    args = parser.parse_args()
    fetch(args.area, args.output, args.cache_dir, args.zoom, args.size)
