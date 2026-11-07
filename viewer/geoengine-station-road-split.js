/**
 * GeoEngine station-east 100m: visual carriageway/sidewalk/curb hypotheses.
 *
 * The PLATEAU road extent does not encode actual sidewalks or carriageways.
 * Never consume these meshes for collision, accessibility or traffic rules.
 */
import * as THREE from 'three';
import {stationGround} from './geoengine-station-roads-v02.js';

const SCHEMA='therabby.geoengine.station-road-split.visual.v0.1';
const BOUNDS='[-50,-50,50,50]';
const MATERIALS={
  carriageway_candidate:{color:0x55595b,roughness:.97},
  sidewalk_candidate:{color:0xa8aba1,roughness:1},
  unclassified_corridor:{color:0x9a9c8b,roughness:1},
};

function assertPoint(point){
  return Array.isArray(point)&&point.length===2&&point.every(Number.isFinite)&&
    Math.abs(point[0])<=50.01&&Math.abs(point[1])<=50.01;
}
function signedArea(points){
  let area=0;
  for(let i=0;i<points.length;i++){
    const a=points[i],b=points[(i+1)%points.length];
    area+=a[0]*b[1]-b[0]*a[1];
  }
  return area/2;
}
export function validateRoadSplit(data,station){
  if(data?.schema!==SCHEMA||data.status!=='experimental'||data.projected_crs!=='EPSG:6677'||
     JSON.stringify(data.bounds_local_xz_m)!==BOUNDS||
     !Number.isFinite(data.center_east_m)||!Number.isFinite(data.center_north_m)||
     data.center_east_m!==station.center_east_m||data.center_north_m!==station.center_north_m||
     !data.source?.plateau||!data.source?.osm||!data.source?.gsi){
    throw new Error('Road split source/schema/CRS/station center mismatch');
  }
  if(!data.layers||!Array.isArray(data.curb_candidates)||data.curb_candidates.length>30000)
    throw new Error('Invalid road split layers or curb array');
  let polygonCount=0,totalVertices=0;
  for(const kind of Object.keys(MATERIALS)){
    const items=data.layers[kind];
    if(!Array.isArray(items))throw new Error('Missing road split layer: '+kind);
    for(const poly of items){
      polygonCount++;
      if(!Array.isArray(poly.outer)||poly.outer.length<3||
         !Array.isArray(poly.holes)||!poly.outer.every(assertPoint)||
         Math.abs(signedArea(poly.outer))<0.0005){
        throw new Error('Invalid road split polygon');
      }
      totalVertices+=poly.outer.length;
      for(const hole of poly.holes){
        if(!Array.isArray(hole)||hole.length<3||!hole.every(assertPoint)||
           Math.abs(signedArea(hole))<0.0005)throw new Error('Invalid road split hole');
        totalVertices+=hole.length;
      }
    }
  }
  if(polygonCount>20000||totalVertices>250000)
    throw new Error('Road split exceeds geometry budget');
  for(const line of data.curb_candidates){
    if(!Array.isArray(line)||line.length<2||!line.every(assertPoint))
      throw new Error('Invalid candidate curb line');
    totalVertices+=line.length;
    if(totalVertices>300000)throw new Error('Road split exceeds curb budget');
  }
  const stats=data.statistics;
  if(!stats||!Number.isFinite(stats.partition_error_m2)||!Number.isFinite(stats.overlap_error_m2)||
     stats.partition_error_m2>0.01||stats.overlap_error_m2>0.01)
    throw new Error('Road split geometric conservation failed');
  return data;
}

function addTriangle(buffer,data,tri,heightOffset,maxEdge=4){
  const pending=[tri];
  while(pending.length){
    const t=pending.pop();
    const lengths=[Math.hypot(t[0][0]-t[1][0],t[0][1]-t[1][1]),
                   Math.hypot(t[1][0]-t[2][0],t[1][1]-t[2][1]),
                   Math.hypot(t[2][0]-t[0][0],t[2][1]-t[0][1])];
    const at=lengths.indexOf(Math.max(...lengths));
    if(lengths[at]>maxEdge){
      const a=t[at],b=t[(at+1)%3],c=t[(at+2)%3];
      const mid=[(a[0]+b[0])/2,(a[1]+b[1])/2];
      pending.push([a,mid,c],[mid,b,c]);
    }else{
      const coordinates=[];
      for(const [x,z] of t){
        const y=stationGround(data,x,z);
        if(!Number.isFinite(y))return; // DEM no-data: do not draw invented elevation
        coordinates.push([x,y+heightOffset,z]);
      }
      for(const p of coordinates)buffer.push(...p);
    }
  }
}

