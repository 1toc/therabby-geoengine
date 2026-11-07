"""Synthetic tests only; no authentic Fukushima geodata shipped."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_station_road_split import build,SCHEMA  # noqa: E402

def encoded(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()

class SyntheticRoadSplitTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.station=root/"road_extent.json"
        self.manifest=root/"roads"/"tileset.json"
        self.tile=root/"roads"/"tiles"/"55_195.json"
        self.station_data={
            "schema":"therabby.geoengine.station-road-corridor.v0.2",
            "status":"complete","projected_crs":"EPSG:6677",
            "center_east_m":55500,"center_north_m":195500,
            "bounds_local_xz_m":[-150,-150,150,150],
            "roads":[{"id":"fictional-plateau-road",
                     "geometry_quality":"official-road-extent-not-carriageway",
                     "polygon":[[-40,-10],[40,-10],[40,10],[-40,10]]}]
        }
        self.tile_data={
            "schema":"therabby.geoengine.citywide-road-tile.v0.1",
            "tile_id":"55_195","projected_crs":"EPSG:6677",
            "tile_origin_east_m":55000,"tile_origin_north_m":196000,
            "edges":[{"id":"fictional-osm-road","points":[[462,500],[538,500]],
                      "highway":"secondary","road_class":"drive",
                      "bridge_osm_tag":"no","tunnel_osm_tag":"no",
                      "access_osm_tag":"yes","width_m":8,"width_quality":"class-estimate",
                      "ground_height_from_tp_m":80,"ground_height_to_tp_m":80}]}
        self.write()

    def write(self):
        encoded(self.station,self.station_data)
        checksum=encoded(self.tile,self.tile_data)
        self.index_data={
            "schema":"therabby.geoengine.citywide-road-tiles.v0.1",
            "status":"complete","projected_crs":"JGD2011 / Japan Plane Rectangular CS IX (EPSG:6677)",
            "tiles":[{"id":"55_195","path":"tiles/55_195.json",
                      "sha256":checksum,"bbox_east_north_m":[55000,195000,56000,196000]}]}
        encoded(self.manifest,self.index_data)

    @staticmethod
    def union_layer(data,key):
        return unary_union([Polygon(p["outer"],p["holes"]) for p in data["layers"][key]])

    def test_partition_is_conservative_and_separate(self):
        r=build(self.station,self.manifest)
        self.assertEqual(r["schema"],SCHEMA)
        self.assertEqual(r["status"],"experimental")
        a=self.union_layer(r,"carriageway_candidate")
        b=self.union_layer(r,"sidewalk_candidate")
        c=self.union_layer(r,"unclassified_corridor")
        self.assertAlmostEqual(a.area,608,delta=.1)
        self.assertGreater(b.area,0)
        self.assertGreater(c.area,0)
        self.assertAlmostEqual(a.union(b).union(c).area,1600,delta=.05)
        self.assertLess(a.intersection(b).area,.01)
        self.assertLess(b.intersection(c).area,.01)
        self.assertGreater(len(r["curb_candidates"]),0)
        self.assertFalse(any("verified" in x.lower() for x in [r["geometry_quality"]]))

    def test_output_file_is_json_and_contains_provenance(self):
        output=pathlib.Path(self.tmp.name)/"result.json"
        build(self.station,self.manifest,output)
        result=json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(len(result["source"]["inputs"]),3)
        self.assertEqual(result["source"]["osm"],"© OpenStreetMap contributors / ODbL 1.0")
        self.assertEqual(result["statistics"]["osm_segments_selected"],1)

    def test_wrong_epsg_rejected(self):
        self.station_data["projected_crs"]="EPSG:4326"
        self.write()
        with self.assertRaisesRegex(ValueError,"schema or projected CRS"):
            build(self.station,self.manifest)

    def test_missing_or_nonmatching_osm_rejected(self):
        self.tile_data["edges"][0]["points"]=[[200,500],[300,500]]
        self.write()
        with self.assertRaisesRegex(ValueError,"No valid OSM"):
            build(self.station,self.manifest)

    def test_bridge_is_not_fabricated_as_ground_carriageway(self):
        self.tile_data["edges"][0]["bridge_osm_tag"]="yes"
        self.write()
        with self.assertRaisesRegex(ValueError,"No valid OSM"):
            build(self.station,self.manifest)

    def test_private_osm_road_is_excluded(self):
        self.tile_data["edges"][0]["access_osm_tag"]="private"
        self.write()
        with self.assertRaisesRegex(ValueError,"No valid OSM"):
            build(self.station,self.manifest)

    def test_tampered_tile_fails_sha256(self):
        self.tile_data["edges"][0]["width_m"]=11
        encoded(self.tile,self.tile_data)
        with self.assertRaisesRegex(ValueError,"checksum"):
            build(self.station,self.manifest)

    def test_invalid_polygon_cannot_be_silently_repaired(self):
        self.station_data["roads"][0]["polygon"]=[[-40,-10],[40,10],[-40,10],[40,-10]]
        self.write()
        with self.assertRaisesRegex(ValueError,"topology"):
            build(self.station,self.manifest)

if __name__=="__main__":
    unittest.main()
