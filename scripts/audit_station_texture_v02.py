#!/usr/bin/env python3
"""Audit embedded station LOD2 JPEGs and make a truthful 1:1 detail comparison."""
from __future__ import annotations

import collections
import hashlib
import io
import json
import pathlib
import struct

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "data/derived/fukushima-station-lod2-overlay"
REPORT = ROOT / "docs/evidence/station_texture_v02_audit.json"
FIGURE = ROOT / "docs/evidence/station_texture_v02_source_variants.png"


def glb_images(path):
    blob = path.read_bytes()
    if blob[:4] != b"glTF" or struct.unpack_from("<I", blob, 8)[0] != len(blob):
        raise ValueError(f"Invalid GLB: {path}")
    json_len = struct.unpack_from("<I", blob, 12)[0]
    data = json.loads(blob[20:20 + json_len])
    bin_header = 20 + json_len
    if blob[bin_header + 4:bin_header + 8] != b"BIN\0":
        raise ValueError(f"No GLB BIN chunk: {path}")
    bin_start = bin_header + 8
    images = {}
    for image in data.get("images", []):
        view = data["bufferViews"][image["bufferView"]]
        raw = blob[bin_start + view.get("byteOffset", 0):
                   bin_start + view.get("byteOffset", 0) + view["byteLength"]]
        with Image.open(io.BytesIO(raw)) as opened:
            size = opened.size
        images[image["name"]] = {"bytes": raw, "size": size, "mime": image["mimeType"]}
    return data, images


def audit():
    manifest = json.loads((OVERLAY / "tileset.json").read_text(encoding="utf-8"))
    source_manifest = json.loads((OVERLAY / "source_photos.json").read_text(encoding="utf-8"))
    sources = {pathlib.PurePosixPath(item["uri"]).stem: item for item in source_manifest["files"]}
    variants = {name: {} for name in ("low", "medium", "high")}
    samplers = {}
    for tile in manifest["tiles"]:
        for name in variants:
            data, images = glb_images(OVERLAY / tile[f"lod2_{name}"]["path"])
            if len(images) != len(data.get("images", [])):
                raise ValueError("Duplicate GLB image names")
            variants[name].update(images)
            samplers[name] = data.get("samplers", [])
    if any(set(images) != set(sources) for images in variants.values()):
        raise ValueError("Source and all three GLB variants must have matching image IDs")
    exact = 0
    dimensions = collections.Counter()
    changed = {"low": 0, "medium": 0}
    for name, source in sources.items():
        path = ROOT / "data/raw/plateau" / source["uri"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError(f"Official JPEG hash mismatch: {path}")
        if hashlib.sha256(variants["high"][name]["bytes"]).digest() != hashlib.sha256(raw).digest():
            raise ValueError(f"High GLB altered the official JPEG: {name}")
        exact += 1
        with Image.open(io.BytesIO(raw)) as image:
            dimensions[f"{image.width}x{image.height}"] += 1
        for quality in changed:
            changed[quality] += variants[quality][name]["size"] != variants["high"][name]["size"]
    for quality, limit in (("low", 512), ("medium", 1024)):
        if any(max(image["size"]) > limit for image in variants[quality].values()):
            raise ValueError(f"{quality} GLB exceeds {limit}px")
    candidate = max(sources, key=lambda key: (
        min(variants["high"][key]["size"]),
        variants["high"][key]["size"][0] * variants["high"][key]["size"][1]))
    canvas = Image.new("RGB", (4 * 512, 550), "#e7eceb")
    draw = ImageDraw.Draw(canvas)
    original = Image.open(ROOT / "data/raw/plateau" / sources[candidate]["uri"]).convert("RGB")
    for index, quality in enumerate(("source", "low", "medium", "high")):
        image = original if quality == "source" else Image.open(io.BytesIO(variants[quality][candidate]["bytes"])).convert("RGB")
        factor = min(1, 512 / max(original.size))
        # Same fractional area of one facade, shown at the original 512-pixel scale.
        w, h = max(1, round(512 * image.width / original.width)), max(1, round(512 * image.height / original.height))
        box = ((image.width - w) // 2, (image.height - h) // 2)
        crop = image.crop((box[0], box[1], box[0] + w, box[1] + h))
        canvas.paste(crop.resize((512, 512), Image.Resampling.BILINEAR), (index * 512, 38))
        draw.text((index * 512 + 8, 10), f"{quality.upper()} {image.width}x{image.height}", fill="#132932")
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(FIGURE, optimize=True)
    report = {
        "schema": "therabby.geoengine.station-texture-audit.v0.2",
        "official_image_count": len(sources), "high_glb_exact_official_jpeg_count": exact,
        "source_dimensions": dict(dimensions.most_common()),
        "images_reduced_from_source": changed,
        "embedded_image_format": "JPEG", "ktx2_used": False,
        "glb_samplers": samplers,
        "tile_renderer_error_target": "not applicable: this viewer loads GLBs, not 3D Tiles",
        "tile_cache_limit": "not applicable to station GLB overlay",
        "comparison_image": str(FIGURE.relative_to(ROOT)).replace("\\", "/"),
        "comparison_image_id": candidate,
        "comparison_method": "central same-fractional crop, source 512 original pixels, derivatives bilinearly scaled for display; no sharpening",
        "source": "Project PLATEAU / Fukushima City 2025",
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = audit()
    print(json.dumps({key: result[key] for key in ("official_image_count", "high_glb_exact_official_jpeg_count", "images_reduced_from_source", "comparison_image")}, ensure_ascii=False))
