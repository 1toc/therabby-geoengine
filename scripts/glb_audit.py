"""Read GLB geometry and embedded-image accounting without a browser or Blender."""
import argparse
import hashlib
import io
import json
import struct
from pathlib import Path

from PIL import Image

COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    data = Path(path).read_bytes()
    if data[:4] != b"glTF" or struct.unpack_from("<I", data, 4)[0] != 2:
        raise ValueError("Not a glTF 2.0 GLB")
    if struct.unpack_from("<I", data, 8)[0] != len(data):
        raise ValueError("GLB length mismatch")
    position = 12
    chunks = {}
    while position < len(data):
        length, kind = struct.unpack_from("<II", data, position)
        position += 8
        chunks[kind] = data[position:position + length]
        position += length
    return json.loads(chunks[0x4E4F534A]), chunks[0x004E4942]


def buffer_view(doc, binary, index):
    view = doc["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def accessor_bytes(doc, binary, index):
    accessor = doc["accessors"][index]
    view = doc["bufferViews"][accessor["bufferView"]]
    element_size = COMPONENT_BYTES[accessor["componentType"]] * TYPE_SIZE[accessor["type"]]
    stride = view.get("byteStride", element_size)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return b"".join(binary[start + n * stride:start + n * stride + element_size]
                    for n in range(accessor["count"]))


def geometry_fingerprint(doc, binary):
    """Hash the ordered indices, coordinates and UVs for every mesh primitive."""
    hashes = {}
    for mesh in doc.get("meshes", []):
        digest = hashlib.sha256()
        for primitive in mesh["primitives"]:
            for semantic, index in sorted(primitive.get("attributes", {}).items()):
                if semantic in ("POSITION", "TEXCOORD_0"):
                    digest.update(semantic.encode())
                    digest.update(accessor_bytes(doc, binary, index))
            if "indices" in primitive:
                digest.update(accessor_bytes(doc, binary, primitive["indices"]))
        hashes[mesh.get("name", str(len(hashes)))] = digest.hexdigest()
    return hashes


def audit(path):
    doc, binary = read_glb(path)
    images = []
    for item in doc.get("images", []):
        with Image.open(io.BytesIO(buffer_view(doc, binary, item["bufferView"]))) as image:
            images.append({"size": list(image.size), "format": image.format})
    triangles = sum(doc["accessors"][p["indices"]]["count"] // 3
                    for mesh in doc.get("meshes", []) for p in mesh["primitives"] if "indices" in p)
    pixels = sum(i["size"][0] * i["size"][1] for i in images)
    return {"file": str(path), "bytes": Path(path).stat().st_size,
            "meshes": len(doc.get("meshes", [])), "materials": len(doc.get("materials", [])),
            "triangles": triangles, "images": len(images), "image_formats": {
                kind: sum(i["format"] == kind for i in images) for kind in sorted({i["format"] for i in images})},
            "image_sizes": images, "pixels": pixels,
            "rgba8_mips_estimate_mib": round(pixels * 4 * 4 / 3 / 1048576, 1),
            "geometry_fingerprint": geometry_fingerprint(doc, binary)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("glb", nargs="+")
    parser.add_argument("--output")
    args = parser.parse_args()
    reports = [audit(path) for path in args.glb]
    text = json.dumps(reports, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(json.dumps([{key: value for key, value in report.items()
                       if key not in ("geometry_fingerprint", "image_sizes")}
                      for report in reports], ensure_ascii=False, indent=2))
