"""STEP 1-1 geometry regression tests (no external HTTP required)."""
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest
import shapefile
from shapely.geometry import shape
from pyproj import Geod

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_boundary import extract_boundary


def make_sample_zip(tmp_path, include_fukushima=True):
    """Build fake *fixture* municipalities in a real shapefile container."""
    prefix=str(tmp_path/'N03-sample_07')
    with shapefile.Writer(prefix,shapeType=shapefile.POLYGON,encoding='utf-8') as writer:
        writer.field('N03_001','C',size=80)
        writer.field('N03_004','C',size=80)
        writer.field('N03_007','C',size=8)
        if include_fukushima:
            # Area ~763 km2, synthetic only for conversion testing.
            writer.poly([[[140.20,37.62],[140.20,37.88],[140.50,37.88],[140.50,37.62],[140.20,37.62]]])
            writer.record('福島県','福島市','07201')
        writer.poly([[[140.60,37.62],[140.60,37.63],[140.61,37.63],[140.61,37.62],[140.60,37.62]]])
        writer.record('福島県','別の市','07299')
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as zf:
        for ext in ('shp','shx','dbf'):
            p=Path(prefix+'.'+ext)
            zf.write(p,arcname=p.name)
    return bio.getvalue()


def test_boundary_geometry_has_realistic_city_scope_and_declared_provenance():
    gj=json.loads((ROOT/'data'/'fukushima_city_boundary.geojson').read_text(encoding='utf-8'))
    meta=json.loads((ROOT/'data'/'boundary_metadata.json').read_text(encoding='utf-8'))
    geom=shape(gj['features'][0]['geometry'])
    assert geom.is_valid and geom.geom_type in {'Polygon','MultiPolygon'}
    assert meta['status'] in {'preview','official_2026'}
    if meta['status']=='official_2026':
        assert meta['source']=='国土交通省 国土数値情報（行政区域データ）2026年版'
        assert meta['source_sha256']
    else:
        assert meta['source_date'] is None
    area,_=Geod(ellps='GRS80').geometry_area_perimeter(geom)
    assert 700 < abs(area)/1e6 < 850
    assert gj['features'][0]['properties']['municipality_code']=='07201'


def test_extract_filters_municipality_code_and_calculates_area(tmp_path):
    boundary,meta=extract_boundary(make_sample_zip(tmp_path),simplify_meters=0)
    assert meta['status']=='official_2026'
    assert meta['source_date']=='2026-01-01'
    assert meta['component_count']==1
    assert boundary['features'][0]['properties']['municipality_code']=='07201'
    assert 700<meta['area_km2_geodesic']<850
    b=meta['bbox'];assert b[0]==pytest.approx(140.20,abs=1e-5) and b[2]==pytest.approx(140.50,abs=1e-5)


def test_extract_rejects_zip_without_target(tmp_path):
    with pytest.raises(ValueError,match='07201'):
        extract_boundary(make_sample_zip(tmp_path,include_fukushima=False))
