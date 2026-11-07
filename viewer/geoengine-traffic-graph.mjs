/**
 * Experimental 2D movement graph over GeoEngine's existing citywide road tiles.
 * Coordinate contract: EPSG:6677 east/north -> local X east, Z south (metres).
 * This is NOT a survey, lane graph, vehicle physics or legal route evaluator.
 */
const VEHICLE_EXCLUDE = new Set(['footway','pedestrian','path','cycleway','steps','bridleway','track','construction','proposed','platform']);
const PEDESTRIAN_TYPES = new Set(['footway','pedestrian','path']);
const CLOSED_ACCESS = new Set(['no','private']);
const ONEWAY_FORWARD = new Set(['yes','true','1']);
const ONEWAY_REVERSE = new Set(['-1','reverse']);

export function buildTrafficGraph(tiles, centerEast, centerNorth, radiusM=300) {
  if (!Number.isFinite(centerEast)||!Number.isFinite(centerNorth)||
      !Number.isFinite(radiusM)||radiusM<=0||radiusM>2000) throw new RangeError('探索中心・半径が不正です');
  if (!Array.isArray(tiles)) throw new TypeError('タイルは配列で渡してください');
  const segments=[], adjacency={vehicle:new Map(),pedestrian:new Map()}, seen=new Set();
  const counts={bad:0,far:0,duplicate:0,estimated_width:0};
  function addArc(mode,from,to,a,b,edge,length,groundFromTp=null,groundToTp=null) {
    const map=adjacency[mode];
    if (!map.has(from))map.set(from,[]);
    map.get(from).push({mode,from,to,a,b,length,edgeId:edge.id,highway:edge.highway,groundFromTp,groundToTp});
  }
  for (const tile of tiles) {
    if (!tile || tile.schema!=='therabby.geoengine.citywide-road-tile.v0.1'||
        tile.projected_crs!=='EPSG:6677'||!Number.isFinite(tile.tile_origin_east_m)||
        !Number.isFinite(tile.tile_origin_north_m)||!Array.isArray(tile.edges)) {
      throw new Error('未対応または破損したEPSG:6677道路タイルです');
    }
    for (const edge of tile.edges) {
      if (!edge||typeof edge.id!=='string'||typeof edge.from_node!=='string'||
          typeof edge.to_node!=='string'||!Array.isArray(edge.points)||
          edge.points.length!==2||edge.points.some(p=>!Array.isArray(p)||p.length!==2||
            !p.every(Number.isFinite))) {counts.bad++;continue;}
      if(seen.has(edge.id)){counts.duplicate++;continue;}
      seen.add(edge.id);
      const a=[tile.tile_origin_east_m+edge.points[0][0]-centerEast,
               centerNorth-tile.tile_origin_north_m+edge.points[0][1]];
      const b=[tile.tile_origin_east_m+edge.points[1][0]-centerEast,
               centerNorth-tile.tile_origin_north_m+edge.points[1][1]];
      const dx=b[0]-a[0],dz=b[1]-a[1],len=Math.hypot(dx,dz);
      if(len<0.1||len>3000){counts.bad++;continue;}
      const t=Math.max(0,Math.min(1,-(a[0]*dx+a[1]*dz)/(len*len)));
      if(Math.hypot(a[0]+dx*t,a[1]+dz*t)>radiusM){counts.far++;continue;}
      const highway=String(edge.highway||'').toLowerCase();
      const pedestrian=PEDESTRIAN_TYPES.has(highway);
      const access=String(edge.access_osm_tag||'').toLowerCase();
      const closed=CLOSED_ACCESS.has(access);
      const gradeSeparated=!!(edge.bridge_osm_tag && !['no','false','0'].includes(String(edge.bridge_osm_tag).toLowerCase()))||
        !!(edge.tunnel_osm_tag && !['no','false','0'].includes(String(edge.tunnel_osm_tag).toLowerCase()));
      const vehicle=!VEHICLE_EXCLUDE.has(highway)&&!!highway&&!closed&&!gradeSeparated&&
        !['motorway','motorway_link','trunk','trunk_link'].includes(highway);
      const canWalk=pedestrian&&!closed&&!gradeSeparated;
      const rawWidth=Number(edge.width_m);
      const width=Number.isFinite(rawWidth)?Math.max(1.5,Math.min(rawWidth,18)):(pedestrian?2.2:5);
      if(edge.width_quality!=='surveyed')counts.estimated_width++;
      const segment={id:edge.id,from:edge.from_node,to:edge.to_node,a,b,length:len,width_m:width,
        highway,kind:pedestrian?'footpath':VEHICLE_EXCLUDE.has(highway)?'other':'road',
        simulated_vehicle:vehicle,simulated_pedestrian:canWalk,
        width_quality:edge.width_quality||'unknown',source_way_id:edge.source_way_id||null,
        groundFromTp:Number.isFinite(edge.ground_height_from_tp_m)?edge.ground_height_from_tp_m:null,
        groundToTp:Number.isFinite(edge.ground_height_to_tp_m)?edge.ground_height_to_tp_m:null};
      segments.push(segment);
      if(vehicle) {
        const ow=String(edge.oneway_osm_tag||'').toLowerCase();
        if(!ONEWAY_REVERSE.has(ow))addArc('vehicle',edge.from_node,edge.to_node,a,b,edge,len,segment.groundFromTp,segment.groundToTp);
        if(!ONEWAY_FORWARD.has(ow))addArc('vehicle',edge.to_node,edge.from_node,b,a,edge,len,segment.groundToTp,segment.groundFromTp);
      }
      if(canWalk){
        addArc('pedestrian',edge.from_node,edge.to_node,a,b,edge,len,segment.groundFromTp,segment.groundToTp);
        addArc('pedestrian',edge.to_node,edge.from_node,b,a,edge,len,segment.groundToTp,segment.groundFromTp);
      }
    }
  }
  return {segments,adjacency,counts,crs:'EPSG:6677',centerEast,centerNorth,
    legal_drivability:null,collision_ready:false,road_deck_height_m:null,
    quality:'OSM中心線＋推定幅の2D概略。高さ・車線・信号・通行可否は未検証'};
}

