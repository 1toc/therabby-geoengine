"""Road geometry fixture tests. All invented ways are ONLY used in tests."""
import json
import hashlib
from pathlib import Path
import sys
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from shapely.geometry import shape

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_roads import Collector, read_boundary, process_overpass_data, tile_key, get_station_data, main, inspect_pbf_source


def sample():
    return {
      'elements':[
        {'type':'way','id':1001,'tags':{'highway':'primary','name':'TEST arterial','maxspeed':'50','oneway':'yes'},'geometry':[
          {'lon':140.455,'lat':37.755},{'lon':140.465,'lat':37.755}]},
        {'type':'way','id':1002,'tags':{'highway':'footway','name':'TEST footpath'},'geometry':[
          {'lon':140.460,'lat':37.753},{'lon':140.461,'lat':37.757}]},
        {'type':'way','id':1003,'tags':{'highway':'proposed','name':'NOT-ACTUAL-ROAD'},'geometry':[
          {'lon':140.455,'lat':37.755},{'lon':140.465,'lat':37.755}]},
        {'type':'node','id':999,'tags':{'highway':'primary'},'lat':37.755,'lon':140.459},
      ]}


def test_default_boundary_quality_matches_declared_source():
    boundary,path,quality=read_boundary()
    meta=json.loads((ROOT/'data'/'boundary_metadata.json').read_text(encoding='utf-8'))
    assert quality==meta['status']
    assert quality in {'preview','official_2026'}
    assert 139<boundary.bounds[0]<142
    assert boundary.contains(shape({'type':'Point','coordinates':[140.459,37.755]}))


def test_road_extract_preserves_tags_and_clips(tmp_path):
    boundary,_,quality=read_boundary()
    collector=Collector(boundary)
    process_overpass_data(sample(),collector)
    assert collector.kept_ways==2
    assert collector.total_ways==3
    assert collector.way_types['primary']==1
    assert collector.way_types['footway']==1
    index=collector.write(tmp_path/'roads','overpass_station','TEST FIXTURE','fukushima_city_boundary.geojson',quality)
    assert index['way_count']==2
    assert index['boundary_quality']==quality
    assert index['coverage']=='station_test_area'
    assert index['license']=='ODbL 1.0'
    feats=[]
    for t in index['tiles']:
        path=tmp_path/'roads'/t['file']
        data=json.loads(path.read_text(encoding='utf-8'))
        assert data['type']=='FeatureCollection'
        for feat in data['features']:
            geom=shape(feat['geometry'])
            assert boundary.buffer(1e-8).covers(geom)
            assert feat['properties']['road_class'] in {'major','walk'}
            feats.append(feat)
    assert any(f['properties']['name']=='TEST arterial' for f in feats)
    assert any(f['properties']['name']=='TEST footpath' for f in feats)
    assert not any(f['properties']['name']=='NOT-ACTUAL-ROAD' for f in feats)


def test_outside_and_boundary_crossing(tmp_path):
    boundary,_,_=read_boundary()
    c=Collector(boundary)
    c.add_way(1,{'highway':'residential'},[(140.35,37.79),(140.455,37.755)])
    c.add_way(2,{'highway':'residential'},[(141.5,37.755),(141.6,37.755)])
    assert c.kept_ways==1
    assert c.total_ways==2
    for features in c.grid.values():
        for feat in features: assert boundary.buffer(1e-8).covers(shape(feat['geometry']))


def test_empty_collector_does_not_invent_roads(tmp_path):
    boundary,_,quality=read_boundary()
    obj=Collector(boundary).write(tmp_path/'roads','osm_api_json','source URL fixture','boundary.geojson',quality)
    assert obj['status']=='empty'
    assert obj['way_count']==0
    assert obj['tiles']==[]


def test_invalid_overpass_rejected():
    b,_,_=read_boundary()
    with pytest.raises(ValueError,match='elements'):
        process_overpass_data({},Collector(b))


def test_tile_edges_deterministic():
    assert tile_key(140.459,37.755)==tile_key(140.459,37.755)
    assert tile_key(140.475,37.75)==tile_key(140.475,37.75)


def test_overpass_http_error_is_reported_as_external_api_failure():
    error=urllib.error.HTTPError('https://example.invalid',429,'Too Many Requests',{},None)
    with patch('build_roads.urllib.request.urlopen',side_effect=error):
        with pytest.raises(RuntimeError,match='外部APIエラー: Overpass HTTP 429'):
            get_station_data()


def test_overpass_network_error_is_distinguished_from_api_response():
    with patch('build_roads.urllib.request.urlopen',side_effect=urllib.error.URLError('offline')):
        with pytest.raises(RuntimeError,match='外部通信エラー: Overpassへ接続できません'):
            get_station_data()


def test_failed_empty_import_preserves_existing_road_output(tmp_path):
    output=tmp_path/'roads'
    output.mkdir()
    sentinel=output/'index.json'
    sentinel.write_text('{"status":"existing"}',encoding='utf-8')
    with patch('build_roads.get_station_data',return_value={'elements':[]}):
        assert main(['--overpass-station','--out',str(output)])==1
    assert sentinel.read_text(encoding='utf-8')=='{"status":"existing"}'


def test_successful_import_publishes_immutable_tile_generation(tmp_path):
    output=tmp_path/'roads'
    with patch('build_roads.get_station_data',return_value=sample()):
        assert main(['--overpass-station','--out',str(output)])==0
    index=json.loads((output/'index.json').read_text(encoding='utf-8'))
    assert index['status']=='ready'
    assert index['coverage']=='station_test_area'
    assert all(tile['file'].startswith('tiles-') for tile in index['tiles'])
    assert all((output/tile['file']).is_file() for tile in index['tiles'])


def test_index_replace_failure_keeps_previous_manifest(tmp_path):
    output=tmp_path/'roads'
    output.mkdir()
    sentinel=output/'index.json'
    sentinel.write_text('{"status":"existing"}',encoding='utf-8')
    with patch('build_roads.get_station_data',return_value=sample()), patch('build_roads.os.replace',side_effect=PermissionError('locked index')):
        assert main(['--overpass-station','--out',str(output)])==1
    assert sentinel.read_text(encoding='utf-8')=='{"status":"existing"}'


def test_local_osm_json_is_not_mislabeled_as_citywide(tmp_path):
    boundary,_,quality=read_boundary()
    index=Collector(boundary).write(tmp_path/'roads', 'osm_api_json', 'source URL fixture', 'boundary.geojson', quality)
    assert index['coverage']=='local_json_import'
    assert index['source_acquired_utc'] is None
    assert index['generated_utc']


def test_pbf_source_metadata_records_hash_and_snapshot_not_mtime_as_snapshot(tmp_path):
    source=tmp_path/'synthetic_pbf_metadata_fixture.pbf'
    source.write_bytes(b'SYNTHETIC_TEST_FIXTURE')

    class Header:
        def get(self,key):
            return '2026-10-29T21:21:26Z' if key=='osmosis_replication_timestamp' else None
    class Reader:
        def __init__(self,path): self.path=path
        def header(self): return Header()
        def close(self): pass

    fake_osmium=SimpleNamespace(io=SimpleNamespace(Reader=Reader))
    with patch.dict(sys.modules,{'osmium':fake_osmium}):
        meta=inspect_pbf_source(source)
    assert meta['snapshot_timestamp_utc']=='2026-10-29T21:21:26Z'
    assert meta['file_mtime_utc']
    assert meta['sha256']==hashlib.sha256(b'SYNTHETIC_TEST_FIXTURE').hexdigest()
