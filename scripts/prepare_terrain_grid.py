#!/usr/bin/env python3
"""Build the source-checked local 5m ground terrain grid."""
import argparse
from geoengine import load_area, write_json
from terrain_grid import build_grid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--area',default='config/fukushima_station_east_1km.json')
    parser.add_argument('--source-dir',default='data/raw/gsi_dem5a_1km')
    parser.add_argument('--output',default='dist/real/fukushima-east-1km/terrain_grid_5m.json')
    args=parser.parse_args()
    grid=build_grid(load_area(args.area),args.source_dir)
    write_json(args.output,grid)
    print('GSI DEM5A:',len(grid['heights_relative_m']),'x',
          len(grid['heights_relative_m'][0]),'origin T.P.',grid['height_origin_tp_m'],
          'relative range',grid['min_relative_m'],grid['max_relative_m'])


if __name__=='__main__':main()
