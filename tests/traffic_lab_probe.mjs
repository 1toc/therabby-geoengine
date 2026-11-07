import test from 'node:test';
import assert from 'node:assert/strict';
import {buildTrafficGraph,makeSyntheticTrafficTiles} from '../viewer/geoengine-traffic-graph.mjs';

const getArcs=(graph,mode)=>[...graph.adjacency[mode].values()].flat();
const demo=()=>makeSyntheticTrafficTiles();

test('fixture is explicitly synthetic and renders connected vehicle/pedestrian edges',()=>{
  const tiles=demo(),g=buildTrafficGraph(tiles,55500,194500,280);
  assert.equal(tiles[0].data_quality,'SYNTHETIC_TEST_FIXTURE');
  assert.equal(g.segments.length,tiles[0].edges.length);
  assert.ok(getArcs(g,'vehicle').length>=8);
  assert.ok(getArcs(g,'pedestrian').length>=5);
  assert.ok(getArcs(g,'pedestrian').every(a=>a.highway==='footway'));
  assert.equal(g.legal_drivability,null);
  assert.equal(g.collision_ready,false);
  assert.equal(g.road_deck_height_m,null);
});

test('EPSG:6677 north is converted to local Z south without guessing elevation',()=>{
  const g=buildTrafficGraph(demo(),55500,194500);
  const north=g.segments.find(s=>s.id==='demo-n');
  assert.deepEqual(north.a,[0,-170]);
  assert.deepEqual(north.b,[0,0]);
  assert.equal(g.crs,'EPSG:6677');
});

test('forward one-way only adds forward travel arc',()=>{
  const tiles=demo();tiles[0].edges[0].oneway_osm_tag='yes';
  const arcs=getArcs(buildTrafficGraph(tiles,55500,194500),'vehicle').filter(a=>a.edgeId==='demo-w');
  assert.equal(arcs.length,1);
  assert.equal(arcs[0].from,'demo:-200:0');
  assert.equal(arcs[0].to,'demo:0:0');
});

test('reverse one-way only adds reverse travel arc',()=>{
  const tiles=demo();tiles[0].edges[0].oneway_osm_tag='-1';
  const arcs=getArcs(buildTrafficGraph(tiles,55500,194500),'vehicle').filter(a=>a.edgeId==='demo-w');
  assert.equal(arcs.length,1);
  assert.equal(arcs[0].from,'demo:0:0');
  assert.equal(arcs[0].to,'demo:-200:0');
});

test('OSM footways do not become vehicle routes, and prohibited roads do not get traffic',()=>{
  const tiles=demo();
  const edge=tiles[0].edges[0];
  edge.access_osm_tag='private';
  const other=tiles[0].edges[1];other.bridge_osm_tag='yes';
  const g=buildTrafficGraph(tiles,55500,194500);
  const vehicles=getArcs(g,'vehicle');
  assert.ok(!vehicles.some(a=>a.edgeId===edge.id||a.edgeId===other.id));
  assert.ok(vehicles.every(a=>a.highway!=='footway'));
  assert.ok(g.segments.some(s=>s.id===edge.id)); // display remains a map, not a legal routing conclusion
});

test('duplicate IDs are not duplicated and malformed tile CRS is rejected',()=>{
  const tiles=demo();tiles[0].edges.push({...tiles[0].edges[0]});
  const g=buildTrafficGraph(tiles,55500,194500);
  assert.equal(g.counts.duplicate,1);
  tiles[0].projected_crs='EPSG:4326';
  assert.throws(()=>buildTrafficGraph(tiles,55500,194500),/EPSG:6677/);
});

test('distant segments are excluded from the preview',()=>{
  const tiles=demo(),g=buildTrafficGraph(tiles,55500,194500,25);
  assert.ok(g.segments.length<tiles[0].edges.length);
});

test('shared OSM node IDs link arcs from different tiles',()=>{
  const tiles=demo();
  // Second synthetic tile joins the first road at the same absolute projected point.
  tiles.push({schema:'therabby.geoengine.citywide-road-tile.v0.1',tile_id:'synthetic-2',
    projected_crs:'EPSG:6677',tile_origin_east_m:55000,tile_origin_north_m:195000,
    edges:[{id:'joined',from_node:'demo:200:0',to_node:'demo:260:0',
      points:[[700,500],[760,500]],width_m:6,width_quality:'synthetic-estimate',
      highway:'residential',oneway_osm_tag:'yes'}]});
  const g=buildTrafficGraph(tiles,55500,194500,300);
  assert.ok(g.adjacency.vehicle.get('demo:200:0').some(a=>a.edgeId==='joined'));
});