function topSurface(geographic,station,kind){
  const positions=[];
  const shapeFor=(poly)=>{
    const shape=new THREE.Shape(poly.outer.map(([x,z])=>new THREE.Vector2(x,z)));
    for(const ring of poly.holes)shape.holes.push(new THREE.Path(ring.map(([x,z])=>new THREE.Vector2(x,z))));
    return shape;
  };
  const offset=kind==='carriageway_candidate'?.18:kind==='sidewalk_candidate'?.27:.19;
  for(const polygon of geographic){
    const triangulated=new THREE.ShapeGeometry(shapeFor(polygon));
    try{
      const p=triangulated.getAttribute('position'),idx=triangulated.index;
      const count=idx?.count??p.count;
      for(let i=0;i<count;i+=3){
        const triangle=[];
        for(let j=0;j<3;j++){
          const k=idx?idx.getX(i+j):i+j;
          triangle.push([p.getX(k),p.getY(k)]);
        }
        addTriangle(positions,station,triangle,offset);
      }
    }finally{triangulated.dispose();}
  }
  if(!positions.length)return null;
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.computeVertexNormals();
  const material=new THREE.MeshStandardMaterial({
    ...MATERIALS[kind],side:THREE.DoubleSide,metalness:0,
    depthWrite:true,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1
  });
  const mesh=new THREE.Mesh(geometry,material);
  mesh.name='推定 '+kind+'（視覚のみ）';
  mesh.userData.estimatedRoadSidewalk=true;
  mesh.renderOrder=5;
  return mesh;
}

function curbWalls(lines,station){
  const positions=[];
  for(const line of lines){
    for(let k=0;k<line.length-1;k++){
      const [x0,z0]=line[k],[x1,z1]=line[k+1];
      const distance=Math.hypot(x1-x0,z1-z0);
      if(distance<0.001)continue;
      const steps=Math.ceil(distance/2);
      for(let i=0;i<steps;i++){
        const t0=i/steps,t1=(i+1)/steps;
        const a=[x0+(x1-x0)*t0,z0+(z1-z0)*t0];
        const b=[x0+(x1-x0)*t1,z0+(z1-z0)*t1];
        const ah=stationGround(station,...a),bh=stationGround(station,...b);
        if(!Number.isFinite(ah)||!Number.isFinite(bh))continue;
        const lowA=[a[0],ah+.18,a[1]],highA=[a[0],ah+.27,a[1]];
        const lowB=[b[0],bh+.18,b[1]],highB=[b[0],bh+.27,b[1]];
        for(const vertex of [lowA,highA,highB,lowA,highB,lowB])positions.push(...vertex);
      }
    }
  }
  if(!positions.length)return null;
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.computeVertexNormals();
  const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({
    color:0xb7b6ad,roughness:1,side:THREE.DoubleSide,metalness:0,
  }));
  mesh.name='縁石候補の側面（高さ9cmの演出・実測ではない）';
  mesh.userData.estimatedCurb=true;
  mesh.renderOrder=6;
  return mesh;
}

export function buildStationRoadSplitObject(raw,station,origin){
  validateRoadSplit(raw,station);
  const group=new THREE.Group();
  group.name='駅東口100m: 車道・歩道・縁石の推定立体表示（視覚実験）';
  group.userData.roadSplitStatus='estimated-visual-only';
  group.userData.roadSplitStats=raw.statistics;
  group.position.set(station.center_east_m-origin.east,0,origin.north-station.center_north_m);
  for(const kind of Object.keys(MATERIALS)){
    const mesh=topSurface(raw.layers[kind],station,kind);
    if(mesh)group.add(mesh);
  }
  const curbs=curbWalls(raw.curb_candidates,station);
  if(curbs)group.add(curbs);
  return group;
}
