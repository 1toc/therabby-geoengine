import json
import math
import pathlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import geoengine as geo

class TestM1(unittest.TestCase):
    def setUp(self):
        self.area=geo.load_area(ROOT/"config/fukushima_station_east.json")

    def test_projection_origin(self):
        self.assertEqual(geo.xy_of(self.area["center_lat"],self.area["center_lon"],self.area),[0,0])
        self.assertGreater(geo.xy_of(self.area["center_lat"],self.area["center_lon"]+.0001,self.area)[0],0)
        self.assertLess(geo.xy_of(self.area["center_lat"]+.0001,self.area["center_lon"],self.area)[1],0)

    def test_road_clip(self):
        p=geo.segment_clip([-200,0],[200,0],100)
        self.assertEqual(p,[[-100.,0.],[100.,0.]])
        self.assertIsNone(geo.segment_clip([200,200],[300,300],100))

    def test_height_quality(self):
        self.assertEqual(geo.osm_height({"height":"11.3 m"}),(11.3,"measured-osm-tag"))
        self.assertEqual(geo.osm_height({})[1],"fallback-placeholder-not-measured")

    def test_osm_build(self):
        source=geo.read_json(ROOT/"fixtures/fictional_osm.json")
        roads,bldgs=geo.parse_osm(source,self.area)
        self.assertEqual(len(roads),2)
        self.assertEqual(len(bldgs),2)
        self.assertEqual(bldgs[0]["height_m"],14)
        self.assertEqual(bldgs[1]["height_quality"],"estimated-from-osm-levels")

    def test_plateau_fixture(self):
        b,count=geo.plateau_buildings([ROOT/"fixtures/minimal_plateau_lod1.gml"],self.area)
        self.assertEqual(count,1)
        self.assertEqual(len(b),1)
        self.assertEqual(b[0]["height_m"],12)
        self.assertEqual(b[0]["source"],"PLATEAU CityGML")

    def test_official_lod1_parser_accepts_small_valid_synthetic_footprint(self):
        # SYNTHETIC_TEST_FIXTURE: 1-2 m² geometry, not authentic Fukushima data.
        source = (ROOT/"fixtures/minimal_plateau_lod1.gml").read_text(encoding="utf-8")
        source = source.replace("140.4623", "140.46201").replace("37.7545", "37.754635")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/"small_synthetic_lod1.gml"
            path.write_text(source, encoding="utf-8")
            buildings, count = geo.plateau_buildings([path], self.area, include_lod2=False)
        self.assertEqual(count, 1)
        self.assertEqual(len(buildings), 1)
        self.assertGreater(geo.polygon_area(buildings[0]["footprint"]), 1)
        self.assertLess(geo.polygon_area(buildings[0]["footprint"]), 2)
        self.assertEqual(buildings[0]["height_m"], 12)

    def test_lod2_surface_rings_and_local_height(self):
        bldg_ns = "http://www.opengis.net/citygml/building/2.0"
        gml_ns = "http://www.opengis.net/gml"
        building = ET.Element(f"{{{bldg_ns}}}Building")
        outer = [(37.7544, 140.4618), (37.7544, 140.4620),
                 (37.7543, 140.4620), (37.7543, 140.4618)]
        inner = [(37.75438, 140.46184), (37.75438, 140.46188),
                 (37.75435, 140.46188), (37.75435, 140.46184)]
        for kind, height in (("GroundSurface", 100), ("RoofSurface", 112)):
            bounded = ET.SubElement(building, f"{{{bldg_ns}}}boundedBy")
            thematic = ET.SubElement(bounded, f"{{{bldg_ns}}}{kind}")
            multi = ET.SubElement(thematic, f"{{{bldg_ns}}}lod2MultiSurface")
            polygon = ET.SubElement(multi, f"{{{gml_ns}}}Polygon")
            boundaries = [("exterior", outer)]
            if kind == "RoofSurface":
                boundaries.append(("interior", inner))
            for boundary_name, points in boundaries:
                boundary = ET.SubElement(polygon, f"{{{gml_ns}}}{boundary_name}")
                ring = ET.SubElement(boundary, f"{{{gml_ns}}}LinearRing")
                pos = ET.SubElement(ring, f"{{{gml_ns}}}posList")
                pos.text = " ".join(f"{lat} {lon} {height}" for lat, lon in points + points[:1])
        surfaces = geo.lod2_surfaces_from_building(building, self.area, "urn:ogc:def:crs:EPSG::6697")
        self.assertEqual(len(surfaces), 2)
        self.assertEqual(len(surfaces[1]["rings"]), 2)
        self.assertEqual(surfaces[0]["rings"][0][0][2], 0)
        self.assertEqual(surfaces[1]["rings"][0][0][2], 12)

    def test_photo_texture_uv_alignment_and_source_guard(self):
        app_ns = geo.NS["app"]
        bldg_ns, gml_ns = geo.NS["bldg"], geo.NS["gml"]
        member = ET.Element(f"{{{app_ns}}}appearanceMember")
        texture = ET.SubElement(member, f"{{{app_ns}}}ParameterizedTexture")
        ET.SubElement(texture, f"{{{app_ns}}}imageURI").text = "56405306_bldg_6697_appearance/test.jpg"
        target = ET.SubElement(texture, f"{{{app_ns}}}target", {"uri": "#photo-poly"})
        coord_list = ET.SubElement(target, f"{{{app_ns}}}TexCoordList")
        ET.SubElement(coord_list, f"{{{app_ns}}}textureCoordinates", {"ring": "#photo-ring"}).text = \
            "0 0 1 0 1 1 0 1 0 0"
        appearances = geo.appearance_targets(member)
        building = ET.Element(f"{{{bldg_ns}}}Building")
        bounded = ET.SubElement(building, f"{{{bldg_ns}}}boundedBy")
        roof = ET.SubElement(bounded, f"{{{bldg_ns}}}RoofSurface")
        multi = ET.SubElement(roof, f"{{{bldg_ns}}}lod2MultiSurface")
        polygon = ET.SubElement(multi, f"{{{gml_ns}}}Polygon", {f"{{{gml_ns}}}id": "photo-poly"})
        exterior = ET.SubElement(polygon, f"{{{gml_ns}}}exterior")
        ring = ET.SubElement(exterior, f"{{{gml_ns}}}LinearRing", {f"{{{gml_ns}}}id": "photo-ring"})
        ET.SubElement(ring, f"{{{gml_ns}}}posList").text = \
            "37.7544 140.4618 100 37.7544 140.4620 100 37.7543 140.4620 100 37.7543 140.4618 100 37.7544 140.4618 100"
        surfaces = geo.lod2_surfaces_from_building(
            building, self.area, "EPSG:6697", appearances, "56405306_bldg_6697_op.gml")
        self.assertEqual(surfaces[0]["texture_uv_rings"][0], [[0, 0], [1, 0], [1, 1], [0, 1]])
        with self.assertRaisesRegex(ValueError, "Unsupported PLATEAU texture path"):
            geo.safe_texture_uri("56405306_bldg_6697_op.gml", "../other.jpg")

    def test_reject_projected_coordinates(self):
        with self.assertRaises(ValueError): geo.extract_coords_from_poslist("399123 44991 50 399124 44994 50")
        with self.assertRaisesRegex(ValueError, "not lat/lon"):
            geo.extract_coords_from_poslist("399123 44991 50", 3, "urn:ogc:def:crs:EPSG::6697")
        with self.assertRaisesRegex(ValueError, "Unsupported or missing PLATEAU CRS"):
            geo.extract_coords_from_poslist("37.75 140.46 50", 3, "EPSG:6670")
        with self.assertRaisesRegex(ValueError, "not lat/lon"):
            geo.extract_coords_from_poslist("140.46 37.75 50", 3, "EPSG:6697")

    def test_plateau_api_bbox_and_link_safety(self):
        u = geo.plateau_index_url(self.area)
        self.assertIn('/datacatalog/citygml/r:', u)
        self.assertIn('140.',u)
        fake = {'results':[{'url':'https://assets.cms.plateau.reearth.io/assets/id/53394509_bldg_6697_op.gml'},
                           {'url':'https://attacker.example/53394509_bldg_6697_op.gml'},
                           {'url':'https://assets.cms.plateau.reearth.io/assets/id/53394509_tran_6697_op.gml'}]}
        self.assertEqual(len(geo.discover_plateau_gml_links(fake)),1)

    def test_select_plateau_2025_lod1_files(self):
        base = "https://assets.cms.plateau.reearth.io/assets/id/"
        def entry(mesh, lod1, size):
            return {"code": mesh, "lod1": lod1, "fileSize": size,
                    "url": base + mesh + "_bldg_6697_op.gml"}
        index = {"cities": [
            {"cityCode": "07201", "year": 2024, "files": {"bldg": [entry("56405306", 100, 50)]}},
            {"cityCode": "07201", "year": 2025, "files": {"bldg": [
                entry("56405306", 1628, 30293767), entry("56405307", 1809, 57423445),
                entry("56405308", 0, 100)]}}]}
        files = geo.select_plateau_files(index, self.area)
        self.assertEqual([f["mesh_code"] for f in files], ["56405306", "56405307"])
        self.assertEqual(sum(f["file_size"] for f in files), 87717212)
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp)/"index.json"
            geo.write_json(source, index)
            geo.fetch_plateau(self.area, pathlib.Path(tmp)/"out", source, dry_run=True)
            self.assertEqual(len(geo.read_json(pathlib.Path(tmp)/"out/plateau_file_list.json")["files"]), 2)

    def test_reject_catalog_city_mismatch_and_oversized_file(self):
        with self.assertRaisesRegex(ValueError, "Expected one PLATEAU city"):
            geo.select_plateau_files({"cities": []}, self.area)
        item = {"url": "https://assets.cms.plateau.reearth.io/assets/id/56405306_bldg_6697_op.gml",
                "lod1": 1, "fileSize": 150_000_001}
        with self.assertRaisesRegex(ValueError, "exceeds 150 MB"):
            geo.select_plateau_files({"cities": [{"cityCode": "07201", "year": 2025,
                "files": {"bldg": [item]}}]}, self.area)

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)/"map.json"
            actual=geo.build(self.area,ROOT/"fixtures/fictional_osm.json",[str(ROOT/"fixtures/minimal_plateau_lod1.gml")],"auto",out)
            geo.validate(out)
            self.assertEqual(len(actual["roads"]),2)
            self.assertEqual(actual["buildings_source_selected"],"plateau")
            self.assertEqual(actual["coordinate_system"]["axes"]["z"],"south")

    def test_shifted_area_rebuild_with_fictional_data(self):
        shifted = dict(self.area, id="synthetic-shifted-aoi",
                       center_lat=self.area["center_lat"] + .00015,
                       center_lon=self.area["center_lon"] - .0001,
                       half_size_m=80)
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)/"shifted-map.json"
            result = geo.build(shifted, ROOT/"fixtures/fictional_osm.json",
                               [str(ROOT/"fixtures/minimal_plateau_lod1.gml")], "auto", out)
            geo.validate(out)
            self.assertEqual(result["data_quality"], "SYNTHETIC_TEST_FIXTURE")
            self.assertGreater(result["statistics"]["roads"], 0)
            self.assertGreater(result["statistics"]["buildings"], 0)

if __name__=="__main__":unittest.main()
