"""Survey-check guards and real tile-coordinate checks; no invented survey results."""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_citywide_survey_anchors as survey


class SurveyAnchorTests(unittest.TestCase):
    def test_rejects_unknown_datum_and_insufficient_survey_evidence(self):
        synthetic = {"schema": "therabby.geoengine.survey-anchors.v0.1",
                     "horizontal_crs": "EPSG:4326", "vertical_datum": "T.P. (Tokyo Peil)",
                     "anchors": []}
        with self.assertRaisesRegex(ValueError, "EPSG:6668"):
            survey.validate_input(synthetic)
        synthetic["horizontal_crs"] = "JGD2011 geographic (EPSG:6668)"
        with self.assertRaisesRegex(ValueError, "At least two"):
            survey.validate_input(synthetic)

    def test_synthetic_line_distance_clamps_to_endpoints(self):
        self.assertAlmostEqual(survey.distance_to_segment(5, 3, (0, 0), (10, 0)), 3)
        self.assertAlmostEqual(survey.distance_to_segment(15, 0, (0, 0), (10, 0)), 5)

    def test_real_building_tile_origin_places_outline_at_absolute_projected_point(self):
        manifest = json.loads((survey.BUILDINGS / "tileset.json").read_text(encoding="utf-8"))
        item = next(item for item in manifest["tiles"] if item["id"] == "55_194")
        data = json.loads((survey.BUILDINGS / item["path"]).read_text(encoding="utf-8"))
        point = data["buildings"][0]["footprint"][0]
        east = item["tile_origin_east_m"] + point[0]
        north = item["tile_origin_north_m"] - point[1]
        result = survey.nearest_building(east, north, manifest)
        self.assertLessEqual(result["horizontal_error_m"], 0.001)
        self.assertIsNone(result["foundation_height_tp_m"])

    def test_real_road_node_has_zero_centerline_error_without_deck_claim(self):
        manifest = json.loads((survey.ROADS / "tileset.json").read_text(encoding="utf-8"))
        item = next(item for item in manifest["tiles"] if item["id"] == "55_194")
        data = json.loads((survey.ROADS / item["path"]).read_text(encoding="utf-8"))
        point = data["edges"][0]["points"][0]
        east, north = data["tile_origin_east_m"]+point[0], data["tile_origin_north_m"]-point[1]
        result = survey.nearest_road(east, north, manifest)
        self.assertLessEqual(result["horizontal_error_m"], 0.001)
        self.assertIsNone(result["road_deck_height_tp_m"])


if __name__ == "__main__":
    unittest.main()
