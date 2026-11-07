"""Citywide PLATEAU metadata preflight tests; catalog rows are synthetic fixtures only."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from plan_citywide_plateau import bbox_from_geojson, make_plan, select_city_building_files, validate_download_plan


class TestCitywidePlateauPlan(unittest.TestCase):
    def setUp(self):
        self.boundary = {"type": "FeatureCollection", "features": [{"type": "Feature",
            "properties": {"municipality_code": "07201"},
            "geometry": {"type": "Polygon", "coordinates": [[[140.2, 37.6], [140.5, 37.6],
                [140.5, 38.0], [140.2, 38.0], [140.2, 37.6]]]}}]}
        self.metadata = {"status": "official_2026", "municipality_code": "07201",
                         "source": "synthetic boundary metadata test fixture", "source_sha256": "fixture"}
        self.catalog = {"cities": [{"cityCode": "07201", "year": 2025, "files": {"bldg": [
            {"url": "https://assets.cms.plateau.reearth.io/assets/id/20250101_bldg_12345678_op.gml",
             "code": "12345678", "lod1": 42, "maxLod": 2, "fileSize": 600_000_000},
            {"url": "https://assets.cms.plateau.reearth.io/assets/id/20250101_bldg_12345679_op.gml",
             "code": "12345679", "lod1": 7, "maxLod": 1, "fileSize": 500_000_001},
        ]}}]}

    def test_bbox_from_geojson(self):
        self.assertEqual(bbox_from_geojson(self.boundary), [140.2, 37.6, 140.5, 38.0])

    def test_over_one_gigabyte_is_marked_for_operator_approval_without_download(self):
        plan = make_plan(self.catalog, b"SYNTHETIC_TEST_FIXTURE", [140.2, 37.6, 140.5, 38.0], self.metadata)
        self.assertEqual(plan["status"], "requires_operator_approval")
        self.assertFalse(plan["downloads_performed"])
        self.assertEqual(plan["file_count"], 2)
        self.assertEqual(plan["lod1_feature_count"], 49)
        self.assertEqual(plan["total_file_size_bytes"], 1_100_000_001)

    def test_rejects_non_official_building_url(self):
        self.catalog["cities"][0]["files"]["bldg"][0]["url"] = "https://example.invalid/building.gml"
        with self.assertRaisesRegex(ValueError, "公式PLATEAU"):
            select_city_building_files(self.catalog, "07201", 2025)

    def test_download_gate_requires_explicit_over_1gb_flag(self):
        plan = make_plan(self.catalog, b"SYNTHETIC_TEST_FIXTURE", [140.2, 37.6, 140.5, 38.0], self.metadata)
        with self.assertRaisesRegex(PermissionError, "operator approval"):
            validate_download_plan(plan)
        self.assertEqual(validate_download_plan(plan, approved_over_1gb=True), 1_100_000_001)


if __name__ == "__main__":
    unittest.main()
