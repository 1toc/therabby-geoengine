import test from 'node:test';
import assert from 'node:assert/strict';
import {
  tileDistance,selectCityTiles,chooseElevationReference,
  groundFromEdge,loadCityAssets,disposeCityAssets
} from '../viewer/geoengine-traffic-city.mjs';

const centerE=55500,centerN=194500;
const meta={
  tile_origin_east_m:55000,tile_origin_north_m:195000,
  byte_length:8,glb:'55_194.glb',id:'55_194'
};
const manifest=(kind,tiles=[meta])=>({
  schema:kind==='building'?'therabby.geoengine.citywide-lod1-glb.v0.1':'therabby.geoengine.citywide-terrain-glb.v0.1',
  status:kind==='building'?'complete':'complete_with_gaps',
  projected_crs:'EPSG:6677',vertical_datum:'T.P. (Tokyo Peil)',tiles
});
const roadTiles=[{
  projected_crs:'EPSG:6677',tile_origin_east_m:55000,tile_origin_north_m:195000,
  edges:[{points:[[500,500],[510,510]],ground_height_from_tp_m:70,ground_height_to_tp_m:72},
         {points:[[700,700],[710,710]],ground_height_from_tp_m:null,ground_height_to_tp_m:null}]
}];

test('selects only near GLB tiles using projected east/north bounds',()=>{
  const far={...meta,id:'55_200',tile_origin_north_m:201000};
  const selected=selectCityTiles(manifest('building',[meta,far]),'building',centerE,centerN,360);
  assert.equal(selected.length,1);assert.equal(selected[0].id,meta.id);
  assert.equal(tileDistance(meta,centerE,centerN),0);
  assert.ok(tileDistance(far,centerE,centerN)>360);
});

test('rejects unknown coordinate reference and vertical datum',()=>{
  const a=manifest('terrain');a.vertical_datum='unknown';
  assert.throws(()=>selectCityTiles(a,'terrain',centerE,centerN),/標高基準/);
  const b=manifest('building');b.projected_crs='EPSG:4326';
  assert.throws(()=>selectCityTiles(b,'building',centerE,centerN),/座標系/);
});

test('ground reference uses closest known DEM5A sample, unknown remains null',()=>{
  const ref=chooseElevationReference(roadTiles,centerE,centerN);
  assert.equal(ref.height_tp_m,70);
  assert.equal(ref.distance_m,0);
  assert.equal(groundFromEdge(roadTiles[0].edges[0],.5),71);
  assert.equal(groundFromEdge(roadTiles[0].edges[1],.5),null);
  assert.equal(chooseElevationReference(roadTiles,52000,180000),null);
});

class Group {
  constructor(){this.children=[];this.parent=null;this.position={set:(...xyz)=>{this.xyz=xyz;}};}
  add(obj){this.children.push(obj);obj.parent=this;}
  remove(obj){this.children=this.children.filter(x=>x!==obj);obj.parent=null;}
  traverse(f){f(this);for(const child of this.children)child.traverse(f);}
}
class FakeGLTFLoader{
  async parseAsync(buf){assert.equal(buf.byteLength,8);return {scene:new Group()};}
}
const mockFetch=(missing=null)=>{
  const urls=[];
  return {urls,fetcher:async(url)=>{
    const value=String(url);urls.push(value);
    if(value.includes('tileset.json')){
      const kind=value.includes('terrain-glb')?'terrain':'building';
      return {ok:true,json:async()=>manifest(kind)};
    }
    if(missing&&value.includes(missing))return {ok:false,status:404};
    return {ok:true,arrayBuffer:async()=>new ArrayBuffer(8)};
  }};
};

test('loads terrain+official buildings, preserving tile X/Z origin and T.P. offset',async()=>{
  const {urls,fetcher}=mockFetch();
  const {group,stats}=await loadCityAssets({
    THREE:{Group},GLTFLoader:FakeGLTFLoader,
    centerEast:centerE,centerNorth:centerN,referenceHeight:70,
    fetcher
  });
  assert.equal(stats.terrain,1);
  assert.equal(stats.building,1);
  assert.equal(stats.bytes,16);
  assert.equal(group.children.length,2);
  assert.deepEqual(group.children[0].xyz,[-500,-70,-500]);
  assert.deepEqual(group.children[1].xyz,[-500,-70,-500]);
  assert.equal(urls.length,4);
  disposeCityAssets(group);
});

test('rejects missing terrain GLB without reporting a successful integrated scene',async()=>{
  const {fetcher}=mockFetch('terrain-glb/55_194.glb');
  await assert.rejects(()=>loadCityAssets({
    THREE:{Group},GLTFLoader:FakeGLTFLoader,
    centerEast:centerE,centerNorth:centerN,referenceHeight:70,
    fetcher
  }),/両方を読み込めません/);
});
