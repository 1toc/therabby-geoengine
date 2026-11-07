import json
import pathlib
import struct
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence"


class StationV02ComparisonTests(unittest.TestCase):
    def test_browser_comparison_image_matches_recorded_view(self):
        report = json.loads((EVIDENCE / "station_photo_v02_browser_low_vs_source.json").read_text(encoding="utf-8"))
        png = (EVIDENCE / "station_photo_v02_browser_low_vs_source.png").read_bytes()
        self.assertEqual(report["schema"], "therabby.geoengine.station-photo-compare.v0.2")
        self.assertEqual(report["view_mode"], "ground")
        self.assertFalse(report["baseline_pc_verified"])
        self.assertEqual([sample["variant"] for sample in report["samples"]], ["low", "high"])
        self.assertGreater(report["samples"][1]["photo_rgba8_mip_estimate_bytes"],
                           report["samples"][0]["photo_rgba8_mip_estimate_bytes"])
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (report["width"] * 2, report["height"] + 54))


if __name__ == "__main__":
    unittest.main()
