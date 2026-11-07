"""GSI DEM5A ground-height sampling with an explicit T.P. vertical datum."""
import hashlib
import math
from pathlib import Path

from geoengine import read_json


def world_pixel(lat,lon,zoom):
    scale=(2**zoom)*256
    return ((lon+180)/360*scale,
            (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*scale)


def decode_dem5a(rgb):
    encoded=(rgb[0]<<16)+(rgb[1]<<8)+rgb[2]
    if encoded==1<<23:return None
    return (encoded if encoded<1<<23 else encoded-(1<<24))*.01


def load_source(source_dir,area_id):
    from PIL import Image
    root=Path(source_dir)
    manifest=read_json(root/'source_manifest.json')
    if manifest['schema']!='therabby.geoengine.source.gsi-dem5a.v0.1' or manifest['area_id']!=area_id or \
            manifest['vertical_datum']!='T.P. (Tokyo Peil), ground terrain elevation':
        raise ValueError('Unsupported/mismatched GSI DEM5A source or vertical datum')
    tiles={}
    for entry in manifest['tiles']:
        path=root/entry['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError(f'GSI DEM5A hash mismatch: {path}')
        image=Image.open(path).convert('RGB')
        if image.size!=(256,256):raise ValueError(f'GSI DEM5A tile dimensions: {path}')
        tiles[(entry['x'],entry['y'])]=image
    return manifest,tiles


def sample_dem(tiles,lat,lon,zoom=15):
    px,py=world_pixel(lat,lon,zoom)
    x0,y0=math.floor(px-.5),math.floor(py-.5)
    tx,tz=px-.5-x0,py-.5-y0
    values=[]
    for y in (y0,y0+1):
        for x in (x0,x0+1):
            image=tiles.get((x//256,y//256))
            if image is None:raise ValueError(f'Missing GSI DEM5A tile at {x//256},{y//256}')
            value=decode_dem5a(image.getpixel((x%256,y%256)))
            if value is None:raise ValueError(f'Missing GSI DEM5A elevation at {lat},{lon}')
            values.append(value)
    return ((values[0]*(1-tx)+values[1]*tx)*(1-tz)+
            (values[2]*(1-tx)+values[3]*tx)*tz)


def build_grid(area,source_dir,step_m=5):
    from prepare_wide_tiles import inverse_project
    if area.get('projection')!='JGD2011_JPRCS_IX_GRS80':
        raise ValueError('DEM grid requires JGD2011_JPRCS_IX_GRS80')
    half=area['half_size_m']
    if (2*half)%step_m or half%step_m:
        raise ValueError('DEM grid step must divide 1km and center')
    manifest,tiles=load_source(source_dir,area['id'])
    count=int(2*half/step_m)+1
    absolute=[]
    for row in range(count):
        z=-half+row*step_m
        values=[]
        for col in range(count):
            x=-half+col*step_m
            lat,lon=inverse_project(x,z,area)
            values.append(sample_dem(tiles,lat,lon))
        absolute.append(values)
    origin=absolute[count//2][count//2]
    relative=[[round(value-origin,3) for value in row] for row in absolute]
    flat=[value for row in relative for value in row]
    return {'schema':'therabby.geoengine.terrain-grid.v0.1','area_id':area['id'],
        'bounds':[-half,-half,half,half],'step_m':step_m,
        'height_origin_tp_m':round(origin,3),
        'heights_relative_m':relative,'min_relative_m':min(flat),'max_relative_m':max(flat),
        'vertical_datum':'T.P. (Tokyo Peil); local Y = T.P. elevation minus height_origin_tp_m',
        'horizontal_quality':'JGD2011 project coordinates sampled from Web Mercator GSI tiles; alignment not surveyed',
        'height_quality':'GSI DEM5A interpolated ground terrain; bridge/deck/road surface unknown',
        'source_manifest_sha256':hashlib.sha256((Path(source_dir)/'source_manifest.json').read_bytes()).hexdigest(),
        'source':'GSI DEM5A PNG z15','attribution':'Geospatial Information Authority of Japan'}


def height_at(grid,x,z):
    x0,z0,x1,z1=grid['bounds']
    if not x0-1e-6<=x<=x1+1e-6 or not z0-1e-6<=z<=z1+1e-6:
        raise ValueError(f'Terrain point outside grid: {x},{z}')
    step=grid['step_m'];u=(max(x0,min(x1,x))-x0)/step
    v=(max(z0,min(z1,z))-z0)/step
    ix=min(math.floor(u),len(grid['heights_relative_m'][0])-2)
    iz=min(math.floor(v),len(grid['heights_relative_m'])-2)
    fx,fz=u-ix,v-iz
    heights=grid['heights_relative_m']
    return ((heights[iz][ix]*(1-fx)+heights[iz][ix+1]*fx)*(1-fz)+
            (heights[iz+1][ix]*(1-fx)+heights[iz+1][ix+1]*fx)*fz)
