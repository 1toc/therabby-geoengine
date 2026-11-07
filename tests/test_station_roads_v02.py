import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_station_roads_v02 import build  # noqa: E402


class TestStationRoadsV02(unittest.TestCase):
    def test_real_station_corridor_keeps_provenance_and_dem(self):
        result = build()
        self.assertEqual(result["projected_crs"], "EPSG:6677")
        self.assertGreater(result["road_count"], 0)
        self.assertEqual(len(result["terrain"]["heights_relative_m"]), 61)
        self.assertTrue(all(r["geometry_quality"] == "official-road-extent-not-carriageway"
                            for r in result["roads"]))
        self.assertEqual(len(result["sources"]), 3)

    def test_unknown_vertical_datum_fails(self):
        import tempfile
        source = json.loads((ROOT / "dist/real/fukushima-east-1km/terrain_grid_5m.json").read_text(encoding="utf-8"))
        source["vertical_datum"] = "unknown"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "dem.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "vertical datum"):
                build(dem_source=path)


if __name__ == "__main__":
    unittest.main()
