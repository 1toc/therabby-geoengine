"""Regression checks for the exported four-tile Fukushima preview."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from glb_audit import accessor_bytes, read_glb

ASSETS = ROOT / "dist/real/fukushima-east"
TILES = ASSETS / "tiles-crisp"


def vertex_uvs(doc, binary):
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            positions = accessor_bytes(doc, binary, primitive["attributes"]["POSITION"])
            uv_accessor = primitive["attributes"].get("TEXCOORD_0")
            texcoords = accessor_bytes(doc, binary, uv_accessor) if uv_accessor is not None else None
            for offset in range(0, len(positions), 12):
                xyz = struct.unpack_from("<fff", positions, offset)
                uv = struct.unpack_from("<ff", texcoords, offset // 12 * 8) if texcoords else None
                yield xyz, uv


class TestTileAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((TILES / "tileset.json").read_text(encoding="utf-8"))
        cls.seams = {}
        cls.road_nodes = {}

    def test_manifest_hashes_and_bounds(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema"], "therabby.geoengine.tileset.prototype.v0.1")
        self.assertEqual(len(manifest["tiles"]), 4)
        source = ASSETS / manifest["source_model"]
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), manifest["source_model_sha256"])
        for tile in manifest["tiles"]:
            path = TILES / tile["glb"]
            self.assertEqual(path.stat().st_size, tile["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), tile["sha256"])
            doc, binary = read_glb(path)
            self.assertEqual(len(doc["meshes"]), tile["mesh_count"])
            x0, z0, x1, z1 = tile["bounds"]
            self.assertEqual(x1-x0, 100)
            self.assertEqual(z1-z0, 100)
            points = list(vertex_uvs(doc, binary))
            self.assertTrue(points)
            for (x, y, z), uv in points:
                self.assertLessEqual(x0-0.001, x)
                self.assertLessEqual(x, x1+0.001)
                self.assertLessEqual(z0-0.001, z)
                self.assertLessEqual(z, z1+0.001)
                self.assertTrue(all(map(lambda n: n == n and abs(n) < 1000,
                                        (x, y, z) + (uv or ()))))
            self.seams[tile["id"]] = {
                tuple(round(c, 4) for c in xyz): {tuple(round(c, 4) for c in uv2) if uv2 else None
                for p2, uv2 in points if all(abs(a-b)<1e-4 for a,b in zip(p2,xyz))}
                for xyz, uv in points if abs(xyz[0])<1e-4 or abs(xyz[2])<1e-4
            }

    def test_shared_geometry_and_uv_are_identical(self):
        if not self.seams:
            self.test_manifest_hashes_and_bounds()
        for a,b,axis in (("0_0","1_0",0),("0_1","1_1",0),
                         ("0_0","0_1",2),("1_0","1_1",2)):
            left = {p:uv for p,uv in self.seams[a].items() if abs(p[axis])<1e-4}
            right = {p:uv for p,uv in self.seams[b].items() if abs(p[axis])<1e-4}
            self.assertTrue(left, (a,b))
            self.assertEqual(left,right, (a,b))

    def test_road_endpoint_ids_connect_across_tiles(self):
        nodes = {}
        for tile in self.manifest["tiles"]:
            payload = json.loads((TILES / tile["roads"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["tile_id"],tile["id"])
            self.assertEqual(len(payload["roads"]),tile["road_fragments"])
            for road in payload["roads"]:
                for point,node in zip((road["points"][0],road["points"][-1]),road["endpoint_nodes"]):
                    if node:
                        nodes.setdefault(node,[]).append((tile["id"],point))
        self.assertGreaterEqual(len(nodes),10)
        for node, entries in nodes.items():
            self.assertEqual(len(entries),2,node)
            self.assertEqual(entries[0][1],entries[1][1],node)
            self.assertNotEqual(entries[0][0],entries[1][0],node)

    def test_wall_web_variant_preserves_png_masters(self):
        master = json.loads((ASSETS / "redraw_manifest_crisp.json").read_text(encoding="utf-8"))
        web = json.loads((ASSETS / "redraw_manifest_crisp_web.json").read_text(encoding="utf-8"))
        self.assertEqual(len(master["walls"]),12)
        self.assertEqual(len(web["walls"]),12)
        for source, item in zip(master["walls"],web["walls"]):
            self.assertEqual((source["building_id"],source["surface_index"]),
                             (item["building_id"],item["surface_index"]))
            self.assertEqual(source["texture"],item["source_texture"])
            original = ASSETS / source["texture"]
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),item["source_sha256"])
            if source.get("projection", "quad") == "quad":
                encoded = ASSETS / item["texture"]
                self.assertEqual(encoded.stat().st_size,item["bytes"])
                self.assertEqual(hashlib.sha256(encoded.read_bytes()).hexdigest(),item["sha256"])
                self.assertLess(max(item["jpeg_channel_rms"]),4)
            else:
                self.assertEqual(item["texture"],source["texture"])


if __name__ == "__main__":
    unittest.main()
