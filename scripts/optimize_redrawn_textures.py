"""Create a separate, reproducible JPEG atlas variant without changing source UVs."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_variant(source_manifest, output_manifest, max_edge, quality):
    source_manifest = Path(source_manifest).resolve()
    output_manifest = Path(output_manifest).resolve()
    if source_manifest == output_manifest:
        raise ValueError("Output manifest must be separate from the source manifest")
    if not 1 <= quality <= 95 or max_edge < 256:
        raise ValueError("quality must be 1..95 and max-edge >= 256")
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    image_dir = output_manifest.parent / output_manifest.stem
    image_dir.mkdir(exist_ok=True)
    entries = []
    for item in source["atlases"]:
        original = source_manifest.parent / item["texture"]
        if sha256(original) != item["encoded_sha256"]:
            raise ValueError(f"Source atlas checksum changed: {original}")
        with Image.open(original) as opened:
            img = opened.convert("RGB")
        width, height = img.size
        scale = min(1, max_edge / max(width, height))
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        resized = img.resize(size, Image.Resampling.LANCZOS) if size != img.size else img
        target = image_dir / Path(item["texture"]).name
        resized.save(target, "JPEG", quality=quality, subsampling=0, optimize=True)
        with Image.open(target) as opened:
            decoded = opened.convert("RGB")
        diff = ImageChops.difference(resized, decoded)
        rms = ImageStat.Stat(diff).rms
        entries.append({
            "building_id": item["building_id"], "uri": item["uri"],
            "texture": target.relative_to(output_manifest.parent).as_posix(),
            "source_texture": item["texture"],
            "source_sha256": item["encoded_sha256"],
            "sha256": sha256(target), "source_size": [width, height],
            "size": list(size), "bytes": target.stat().st_size,
            "jpeg_channel_rms": [round(v, 3) for v in rms],
        })
    result = {
        "method": "Lanczos resize only above max edge, JPEG encode with 4:4:4 chroma; UVs and geometry unchanged",
        "source_manifest": source_manifest.name,
        "max_edge": max_edge, "jpeg_quality": quality,
        "accuracy": "AI-repainted details remain inferred, not surveyed",
        "atlases": entries,
    }
    output_manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="dist/real/fukushima-east/redraw_atlas_manifest.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-edge", type=int, required=True)
    parser.add_argument("--quality", type=int, default=88)
    args = parser.parse_args()
    result = build_variant(args.source, args.output, args.max_edge, args.quality)
    entries = result["atlases"]
    print(json.dumps({"atlases": len(entries), "bytes": sum(e["bytes"] for e in entries),
                      "pixels": sum(e["size"][0] * e["size"][1] for e in entries)}, indent=2))
