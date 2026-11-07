import * as THREE from 'three';

// Official PLATEAU tran LOD1 is a corridor extent, never a surveyed carriageway.
export function stationGround(data,x,z){
  if(x < -150 || x > 150 || z < -150 || z > 150)return null;
  if(data.visualTerrain){
    for(const triangle of data.visualTerrain.triangles){
      const [[ax,az,ah],[bx,bz,bh],[cx,cz,ch]]=triangle;
      if(x<Math.min(ax,bx,cx)-1e-6||x>Math.max(ax,bx,cx)+1e-6||
         z<Math.min(az,bz,cz)-1e-6||z>Math.max(az,bz,cz)+1e-6)continue;
      const det=(bz-cz)*(ax-cx)+(cx-bx)*(az-cz);
      if(Math.abs(det)<1e-10)continue;
      const a=((bz-cz)*(x-cx)+(cx-bx)*(z-cz))/det;
      const b=((cz-az)*(x-cx)+(ax-cx)*(z-cz))/det,c=1-a-b;
      if(Math.min(a,b,c)>=-1e-7)return a*ah+b*bh+c*ch;
    }
    return null;
  }
  const grid=data.terrain, [x0,z0,x1,z1]=grid.bounds_local_xz_m;
  if(x<x0||x>x1||z<z0||z>z1)return null;
  const u=(x-x0)/grid.step_m,v=(z-z0)/grid.step_m;
  const ix=Math.min(Math.floor(u),grid.heights_relative_m[0].length-2);
  const iz=Math.min(Math.floor(v),grid.heights_relative_m.length-2);
  const fx=u-ix,fz=v-iz,h=grid.heights_relative_m;
  return grid.height_origin_tp_m+
    ((h[iz][ix]*(1-fx)+h[iz][ix+1]*fx)*(1-fz)+
     (h[iz+1][ix]*(1-fx)+h[iz+1][ix+1]*fx)*fz);
}

export function validateStationRoads(data){
  if(data?.schema!=='therabby.geoengine.station-road-corridor.v0.2'||data.status!=='complete'||
     data.projected_crs!=='EPSG:6677'||!Number.isFinite(data.center_east_m)||
     !Number.isFinite(data.center_north_m)||data.road_count!==data.roads?.length||
     JSON.stringify(data.bounds_local_xz_m)!=='[-150,-150,150,150]'||
     JSON.stringify(data.terrain?.bounds_local_xz_m)!=='[-150,-150,150,150]'||
     data.terrain.step_m!==5||data.terrain.vertical_datum!=='T.P. (Tokyo Peil)'||
     data.terrain.heights_relative_m.length!==61||
     data.terrain.heights_relative_m.some(row=>row.length!==61))
    throw new Error('駅東口道路範囲の形式・座標系・標高基準が未対応です');
  for(const road of data.roads){
    if(road.geometry_quality!=='official-road-extent-not-carriageway'||
       road.polygon.length<3||road.polygon.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v)||Math.abs(v)>150.001)))
      throw new Error(`駅東口道路範囲の品質または座標が不正です: ${road.id}`);
  }
  return data;
}

export function buildStationRoadObject(data,origin,texture=null){
  validateStationRoads(data);
  const positions=[],uvs=[];
  function addTriangle(a,b,c){
    const stack=[[a,b,c]];
    while(stack.length){
      const tri=stack.pop();
      const lengths=[Math.hypot(tri[0][0]-tri[1][0],tri[0][1]-tri[1][1]),
        Math.hypot(tri[1][0]-tri[2][0],tri[1][1]-tri[2][1]),
        Math.hypot(tri[2][0]-tri[0][0],tri[2][1]-tri[0][1])];
      const longest=lengths.indexOf(Math.max(...lengths));
      if(lengths[longest]>4){
        const p=tri[longest],q=tri[(longest+1)%3],r=tri[(longest+2)%3];
        const mid=[(p[0]+q[0])/2,(p[1]+q[1])/2];
        stack.push([p,mid,r],[mid,q,r]);
      }else{
        for(const [x,z] of tri){
          const ground=stationGround(data,x,z);
          if(ground===null)throw new Error('道路面がDEM5A範囲外です');
          positions.push(x,ground+.08,z);
          uvs.push((data.center_east_m+x)/7,(data.center_north_m-z)/7);
        }
      }
    }
  }
  for(const road of data.roads){
    const shape=new THREE.Shape(road.polygon.map(([x,z])=>new THREE.Vector2(x,z)));
    const geometry=new THREE.ShapeGeometry(shape);
    const p=geometry.getAttribute('position'),indices=geometry.index;
    for(let i=0;i<(indices?.count??p.count);i+=3){
      const points=[];
      for(let j=0;j<3;j++){
        const k=indices?indices.getX(i+j):i+j;
        points.push([p.getX(k),p.getY(k)]);
      }
      addTriangle(...points);
    }
    geometry.dispose();
  }
  const meshGeometry=new THREE.BufferGeometry();
  meshGeometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  meshGeometry.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));
  meshGeometry.computeVertexNormals();
  const material=new THREE.MeshStandardMaterial({color:texture?0xb6babb:0x777e81,map:texture,roughness:.95,metalness:0,side:THREE.DoubleSide});
  material.userData.asphaltMap=texture;
  const mesh=new THREE.Mesh(meshGeometry,material);
  mesh.name='PLATEAU LOD1 道路外形（車道・歩道未分離）';
  mesh.position.set(data.center_east_m-origin.east,0,origin.north-data.center_north_m);
  mesh.renderOrder=2;
  return mesh;
}

// Neutral visual ground only: the DEM does not classify paving or sidewalks.
export function buildStationGroundObject(data,origin){
  if(!data.visualTerrain?.triangles?.length)return null;
  const positions=[];
  for(const triangle of data.visualTerrain.triangles)for(const [x,z,y] of triangle)positions.push(x,y+.02,z);
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.computeVertexNormals();
  const material=new THREE.MeshStandardMaterial({color:0x9b9d9a,roughness:1,side:THREE.DoubleSide});
  material.onBeforeCompile=shader=>{
    shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nvarying vec2 stationXZ;')
      .replace('#include <begin_vertex>','#include <begin_vertex>\nstationXZ=position.xz;');
    shader.fragmentShader=shader.fragmentShader.replace('#include <common>','#include <common>\nvarying vec2 stationXZ;')
      .replace('#include <clipping_planes_fragment>','#include <clipping_planes_fragment>\nif(abs(stationXZ.x)>150.0 || abs(stationXZ.y)>150.0) discard;');
  };
  const mesh=new THREE.Mesh(geometry,material);
  mesh.position.set(data.center_east_m-origin.east,0,origin.north-data.center_north_m);
  mesh.name='駅前の仮地表色（歩道の位置は未確認）';
  return mesh;
}
