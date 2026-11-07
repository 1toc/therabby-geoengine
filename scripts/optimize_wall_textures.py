"""Encode direct wall repaints for Web delivery while preserving their PNG masters."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_variant(source_manifest, output_manifest, quality=94):
    source_manifest = Path(source_manifest).resolve()
    output_manifest = Path(output_manifest).resolve()
    if source_manifest == output_manifest:
        raise ValueError("Output manifest must be separate from the source manifest")
    if not 1 <= quality <= 95:
        raise ValueError("JPEG quality must be 1..95")
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    output_dir = output_manifest.parent / "redraw_textures_web"
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for item in source["walls"]:
        original = (source_manifest.parent / item["texture"]).resolve()
        if not original.is_file():
            raise FileNotFoundError(original)
        entry = item.copy()
        entry["source_texture"] = item["texture"]
        entry["source_sha256"] = sha256(original)
        # The pure-black polygon exterior is a UV mask. Keep it lossless.
        if item.get("projection", "quad") != "quad":
            entry["encoded_format"] = "PNG (lossless polygon mask)"
            entries.append(entry)
            continue
        target = output_dir / (original.stem + f"_q{quality}.jpg")
        with Image.open(original) as image:
            rgb = image.convert("RGB")
            rgb.save(target, "JPEG", quality=quality, subsampling=0, optimize=True)
        with Image.open(target) as image:
            decoded = image.convert("RGB")
        rms = ImageStat.Stat(ImageChops.difference(rgb, decoded)).rms
        entry["texture"] = target.relative_to(output_manifest.parent).as_posix()
        entry["sha256"] = sha256(target)
        entry["bytes"] = target.stat().st_size
        entry["size"] = list(rgb.size)
        entry["jpeg_channel_rms"] = [round(value, 3) for value in rms]
        entry["encoded_format"] = f"JPEG quality {quality}, 4:4:4"
        entries.append(entry)
    result = {key:value for key,value in source.items() if key != "walls"}
    result["method"] = source["method"] + f" Quad wall PNGs encoded as JPEG q{quality} 4:4:4; polygon masks remain PNG."
    result["source_manifest"] = source_manifest.name
    result["walls"] = entries
    output_manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--quality",type=int,default=94)
    args = parser.parse_args()
    result = build_variant(args.source,args.output,args.quality)
    print(json.dumps({"walls":len(result["walls"]),
        "jpeg_bytes":sum(item.get("bytes",0) for item in result["walls"]),
        "jpeg_max_rms":max((max(item["jpeg_channel_rms"]) for item in result["walls"]
                        if "jpeg_channel_rms" in item),default=0)},indent=2))
