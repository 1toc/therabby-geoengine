"""Phase 1 artifact and visual regression checks for the real Fukushima subset."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from glb_audit import audit
from optimize_redrawn_textures import build_variant

ASSETS = ROOT / "dist/real/fukushima-east"


class TestPhase1(unittest.TestCase):
    def test_variant_file_generation_keeps_source_and_uv_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            source = temp / "source.jpg"
            Image.new("RGB", (512, 256), (30, 80, 120)).save(source, quality=91)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            manifest = temp / "source.json"
            manifest.write_text(json.dumps({"atlases": [{"building_id": "synthetic-building",
                "uri": "synthetic/atlas.jpg", "texture": "source.jpg",
                "encoded_sha256": before}]}), encoding="utf-8")
            output = temp / "optimized.json"
            result = build_variant(manifest, output, 256, 88)
            entry = result["atlases"][0]
            self.assertEqual(entry["uri"], "synthetic/atlas.jpg")
            self.assertEqual(entry["size"], [256, 128])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertTrue((temp / entry["texture"]).is_file())
            self.assertNotEqual((temp / entry["texture"]).resolve(), source.resolve())
            with self.assertRaises(ValueError):
                build_variant(manifest, manifest, 256, 88)

    def test_real_glb_coordinates_uv_indices_and_provenance(self):
        original = audit(ASSETS / "city_photo_redrawn_all.glb")
        optimized = audit(ASSETS / "city_photo_optimized.glb")
        self.assertEqual(original["geometry_fingerprint"], optimized["geometry_fingerprint"])
        self.assertEqual(original["triangles"], optimized["triangles"])
        self.assertEqual(original["materials"], optimized["materials"])
        self.assertLess(optimized["pixels"], original["pixels"])
        self.assertLess(optimized["bytes"], original["bytes"])
        sidecar = json.loads((ASSETS / "city_photo_optimized.provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(sidecar["sha256"], hashlib.sha256((ASSETS / "city_photo_optimized.glb").read_bytes()).hexdigest())
        self.assertEqual(sidecar["atlas_manifest"], "redraw_atlas_1536_q88.json")

    def test_same_camera_render_regression(self):
        for view, max_allowed in (("overview", 1.0), ("street", 2.0)):
            before = Image.open(ASSETS / f"city_photo_redrawn_all_{view}.png").convert("RGB")
            after = Image.open(ASSETS / f"city_photo_optimized_{view}.png").convert("RGB")
            self.assertEqual(before.size, after.size)
            difference = ImageChops.difference(before, after)
            mean = ImageStat.Stat(difference).mean
            self.assertLess(max(mean), max_allowed, f"{view} mean difference too large")


if __name__ == "__main__":
    unittest.main()
