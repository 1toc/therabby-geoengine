"""Checks station photo overlay coordinates and exact LOD1 replacement boundaries."""
import hashlib
import json
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_station_lod2_overlay as overlay  # noqa: E402


class StationLod2OverlayTests(unittest.TestCase):
    def test_projected_surface_uses_tile_local_axes_and_visual_ground_base(self):
        tile = {"tile_origin_east_m": 55000, "tile_origin_north_m": 195000}
        surface = {"type": "RoofSurface", "rings": [[[0, 0, 5], [10, 0, 5], [10, 10, 5]]],
                   "texture_uri": "official.jpg", "texture_uv_rings": [[[0, 0], [1, 0], [1, 1]]]}
        result = overlay.tile_surface(surface, (55386, 194867), tile, 70)
        self.assertEqual(result["rings"], [[[386, 133, 75], [396, 133, 75], [396, 143, 75]]])
        self.assertEqual(result["texture_uv_rings"], surface["texture_uv_rings"])
        self.assertEqual(surface["rings"][0][0], [0, 0, 5])
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            overlay.tile_surface({"rings": [[[math.nan, 0, 0]]]}, (55386, 194867), tile, 70)

    def test_real_station_overlay_replaces_exact_official_ids(self):
        path = overlay.OUTPUT / "tileset.json"
        if not path.exists():
            self.skipTest("Generated 300 m station overlay is not present")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], overlay.SCHEMA)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["area"]["half_size_m"], 150)
        self.assertEqual(manifest["lod2_buildings"], 117)
        self.assertEqual(manifest["official_photo_count"], 117)
        self.assertEqual({tile["id"] for tile in manifest["tiles"]}, {"55_194", "55_195"})
        photo_manifest = json.loads((path.parent / manifest["source_photos"]).read_text(encoding="utf-8"))
        self.assertEqual(len(photo_manifest["files"]), 117)
        for record in photo_manifest["files"]:
            image = overlay.TEXTURE_DIR / pathlib.PurePosixPath(record["uri"])
            self.assertEqual(image.stat().st_size, record["bytes"])
            self.assertEqual(overlay.sha256(image), record["sha256"])
        all_ids = set()
        for tile in manifest["tiles"]:
            scene_path = path.parent / tile["scene"]
            lod1_path = overlay.LOD1_TILESET.parent / tile["source_lod1_tile"]
            self.assertEqual(overlay.sha256(scene_path), tile["scene_sha256"])
            self.assertEqual(overlay.sha256(lod1_path), tile["source_lod1_sha256"])
            scene = json.loads(scene_path.read_text(encoding="utf-8"))
            lod1 = json.loads(lod1_path.read_text(encoding="utf-8"))
            ids = {building["id"] for building in scene["buildings"]}
            self.assertEqual(ids, set(tile["replaced_building_ids"]))
            self.assertFalse(ids & all_ids)
            all_ids.update(ids)
            self.assertTrue(ids.issubset({building["id"] for building in lod1["buildings"]}))
            for building in scene["buildings"]:
                heights = [point[2] for surface in building["lod2_surfaces"]
                           for ring in surface["rings"] for point in ring]
                self.assertAlmostEqual(min(heights), building["base_elevation_m"], places=2)
                for surface in building["lod2_surfaces"]:
                    if surface.get("texture_uri"):
                        self.assertEqual([len(r) for r in surface["rings"]],
                                         [len(r) for r in surface["texture_uv_rings"]])
            for key in ("lod1_filtered", "lod2_low", "lod2_medium", "lod2_high"):
                asset = tile[key]
                output = path.parent / asset["path"]
                self.assertEqual(output.stat().st_size, asset["byte_length"])
                self.assertEqual(overlay.sha256(output), asset["sha256"])
                self.assertEqual(output.read_bytes()[:4], b"glTF")
            self.assertEqual(tile["lod1_filtered"]["buildings"] + tile["lod2_buildings"],
                             next(t["buildings"] for t in json.loads((ROOT / "data/derived/fukushima-citywide-lod1-glb/tileset.json").read_text(encoding="utf-8"))["tiles"] if t["id"] == tile["id"]))
        self.assertEqual(len(all_ids), 117)


if __name__ == "__main__":
    unittest.main()
