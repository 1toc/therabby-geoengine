"""Unit tests for tiled coordinate helpers; geometry inputs are synthetic fixtures."""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_citywide_lod1_tiles as tiles
import diagnose_citywide_lod1_gaps as gap_diagnostics
import build_citywide_road_tiles as city_roads
import prepare_citywide_building_dem as dem
import xml.etree.ElementTree as ET


class CitywideLod1TileTests(unittest.TestCase):
    def test_projected_road_clip_shares_exact_seam_node(self):
        # SYNTHETIC_TEST_FIXTURE: one straight line across a 1 km tile seam.
        a, b = (999.0, 500.0), (1001.0, 500.0)
        west = city_roads.clip_segment(a, b, (0, 0, 1000, 1000))
        east = city_roads.clip_segment(a, b, (1000, 0, 2000, 1000))
        self.assertEqual(west[1], east[0])
        self.assertEqual(city_roads.node_id(west[1]), city_roads.node_id(east[0]))

    def test_gap_classifier_marks_absent_lod1_geometry(self):
        # SYNTHETIC_TEST_FIXTURE: a Building with no geometry, not Fukushima data.
        building = ET.Element("{%s}Building" % gap_diagnostics.geoengine.NS["bldg"])
        self.assertEqual(
            gap_diagnostics.classify_unmatched(
                building, "urn:ogc:def:crs:EPSG::6697",
                {"center_lat": 37.8, "center_lon": 140.4, "half_size_m": 50000}),
            "no_lod1_solid",
        )

    def test_tile_grid_uses_floor_at_negative_and_positive_edges(self):
        self.assertEqual(tiles.tile_index(0, 0), (0, 0))
        self.assertEqual(tiles.tile_index(999.999, 1000), (0, 1))
        self.assertEqual(tiles.tile_index(-0.001, -1000.001), (-1, -2))

    def test_tile_local_axes_are_east_and_south(self):
        self.assertEqual(tiles.output_xy(1234.25, 5678.5, 1, 5), [234.25, 321.5])

    def test_source_manifest_rejects_incomplete_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = pathlib.Path(tmp) / "source_manifest.json"
            manifest_path.write_text(json.dumps({"status": "partial", "municipality_code": "07201", "files": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be complete"):
                tiles.verify_sources(json.loads(manifest_path.read_text(encoding="utf-8")), pathlib.Path(tmp), False)

    def test_mapbox_terrain_rgb_round_trip_at_decimeter_precision(self):
        for elevation in (-123.4, 0.0, 1234.5):
            r, g, b = dem.encode_mapbox_rgb(elevation)
            decoded = -10000 + ((r << 16) + (g << 8) + b) / 10
            self.assertAlmostEqual(decoded, elevation, places=1)

    def test_dem_interpolation_collects_each_pixel_tile(self):
        lat, lon = 37.8004245, 140.3996455
        keys = dem.pixel_tiles(lat, lon)
        self.assertGreaterEqual(len(keys), 1)
        self.assertLessEqual(len(keys), 4)
        self.assertTrue(all(x > 0 and y > 0 for x, y in keys))


if __name__ == "__main__":
    unittest.main()