/** Visibly fictional fixture. Never label this as Fukushima data. */
export function makeSyntheticTrafficTiles() {
  const edges=[];const point=(x,z)=>[x+500,z+500];
  function add(kind,a,b,id,oneway=''){
    edges.push({id:'demo-'+id,from_node:'demo:'+a.join(':'),
      to_node:'demo:'+b.join(':'),points:[point(...a),point(...b)],
      highway:kind,oneway_osm_tag:oneway,width_m:kind==='footway'?2.2:7,
      width_quality:'synthetic-estimate',access_osm_tag:'',bridge_osm_tag:'',tunnel_osm_tag:'',
      source_way_id:'SYNTHETIC_TEST_FIXTURE',legal_drivability:null});
  }
  add('residential',[-200,0],[0,0],'w'); add('residential',[0,0],[200,0],'e');
  add('residential',[0,-170],[0,0],'n');add('residential',[0,0],[0,170],'s');
  add('residential',[-130,-100],[0,-100],'nw');add('residential',[0,-100],[130,-100],'ne');
  add('residential',[0,-100],[0,-0.01],'n2');
  add('footway',[-160,-13],[0,-13],'ped-west');add('footway',[0,-13],[160,-13],'ped-east');
  add('footway',[14,-150],[14,0],'ped-north');add('footway',[14,0],[14,150],'ped-south');
  add('footway',[0,-13],[14,-13],'ped-cross');
  return [{schema:'therabby.geoengine.citywide-road-tile.v0.1',tile_id:'synthetic-demo',
    projected_crs:'EPSG:6677',tile_origin_east_m:55000,tile_origin_north_m:195000,
    data_quality:'SYNTHETIC_TEST_FIXTURE',edges}];
}
