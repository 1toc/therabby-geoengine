import test from 'node:test';
import assert from 'node:assert/strict';
import {isDriveEdge, closestDriveRoad, advanceVehicle} from '../viewer/geoengine-pixel-explorer-core.mjs';

const edge = {highway:'residential', bridge_osm_tag:'no', tunnel_osm_tag:null,
  ground_height_from_tp_m:80, ground_height_to_tp_m:82, width_m:6, points:[[0,0],[100,0]]};
const map = new Map([['road:one',{roadTile:{tile_origin_east_m:55000,
  tile_origin_north_m:195000,edges:[edge]}}]]);
const origin = {east:55000,north:195000};

test('drivable road selection excludes pedestrian paths, tunnels and missing height',()=>{
  assert.equal(isDriveEdge(edge),true);
  assert.equal(isDriveEdge({...edge,highway:'footway'}),false);
  assert.equal(isDriveEdge({...edge,bridge_osm_tag:'yes'}),false);
  assert.equal(isDriveEdge({...edge,ground_height_to_tp_m:null}),false);
});
test('closest road uses projected coordinates and interpolates altitude',()=>{
  const hit=closestDriveRoad(map,origin,50,3,20);
  assert.equal(hit.x,50);assert.equal(hit.z,0);
  assert.equal(hit.y,81);assert.equal(hit.distance,3);
  assert.equal(closestDriveRoad(map,origin,50,50,20),null);
});
test('vehicle accelerates, steers and has no acceleration without input',()=>{
  const start={x:0,z:0,y:80,speed:0,yaw:0};
  let s=start;for(let i=0;i<20;i++)s=advanceVehicle(s,new Set(['w']),0.05);
  assert.ok(s.speed>4&&s.z<0);
  s=advanceVehicle(s,new Set(['w','a']),0.05);assert.ok(s.yaw>0);
  const prior=s.speed;s=advanceVehicle(s,new Set(),0.05);assert.ok(s.speed<prior);
});
