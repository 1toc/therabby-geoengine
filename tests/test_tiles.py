import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from tile_math import tile_bounds, clip_segment_rect, clip_roads


class TestTiles(unittest.TestCase):
    def test_four_tiles_cover_square_without_overlap_interior(self):
        tiles = list(tile_bounds(100,100))
        self.assertEqual([t['bounds'] for t in tiles],
                         [[-100,-100,0,0],[0,-100,100,0],
                          [-100,0,0,100],[0,0,100,100]])

    def test_road_seam_id_and_coordinate_match(self):
        road = {'id':'synthetic-road', 'points':[[-75,-25],[75,25]], 'width_m':6}
        pieces = [clip_roads([road],t['bounds']) for t in tile_bounds(100,100)]
        self.assertEqual(sum(len(p) for p in pieces), 2)
        endpoints = [(p[0]['points'][-1],p[0]['endpoint_nodes'][-1]) for p in pieces if p and p[0]['points'][-1][0]==0]
        endpoints += [(p[0]['points'][0],p[0]['endpoint_nodes'][0]) for p in pieces if p and p[0]['points'][0][0]==0]
        self.assertEqual(endpoints, [([0,0],'seam:0:0'),([0,0],'seam:0:0')])

    def test_clipped_segment_has_exact_shared_boundary(self):
        left = clip_segment_rect([-40,15],[40,15],[-100,0,0,100])
        right = clip_segment_rect([-40,15],[40,15],[0,0,100,100])
        self.assertEqual(left[1],[0,15])
        self.assertEqual(right[0],[0,15])


if __name__ == '__main__':
    unittest.main()
