import test from 'node:test';
import assert from 'node:assert/strict';
import {ROAD_PAINT_SCHEMA,eligiblePaintEdge,estimateLineStyle,buildEstimatedRoadPaint}
  from '../viewer/geoengine-procedural-rules.mjs';

const road=(overrides={})=>({
  points:[[10,10],[110,10]],
  width_m:8,
  highway:'secondary',
  oneway_osm_tag:'no',
  bridge_osm_tag:'no',
  tunnel_osm_tag:'no',
  ground_height_from_tp_m:80,
  ground_height_to_tp_m:84,
  ...overrides,
});
test('ordinary two-way road gives only estimated center and edge markings',()=>{
  const data=buildEstimatedRoadPaint([road()]);
  assert.equal(data.schema,ROAD_PAINT_SCHEMA);
  assert.ok(data.yellow.length>0);
  assert.ok(data.white.length>0);
  assert.equal(data.yellow.length%18,0);
  assert.equal(data.white.length%18,0);
  assert.equal(data.diagnostics.collisionReady,false);
  assert.equal(data.diagnostics.legalAccessVerified,false);
});
test('one-way road does not receive an inferred yellow centre line',()=>{
  const data=buildEstimatedRoadPaint([road({oneway_osm_tag:'yes'})]);
  assert.equal(data.yellow.length,0);
  assert.ok(data.white.length>0);
});
test('narrow and pedestrian ways do not receive fabricated lanes',()=>{
  const data=buildEstimatedRoadPaint([
    road({width_m:3}),road({highway:'footway'}),road({highway:'steps'}),
    road({road_class:'walk'}),
  ]);
  assert.equal(data.diagnostics.quads,0);
});
test('bridge and tunnel are excluded without verified road-deck geometry',()=>{
  const data=buildEstimatedRoadPaint([
    road({bridge_osm_tag:'yes'}),road({tunnel_osm_tag:'yes'}),
  ]);
  assert.equal(data.diagnostics.quads,0);
});
test('missing or unsupported ground height prevents painting',()=>{
  for(const value of [null,undefined,NaN,Infinity]){
    assert.equal(eligiblePaintEdge(road({ground_height_from_tp_m:value})),false);
  }
});
test('invalid points are never emitted',()=>{
  assert.equal(eligiblePaintEdge(road({points:[[0,0],[NaN,1]]})),false);
  assert.equal(eligiblePaintEdge(road({points:[[0,0],[0,0]]})),false);
});
test('sampled heights are used with a consistent render offset',()=>{
  const data=buildEstimatedRoadPaint([road()],(_,linear)=>linear+5);
  const ys=[...data.yellow,...data.white].filter((_,i)=>i%3===1);
  assert.ok(ys.length>0);
  assert.ok(ys.every(y=>y>=85.205-1e-5&&y<=89.205+1e-5));
});
test('tile vertex budget is obeyed',()=>{
  const data=buildEstimatedRoadPaint(Array.from({length:50},()=>road()),undefined,{maxQuads:17});
  assert.ok(data.diagnostics.quads<=17);
  assert.ok((data.yellow.length+data.white.length)/18<=17);
});
test('no budget and zero streets remain valid',()=>{
  assert.equal(buildEstimatedRoadPaint([]).diagnostics.quads,0);
  assert.equal(buildEstimatedRoadPaint([road()],undefined,{maxQuads:0}).diagnostics.quads,0);
});
test('line quality flags and estimated width are explicit',()=>{
  const s=estimateLineStyle(road());
  assert.equal(s.confidence,'estimated-visual-only');
  assert.equal(s.width,8);
  assert.equal(s.center,true);
});
test('input coordinates are not modified',()=>{
  const edge=road();
  const before=JSON.stringify(edge);
  buildEstimatedRoadPaint([edge]);
  assert.equal(JSON.stringify(edge),before);
});
test('bad parameters fail clearly',()=>{
  assert.throws(()=>buildEstimatedRoadPaint(null),/edges/);
  assert.throws(()=>buildEstimatedRoadPaint([road()],null),/sampleHeight/);
  assert.throws(()=>buildEstimatedRoadPaint([road()],undefined,{maxQuads:-1}),/maxQuads/);
});
