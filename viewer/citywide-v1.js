import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { projectFukushima } from './geoengine-citywide-api.js';
import {buildStationRoadObject,buildStationGroundObject,stationGround,validateStationRoads} from './geoengine-station-roads-v02.js';
import {stationStyleProfiles} from './station-style-profiles.js';
import {findWalkCollision,findWalkInterior,walkSlide,insideWalkArea,walkElevationAllowed} from './geoengine-walk-collision.js';

const $=id=>document.getElementById(id);
const benchmarkMode=new URLSearchParams(location.search).get('benchmark');
const initialStationPhoto=new URLSearchParams(location.search).get('station_lod2')==='1';
const photoPilotMode=new URLSearchParams(location.search).get('photo_pilot')==='1';
const photoStreamSetting=new URLSearchParams(location.search).get('photo_stream');
const photoStreamMode=photoStreamSetting==='1'||photoStreamSetting==='all';
const photoStreamFull=photoStreamSetting==='all';
let photoPilot=null;
const autoBenchmark=benchmarkMode==='1'||benchmarkMode==='smoke';
let autoBenchmarkStarted=false;
const origin={east:55000,north:195000};
const assetRoots={building:new URL('../data/derived/fukushima-citywide-lod1-glb/',import.meta.url),
  osmBuilding:new URL('../data/derived/fukushima-citywide-osm-buildings-glb/',import.meta.url),
  far:new URL('../data/derived/fukushima-citywide-far-glb/',import.meta.url),
  terrain:new URL('../data/derived/fukushima-citywide-terrain-glb/',import.meta.url),
  road:new URL('../data/derived/fukushima-citywide-roads-v1/',import.meta.url),
  photo:new URL('../data/derived/fukushima-station-lod2-overlay/',import.meta.url),
  stationRoad:new URL('../data/derived/fukushima-station-roads-v02/road_extent.json',import.meta.url)};
const presets={station:[37.7548,140.4597],iizaka:[37.8306,140.4547],
  hanamiyama:[37.7223,140.4977],tsuchiyu:[37.6821,140.3200]};
const scene=new THREE.Scene();scene.background=new THREE.Color(0xacc5cd);scene.fog=new THREE.Fog(0xacc5cd,2500,5500);
const viewport=$('viewport');
const renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'default'});
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.setPixelRatio(1);renderer.setSize(viewport.clientWidth,viewport.clientHeight,false);
viewport.prepend(renderer.domElement);
const camera=new THREE.PerspectiveCamera(55,viewport.clientWidth/viewport.clientHeight,1,12000);
const controls=new OrbitControls(camera,renderer.domElement);
controls.enableDamping=true;controls.dampingFactor=.09;controls.minDistance=8;controls.maxDistance=5000;
controls.maxPolarAngle=Math.PI*.52;
scene.add(new THREE.HemisphereLight(0xf4f9ff,0x607f70,2.25));
const sunlight=new THREE.DirectionalLight(0xffecd2,2.1);sunlight.position.set(-1200,2400,500);scene.add(sunlight);
const loader=new GLTFLoader(), raycaster=new THREE.Raycaster(), rayDirection=new THREE.Vector3(0,-1,0);
const manifests={},index=new Map(),active=new Map(),pending=new Map(),queue=[];
let desired=new Set(),inProgress=0,quality='light',viewMode='overview',pendingGround=false,tour=null,lastSchedule=0,lastStatus=0,
  lastFrame=0,frameTimes=[],loadFailures=0,loadSuccess=0,unloads=0,measure=null,lastMeasurement=null,lastMeasurementUrl=null,
  photoEnabled=false,lastMoveAlign=0,stationRoadData=null,stationRoadMesh=null,stationGroundMesh=null,
  photoComparisonFrames=null,comparisonUrls=[],stationInspection=false;
const moveKeys=new Set();
let walking=false,walkYaw=0,walkPitch=0,walkDrag=null;
const walkRay=new THREE.Raycaster(),walkDown=new THREE.Raycaster();
const walkTerrainBounds=new WeakMap();
function walkGroundAt(x,z,terrain){
  const nearby=terrain.filter(root=>{
    let box=walkTerrainBounds.get(root);
    if(!box){root.updateWorldMatrix(true,true);box=new THREE.Box3().setFromObject(root);walkTerrainBounds.set(root,box);}
    return x>=box.min.x-0.01&&x<=box.max.x+0.01&&z>=box.min.z-0.01&&z<=box.max.z+0.01;
  });
  if(!nearby.length)return null;
  walkDown.set(new THREE.Vector3(x,3000,z),rayDirection);walkDown.far=4000;
  return walkDown.intersectObjects(nearby,true)[0]??null;
}
function stopWalking(){
  if(!walking)return;
  walking=false;stationInspection=false;moveKeys.clear();controls.enabled=true;
  walkDrag=null;
  $('walk').textContent='駅前を歩く';$('walk-status').textContent='歩行中はWASDで小走り、画面をドラッグして視点変更します。Shiftで加速。';
}
function walkLook(){
  const direction=new THREE.Vector3(-Math.sin(walkYaw)*Math.cos(walkPitch),Math.sin(walkPitch),-Math.cos(walkYaw)*Math.cos(walkPitch));
  controls.target.copy(camera.position).add(direction.multiplyScalar(10));camera.lookAt(controls.target);
  $('walk-status').dataset.eyeY=camera.position.y.toFixed(5);
}
function walkStep(movement,allowSlide=true){
  const area=manifests.photo?.area;if(!area||!photoEnabled){$('walk-status').textContent='駅前LOD2と地形の読み込みを待っています。';return;}
  const buildings=[...active].filter(([key])=>key.startsWith('photo-')).map(([,item])=>item.root);
  const terrain=[...active].filter(([key])=>key.startsWith('terrain:')).map(([,item])=>item.root);
  if(!buildings.length||!terrain.length){$('walk-status').textContent='建物と地形の読み込みを待っています。';return;}
  const next=camera.position.clone().add(movement),east=origin.east+next.x,north=origin.north-next.z;
  if(!insideWalkArea(area,east,north)){$('walk-status').textContent='駅前300m区域の端です。';return;}
  const ground=walkGroundAt(next.x,next.z,terrain);
  if(!ground){$('walk-status').textContent='この場所の地面データがありません。';return;}
  const newY=ground.point.y+1.6;
  if(!walkElevationAllowed(camera.position.y,ground.point.y,movement.length())){$('walk-status').textContent='地面の高低差が大きいため移動を止めました。';return;}
  const collision=findWalkCollision(buildings,camera.position,movement,walkRay);
  if(collision){
    const along=allowSlide?walkSlide(movement,collision):null;
    if(along){walkStep(along,false);return;}
    $('walk-status').textContent='建物の壁に接近しています。';return;
  }
  if(findWalkInterior(buildings,new THREE.Vector3(next.x,newY,next.z),walkRay)){
    $('walk-status').textContent='建物の内部には移動できません。';return;
  }
  camera.position.set(next.x,newY,next.z);walkLook();
  $('walk-status').textContent='歩行中：WASDで小走り、画面ドラッグで視点変更。Shiftで加速。';
}
const stationStyleUniform={value:0},stationPhotoSharpUniform={value:0};

// Patterns are visual estimates; geometry, georeferencing and original maps remain intact.
function installStationStyle(material){
  if(material.userData.stationStyleInstalled)return;
  material.userData.stationStyleInstalled=true;
  let hash=2166136261;
  for(const char of material.name)hash=Math.imul(hash^char.charCodeAt(0),16777619);
  const shade=(hash>>>0)%5;
  const profile=stationStyleProfiles[material.name];
  const wallColor=profile?new THREE.Color().setRGB(...profile.color.map(c=>c/255),THREE.SRGBColorSpace):
    new THREE.Color().setRGB(.38+shade*.06,.40+shade*.05,.40+shade*.04);
  material.onBeforeCompile=shader=>{
    shader.uniforms.stationStyle=stationStyleUniform;
    shader.uniforms.stationPhotoSharp=stationPhotoSharpUniform;
    shader.uniforms.stationTexel={value:new THREE.Vector2(1/512,1/512)};
    material.userData.stationShader=shader;
    shader.uniforms.stationWall={value:wallColor};
    shader.uniforms.stationLayout={value:profile?.layout??0};
    shader.uniforms.stationFloor={value:profile?.floor_m??3.2};
    shader.uniforms.stationBay={value:profile?.bay_m??3.0};
    shader.vertexShader=shader.vertexShader.replace('#include <common>',`#include <common>
      varying vec3 stationWorld; varying vec3 stationNormal;`)
      .replace('#include <project_vertex>',`stationWorld=(modelMatrix*vec4(transformed,1.0)).xyz;
        stationNormal=normalize(mat3(modelMatrix)*normal);
        #include <project_vertex>`);
    shader.fragmentShader=shader.fragmentShader.replace('#include <common>',`#include <common>
      varying vec3 stationWorld; varying vec3 stationNormal;
      uniform float stationStyle; uniform float stationPhotoSharp; uniform vec2 stationTexel; uniform vec3 stationWall;
      uniform float stationLayout; uniform float stationFloor; uniform float stationBay;`)
      .replace('#include <map_fragment>',`#include <map_fragment>
      #ifdef USE_MAP
      if(stationPhotoSharp>0.0){
        vec2 dx=vec2(stationTexel.x*1.4,0.0),dy=vec2(0.0,stationTexel.y*1.4);
        vec3 center=texture2D(map,vMapUv).rgb;
        vec3 adjacent=(texture2D(map,vMapUv+dx).rgb+texture2D(map,vMapUv-dx).rgb+
          texture2D(map,vMapUv+dy).rgb+texture2D(map,vMapUv-dy).rgb)*0.25;
        vec3 edge=center-adjacent;
        float strength=smoothstep(0.008,0.035,max(max(abs(edge.r),abs(edge.g)),abs(edge.b)));
        diffuseColor.rgb+=clamp(edge,vec3(-0.08),vec3(0.08))*stationPhotoSharp*strength;
      }
      #endif`)
      .replace('#include <color_fragment>',`#include <color_fragment>
      if(stationStyle>0.5){
        vec3 n=normalize(stationNormal);
        vec3 wall=stationWall;
        if(abs(n.y)<0.65){
          float horizontal=abs(n.x)>abs(n.z)?stationWorld.z:stationWorld.x;
          vec2 cell=vec2(fract(horizontal/stationBay),fract(stationWorld.y/stationFloor));
          float side=stationLayout<0.5?0.12:(stationLayout<1.5?0.20:0.07);
          float low=stationLayout<0.5?0.30:(stationLayout<1.5?0.24:0.43);
          float high=stationLayout<0.5?0.82:(stationLayout<1.5?0.79:0.76);
          float windowMask=step(side,cell.x)*step(cell.x,1.0-side)*step(low,cell.y)*step(cell.y,high);
          float frame=step(0.485,cell.x)*step(cell.x,0.515);
          float sill=step(0.03,cell.y)*step(cell.y,0.055);
          wall=mix(wall,stationWall*0.72,sill);
          wall=mix(wall,vec3(0.095,0.14,0.17),windowMask*(1.0-frame));
        }else{wall*=0.78;}
        diffuseColor.rgb=wall;
      }`);
  };
  material.customProgramCacheKey=()=> 'geoengine-station-estimated-style-v1';
  material.needsUpdate=true;
}

function setStatus(message,error=false){$('status').textContent=message;$('status').className=error?'error':'';}
function distance2(tile,east,north){
  const e=(tile.tile_origin_east_m??tile.bbox_east_north_m?.[0]??0)+500;
  const n=(tile.tile_origin_north_m??tile.bbox_east_north_m?.[3]??0)-500;
  return (e-east)**2+(n-north)**2;
}
function dispose(root){
  if(!root)return;
  scene.remove(root);
  const geometries=new Set(),materials=new Set(),textures=new Set();
  root.traverse(object=>{
    if(object.geometry)geometries.add(object.geometry);
    for(const mat of Array.isArray(object.material)?object.material:object.material?[object.material]:[]){
      materials.add(mat);for(const value of [...Object.values(mat),...Object.values(mat.userData)])if(value?.isTexture)textures.add(value);
    }
  });
  for(const texture of textures){texture.dispose();if(typeof texture.image?.close==='function')texture.image.close();}
  for(const material of materials)material.dispose();
  for(const geometry of geometries)geometry.dispose();
}
function roadColor(edge){
  if(edge.road_class==='walk'||['footway','path','pedestrian','cycleway','bridleway'].includes(edge.highway))return 0xc9ccc4;
  if(['motorway','trunk','primary','secondary'].includes(edge.highway))return 0xaeb4b8;
  return 0xa4adb0;
}
function makeAsphaltTexture(){
  const canvas=document.createElement('canvas');canvas.width=canvas.height=128;
  const context=canvas.getContext('2d'),pixels=context.createImageData(128,128);
  let seed=27182818;
  for(let i=0;i<pixels.data.length;i+=4){
    seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;
    const grain=116+(seed>>>0)%31;
    pixels.data[i]=grain;pixels.data[i+1]=grain+2;pixels.data[i+2]=grain+3;pixels.data[i+3]=255;
  }
  context.putImageData(pixels,0,0);
  const texture=new THREE.CanvasTexture(canvas);texture.wrapS=texture.wrapT=THREE.RepeatWrapping;
  texture.colorSpace=THREE.SRGBColorSpace;
  texture.minFilter=THREE.LinearMipmapLinearFilter;texture.magFilter=THREE.LinearFilter;
  texture.anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),quality==='high'?8:quality==='standard'?4:2);
  return texture;
}
function buildRoadObject(tile){
  const root=new THREE.Group();root.position.set(tile.tile_origin_east_m-origin.east,0,origin.north-tile.tile_origin_north_m);
  const buckets=new Map(),nodes=new Map(),centerPoints=[],guidePositions=[];let displayed=0,unknown=0,structures=0;
  const texture=makeAsphaltTexture();
  function groundAt(point,linear){
    if(!stationRoadData)return linear;
    return stationGround(stationRoadData,
      tile.tile_origin_east_m+point[0]-stationRoadData.center_east_m,
      stationRoadData.center_north_m-tile.tile_origin_north_m+point[1])??linear;
  }
  function emit(color,vertices){
    if(!buckets.has(color))buckets.set(color,{positions:[],uvs:[]});
    const bucket=buckets.get(color);
    for(const [x,y,z] of vertices){
      bucket.positions.push(x,y,z);
      bucket.uvs.push((tile.tile_origin_east_m+x)/7,(tile.tile_origin_north_m-z)/7);
    }
  }
  for(const edge of tile.edges){
    const h0=edge.ground_height_from_tp_m,h1=edge.ground_height_to_tp_m;
    if(!Number.isFinite(h0)||!Number.isFinite(h1)){unknown++;continue;}
    if(edge.highway==='steps'){structures++;continue;}
    if(!['','no','false','0'].includes(String(edge.bridge_osm_tag||'').toLowerCase())||
       !['','no','false','0'].includes(String(edge.tunnel_osm_tag||'').toLowerCase())){structures++;continue;}
    const [a,b]=edge.points,dx=b[0]-a[0],dz=b[1]-a[1],len=Math.hypot(dx,dz);
    if(len<.01)continue;
    // OSM centreline + estimated width: visual road surface, not a collision mesh.
    const half=Math.min(10,Math.max(1,edge.width_m/2)),ox=-dz/len*half,oz=dx/len*half;
    const stationEast=stationRoadData&&tile.tile_origin_east_m+(a[0]+b[0])/2-stationRoadData.center_east_m;
    const stationSouth=stationRoadData&&stationRoadData.center_north_m-tile.tile_origin_north_m+(a[1]+b[1])/2;
    const inStation=stationRoadData&&Math.abs(stationEast)<160&&Math.abs(stationSouth)<160;
    const color=roadColor(edge),pieces=Math.max(1,Math.ceil(len/(inStation?4:8)));
    // Deliberately approximate guides; not surveyed road markings or lanes.
    function guideStrip(start,end,offset){
      const width=.08,px=-dz/len,pz=dx/len;
      const vertex=(distance,side)=>{
        const t=distance/len,x=a[0]+dx*t+px*(offset+side*width/2),z=a[1]+dz*t+pz*(offset+side*width/2);
        return [x,groundAt([x,z],h0+(h1-h0)*t)+.145,z];
      };
      const points=[vertex(start,-1),vertex(start,1),vertex(end,1),vertex(start,-1),vertex(end,1),vertex(end,-1)];
      for(const point of points)guidePositions.push(...point);
    }
    if(inStation&&color!==0xc9ccc4&&half>=2&&len>8){
      for(let start=3;start<len-3;start+=3){
        const end=Math.min(start+3,len-3);
        guideStrip(start,end,-half+.25);guideStrip(start,end,half-.25);
        if(Number.parseInt(edge.lanes_osm_tag,10)>=2&&!['yes','1','true','-1'].includes(String(edge.oneway_osm_tag).toLowerCase()))
          guideStrip(start,Math.min(start+1.5,end),0);
      }
    }
    for(let segment=0;segment<pieces;segment++){
      const t0=segment/pieces,t1=(segment+1)/pieces;
      const p0=[a[0]+dx*t0,a[1]+dz*t0],p1=[a[0]+dx*t1,a[1]+dz*t1];
      const stripVertex=(point,sign,t)=>{
        const x=point[0]+ox*sign,z=point[1]+oz*sign;
        return [x,groundAt([x,z],h0+(h1-h0)*t)+.12,z];
      };
      const left0=stripVertex(p0,-1,t0),right0=stripVertex(p0,1,t0),
        left1=stripVertex(p1,-1,t1),right1=stripVertex(p1,1,t1);
      emit(color,[left0,right0,right1,left0,right1,left1]);
    }
    const gy0=groundAt(a,h0),gy1=groundAt(b,h1);
    centerPoints.push(a[0],gy0+.16,a[1],b[0],gy1+.16,b[1]);
    if(color!==0xc9ccc4){
      for(const [id,p,h] of [[edge.from_node,a,gy0],[edge.to_node,b,gy1]]){
        if(p[0]<=.01||p[0]>=999.99||p[1]<=.01||p[1]>=999.99)continue;
        const node=nodes.get(id)??{point:p,ground:h,radius:0,count:0,color};
        node.radius=Math.max(node.radius,half);node.count++;nodes.set(id,node);
      }
    }
    displayed++;
  }
  for(const node of nodes.values()){
    if(node.count<2)continue;
    const [x,z]=node.point,y=node.ground+.125,r=node.radius;
    for(let i=0;i<12;i++){
      const a=i*Math.PI/6,b=(i+1)*Math.PI/6;
      const rim=angle=>{const px=x+Math.cos(angle)*r,pz=z+Math.sin(angle)*r;
        return [px,groundAt([px,pz],node.ground)+.125,pz];};
      emit(node.color,[[x,y,z],rim(a),rim(b)]);
    }
  }
  for(const [color,bucket] of buckets){
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(bucket.positions,3));
    geometry.setAttribute('uv',new THREE.Float32BufferAttribute(bucket.uvs,2));
    geometry.computeVertexNormals();
    const material=new THREE.MeshStandardMaterial({color,side:THREE.DoubleSide,roughness:.95,metalness:0,map:$('road-surface').checked?texture:null});
    material.userData.asphaltMap=texture;
    const mesh=new THREE.Mesh(geometry,material);mesh.userData.roadSurface=true;root.add(mesh);
  }
  const guides=new THREE.BufferGeometry();guides.setAttribute('position',new THREE.Float32BufferAttribute(guidePositions,3));
  const guideMesh=new THREE.Mesh(guides,new THREE.MeshBasicMaterial({color:0xe4e1ce,side:THREE.DoubleSide,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1}));
  guideMesh.name='道路の目安線（推定・実際の区画線ではない）';guideMesh.userData.roadGuide=true;guideMesh.visible=$('road-guides').checked;root.add(guideMesh);
  const lines=new THREE.BufferGeometry();lines.setAttribute('position',new THREE.Float32BufferAttribute(centerPoints,3));
  const centerline=new THREE.LineSegments(lines,new THREE.LineBasicMaterial({color:0xffbd59,depthTest:false}));
  centerline.name='OSM道路中心線';centerline.visible=$('road-centerline').checked;
  centerline.renderOrder=5;root.add(centerline);
  root.renderOrder=2;
  return {root,displayed,unknown,structures};
}
async function fetchStationRoads(){
  const response=await fetch(assetRoots.stationRoad);
  if(!response.ok)throw new Error(`駅東口道路外形 HTTP ${response.status}`);
  const data=validateStationRoads(await response.json());
  try{
    const terrainResponse=await fetch(new URL('../data/derived/fukushima-station-roads-v02/visual_terrain.json',import.meta.url));
    if(!terrainResponse.ok)throw new Error(`HTTP ${terrainResponse.status}`);
    const visual=await terrainResponse.json();
    if(visual.schema!=='therabby.geoengine.station-visual-terrain.v1'||
      visual.projected_crs!=='EPSG:6677'||visual.vertical_datum!=='T.P. (Tokyo Peil)'||
      visual.center_east_m!==data.center_east_m||visual.center_north_m!==data.center_north_m||
      !Array.isArray(visual.triangles)||!visual.triangles.length)throw new Error('地形形式が不正です');
    data.visualTerrain=visual;
  }catch(error){console.warn('表示地形を利用できないため従来の標高格子を使用します:',error);}
  stationRoadData=data;
  stationGroundMesh=buildStationGroundObject(data,origin);
  if(stationGroundMesh){stationGroundMesh.visible=photoEnabled;scene.add(stationGroundMesh);}
  stationRoadMesh=buildStationRoadObject(data,origin,makeAsphaltTexture());
  stationRoadMesh.visible=$('roads').checked&&$('road-polygon').checked;
  scene.add(stationRoadMesh);
}
function applyDebugDisplay(){
  if(stationRoadMesh){
    stationRoadMesh.visible=$('roads').checked&&$('road-polygon').checked;
    stationRoadMesh.material.map=$('road-surface').checked?stationRoadMesh.material.userData.asphaltMap:null;
    stationRoadMesh.material.color.setHex($('road-surface').checked?0xb6babb:0x777e81);
    stationRoadMesh.material.needsUpdate=true;
  }
  for(const [key,item] of active){
    if(key.startsWith('road:'))item.root.traverse(object=>{
      if(object.isLineSegments)object.visible=$('road-centerline').checked;
      if(object.userData.roadGuide)object.visible=$('road-guides').checked;
      if(object.userData.roadSurface){
        const material=object.material;
        material.map=$('road-surface').checked?material.userData.asphaltMap:null;
        material.needsUpdate=true;
      }
    });
    if(key.startsWith('photo-'))item.root.traverse(object=>{
      for(const material of Array.isArray(object.material)?object.material:object.material?[object.material]:[]){
        if(material.userData.officialPhotoMap){
          material.map=$('building-texture').checked?material.userData.officialPhotoMap:null;
          material.needsUpdate=true;
        }
      }
    });
  }
  $('lod-info').hidden=!$('building-lod').checked;
  $('height-info').hidden=!$('road-height').checked;
}
function applyPhotoSampling(texture,variant){
  const selected=$('photo-anisotropy').value;
  const requested=selected==='auto'?(variant==='high'||(photoStreamFull&&quality!=='light')?8:variant==='medium'?4:2):Number(selected);
  texture.anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),requested);
  texture.minFilter=$('photo-filter').value==='linear'?THREE.LinearFilter:THREE.LinearMipmapLinearFilter;
  texture.magFilter=THREE.LinearFilter;
  texture.needsUpdate=true;
}
function updatePhotoSampling(){
  for(const [key,item] of active){
    if(!key.startsWith('photo-'))continue;
    const variant=key.split(':',1)[0].slice(6);
    item.root.traverse(object=>{
      for(const material of Array.isArray(object.material)?object.material:object.material?[object.material]:[]){
        if(material.userData.officialPhotoMap){const texture=material.userData.officialPhotoMap;
          applyPhotoSampling(texture,texture.userData.dynamicHigh?'high':variant);}
      }
    });
  }
}
async function fetchManifest(kind){
  const response=await fetch(new URL('tileset.json',assetRoots[kind]));
  if(!response.ok)throw new Error(`${kind}目録 HTTP ${response.status}`);
  const data=await response.json();
  const expected={building:'therabby.geoengine.citywide-lod1-glb.v0.1',
    osmBuilding:'therabby.geoengine.citywide-osm-building-glb.v0.1',
    far:'therabby.geoengine.citywide-far-glb.v0.1',terrain:'therabby.geoengine.citywide-terrain-glb.v0.1',
    road:'therabby.geoengine.citywide-road-tiles.v0.1'}[kind];
  if(data.schema!==expected||!data.projected_crs?.includes('EPSG:6677')||!Array.isArray(data.tiles)||
     (kind!=='road'&&data.vertical_datum!=='T.P. (Tokyo Peil)'))
    throw new Error(`${kind}目録の形式・座標系・標高基準が未対応です`);
  manifests[kind]=data;
  for(const tile of data.tiles)index.set(`${kind}:${tile.id}`,{kind,tile});
}
async function fetchPhotoOverlay(){
  const response=await fetch(new URL('tileset.json',assetRoots.photo));
  if(!response.ok)throw new Error(`駅東口LOD2目録 HTTP ${response.status}`);
  const data=await response.json();
  if(data.schema!=='therabby.geoengine.station-lod2-overlay.v0.1'||data.status!=='complete'||
     !data.projected_crs?.includes('EPSG:6677')||data.render_vertical_frame!=='T.P. (Tokyo Peil) via DEM5A visual base'||
     !Array.isArray(data.tiles)||data.lod2_buildings<1)throw new Error('駅東口LOD2目録の形式・座標系が未対応です');
  const base=new Map(manifests.building.tiles.map(tile=>[tile.id,tile]));
  for(const photo of data.tiles){
    const tile=base.get(photo.id);
    if(!tile||photo.tile_origin_east_m!==tile.tile_origin_east_m||
       photo.tile_origin_north_m!==tile.tile_origin_north_m||
       photo.lod2_buildings!==photo.replaced_building_ids?.length||!photo.lod1_filtered)throw new Error(`LOD2 ${photo.id} とLOD1目録が不一致です`);
    for(const variant of ['low','medium','high']){
      if(!photo[`lod2_${variant}`])throw new Error(`LOD2 ${variant} ${photo.id} がありません`);
      index.set(`photo-${variant}:${photo.id}`,{kind:'photo',tile,photo,variant});
    }
  }
  manifests.photo=data;
  return data;
}
async function readTile(key,record,signal){
  const {kind,tile}=record;
  if(kind==='photo'){
    const selected=record.photo[`lod2_${record.variant}`],filtered=record.photo.lod1_filtered;
    async function loadPart(part){
      const response=await fetch(new URL(part.path,assetRoots.photo),{signal});
      if(!response.ok)throw new Error(`${key} ${part.path} HTTP ${response.status}`);
      const buffer=await response.arrayBuffer();
      if(buffer.byteLength!==part.byte_length)throw new Error(`${key} ${part.path} ファイル長不一致`);
      const gltf=await loader.parseAsync(buffer,assetRoots.photo.href);
      return gltf.scene;
    }
    let lod1,lod2;
    try{
      lod1=await loadPart(filtered);
      lod2=await loadPart(selected);
    }catch(error){dispose(lod1);dispose(lod2);throw error;}
    lod2.traverse(object=>{
      if(object.isMesh){
        const previous=object.onBeforeRender;
        object.onBeforeRender=function(renderer,scene,camera,geometry,material,group){
          previous.call(this,renderer,scene,camera,geometry,material,group);
          const image=material.map?.image,uniform=material.userData.stationShader?.uniforms.stationTexel;
          if(uniform&&image?.width&&image?.height)uniform.value.set(1/image.width,1/image.height);
        };
      }
      for(const material of Array.isArray(object.material)?object.material:object.material?[object.material]:[]){
        installStationStyle(material);
        if(material.map){
          material.userData.officialPhotoMap=material.map;
          applyPhotoSampling(material.map,record.variant);
          if(!$('building-texture').checked)material.map=null;
          material.needsUpdate=true;
        }
      }
    });
    const root=new THREE.Group();root.add(lod1,lod2);
    root.position.set(tile.tile_origin_east_m-origin.east,0,origin.north-tile.tile_origin_north_m);
    return {root,bytes:filtered.byte_length+selected.byte_length,
      buildings:filtered.buildings+record.photo.lod2_buildings,photoBuildings:record.photo.lod2_buildings};
  }
  const file=kind==='road'?tile.path:tile.glb;
  const response=await fetch(new URL(file,assetRoots[kind]),{signal});
  if(!response.ok)throw new Error(`${key} HTTP ${response.status}`);
  if(kind==='road'){
    const data=await response.json();
    if(data.schema!=='therabby.geoengine.citywide-road-tile.v0.1'||data.tile_id!==tile.id||
      data.edges.length!==tile.edge_count)throw new Error(`${key} 内容が目録と一致しません`);
    return {...buildRoadObject(data),bytes:tile.byte_length,edgeCount:data.edges.length,roadTile:data};
  }
  const buffer=await response.arrayBuffer();
  if(buffer.byteLength!==tile.byte_length)throw new Error(`${key} ファイル長が目録と一致しません`);
  const gltf=await loader.parseAsync(buffer,assetRoots[kind].href);
  const root=gltf.scene;
  root.position.set(tile.tile_origin_east_m-origin.east,0,origin.north-tile.tile_origin_north_m);
  return {root,bytes:buffer.byteLength,buildings:tile.buildings??0,farCells:tile.cells??0};
}
function pump(){
  while(inProgress<3&&queue.length){
    const key=queue.shift();if(!desired.has(key)||active.has(key)||pending.has(key))continue;
    const record=index.get(key),controller=new AbortController();
    inProgress++;pending.set(key,controller);
    readTile(key,record,controller.signal).then(item=>{
      if(!desired.has(key)){dispose(item.root);return;}
      if(record.kind==='building'||record.kind==='photo'){
        for(const [oldKey,oldItem] of active){
          if(oldKey!==key&&oldKey.endsWith(`:${record.tile.id}`)&&
             (oldKey.startsWith('building:')||oldKey.startsWith('photo-'))){
            dispose(oldItem.root);active.delete(oldKey);unloads++;
          }
        }
      }
      scene.add(item.root);active.set(key,item);loadSuccess++;
      if(record.kind==='road')applyDebugDisplay();
      if(record.kind==='terrain')alignGround();
      if(record.kind==='road'&&pendingGround)placeGroundCamera();
      if(record.kind==='road')maybeStartAutoBenchmark();
    }).catch(error=>{
      if(error.name!=='AbortError'){
        loadFailures++;console.error(error);setStatus(`タイル ${key} の読込に失敗しました: ${error.message}`,true);
      }
    }).finally(()=>{pending.delete(key);inProgress--;pump();});
  }
}
function schedule(force=false){
  if(!manifests.building)return;
  const now=performance.now();if(!force&&now-lastSchedule<260)return;lastSchedule=now;
  const east=origin.east+controls.target.x,north=origin.north-controls.target.z;
  const radius=quality==='light'?{building:1550,osmBuilding:1550,far:3350,terrain:3350,road:1550}:
    quality==='standard'?{building:2300,osmBuilding:2300,far:4450,terrain:4450,road:2200}:
    {building:2600,osmBuilding:2600,far:5000,terrain:5000,road:2500};
  const photoNear=photoEnabled&&manifests.photo&&
    Math.hypot(east-manifests.photo.area.center_east_m,north-manifests.photo.area.center_north_m)<750;
  const next=[];
  for(const kind of ['terrain','road','building','osmBuilding','far']){
    const manifest=manifests[kind];
    if(kind==='road'&&!$('roads').checked)continue;
    for(const tile of manifest.tiles){
      const d2=distance2(tile,east,north);
      if(d2>radius[kind]**2)continue;
      if(kind==='far'&&d2<=radius.building**2)continue;
      const photoVariant=$('photo-detail').value==='auto'
        ?quality==='light'?'low':quality==='standard'?'medium':'high'
        :$('photo-detail').value;
      const photoKey=`photo-${photoVariant}:${tile.id}`;
      const key=kind==='building'&&photoNear&&index.has(photoKey)?photoKey:`${kind}:${tile.id}`;
      next.push({key,priority:d2+(kind==='terrain'?0:kind==='road'?100000:kind==='building'?200000:kind==='osmBuilding'?250000:300000)});
    }
  }
  next.sort((a,b)=>a.priority-b.priority);desired=new Set(next.map(item=>item.key));
  for(const [key,controller] of pending)if(!desired.has(key))controller.abort();
  for(const [key,item] of active)if(!desired.has(key)){
    const [kind,id]=key.split(':');
    const replacement=kind==='far'?[...desired].find(k=>k===`building:${id}`||k.startsWith('photo-')&&k.endsWith(`:${id}`)):
      kind==='building'||kind.startsWith('photo-')?[...desired].find(k=>k===`far:${id}`||k===`building:${id}`||k.startsWith('photo-')&&k.endsWith(`:${id}`)):null;
    // Keep the old LOD visible until its replacement has finished parsing.
    if(replacement&&desired.has(replacement)&&!active.has(replacement))continue;
    dispose(item.root);active.delete(key);unloads++;
  }
  queue.length=0;for(const item of next)if(!active.has(item.key)&&!pending.has(item.key))queue.push(item.key);
  pump();
}
function alignGround(){
  if(stationInspection)return;
  const roots=[...active].filter(([key])=>key.startsWith('terrain:')).map(([,item])=>item.root);
  if(!roots.length)return;
  raycaster.set(new THREE.Vector3(controls.target.x,3000,controls.target.z),rayDirection);
  raycaster.far=4000;
  const hits=raycaster.intersectObjects(roots,true);
  if(!hits.length)return;
  const y=hits[0].point.y+(viewMode==='ground'?1.8:0),shift=y-controls.target.y;
  if(Math.abs(shift)>.1){controls.target.y=y;camera.position.y+=shift;controls.update();}
}
function eligibleRoad(edge){
  return ['primary','secondary','tertiary','residential','unclassified','living_street'].includes(edge.highway)&&
    Number.isFinite(edge.ground_height_from_tp_m)&&Number.isFinite(edge.ground_height_to_tp_m)&&
    !edge.bridge_osm_tag&&!edge.tunnel_osm_tag&&Math.hypot(edge.points[1][0]-edge.points[0][0],
      edge.points[1][1]-edge.points[0][1])>=.1;
}
function stopTour(){tour=null;$('road-tour').textContent='OSM道路線に沿って移動';}
function startTour(){
  let best=null;const east=origin.east+controls.target.x,north=origin.north-controls.target.z;
  for(const [key,item] of active){
    if(!key.startsWith('road:'))continue;
    const tile=item.roadTile;
    for(const edge of tile.edges){
      if(!eligibleRoad(edge))continue;
      const [a,b]=edge.points;
      const e=tile.tile_origin_east_m+(a[0]+b[0])/2,n=tile.tile_origin_north_m-(a[1]+b[1])/2;
      const distance=Math.hypot(e-east,n-north);
      if(distance<350&&(!best||distance<best.distance))best={edge,tile,distance};
    }
  }
  if(!best){setStatus('現在地から350m以内に追従できるOSM道路線がありません。',true);return false;}
  tour={edge:best.edge,tile:best.tile,forward:true,t:.5,distance_m:0,seam_crossings:0};
  viewMode='overview';$('overview').className='';$('ground').className='secondary';
  $('road-tour').textContent='道路追従を停止';
  return true;
}
function nextTourEdge(atNode){
  const old=tour.edge,[a,b]=old.points;
  const sign=tour.forward?1:-1,dx=(b[0]-a[0])*sign,dz=(b[1]-a[1])*sign;
  const oldLength=Math.hypot(dx,dz);
  let best=null;
  for(const [key,item] of active){
    if(!key.startsWith('road:'))continue;
    const tile=item.roadTile;
    for(const edge of tile.edges){
      if(edge.id===old.id||!eligibleRoad(edge))continue;
      const forward=edge.from_node===atNode;
      if(!forward&&edge.to_node!==atNode)continue;
      const [p,q]=edge.points,ex=(q[0]-p[0])*(forward?1:-1),ez=(q[1]-p[1])*(forward?1:-1);
      const alignment=(dx*ex+dz*ez)/(oldLength*Math.hypot(ex,ez));
      const score=(edge.source_way_id===old.source_way_id?100:0)+alignment*10;
      if(!best||score>best.score)best={edge,tile,forward,score};
    }
  }
  return best;
}
function advanceTour(dt){
  if(!tour||!dt)return;
  let remaining=Math.min(1,dt)*12,steps=0;
  while(remaining>0&&steps++<20){
    const [a,b]=tour.edge.points,len=Math.hypot(b[0]-a[0],b[1]-a[1]);
    const distance=(tour.forward?1-tour.t:tour.t)*len;
    const move=Math.min(remaining,distance);
    tour.t+=move/len*(tour.forward?1:-1);tour.distance_m+=move;remaining-=move;
    if(distance>move+.0001)break;
    const atNode=tour.forward?tour.edge.to_node:tour.edge.from_node;
    const next=nextTourEdge(atNode);
    if(next){
      if(next.tile.tile_id!==tour.tile.tile_id)tour.seam_crossings++;
      Object.assign(tour,{edge:next.edge,tile:next.tile,forward:next.forward,t:next.forward?0:1});
    }else{
      // The graph is read-only and legal access is unknown. Reverse at a data end.
      tour.forward=!tour.forward;
      break;
    }
  }
  const [a,b]=tour.edge.points,t=tour.t,tile=tour.tile;
  const x=tile.tile_origin_east_m+a[0]+(b[0]-a[0])*t-origin.east;
  const z=origin.north-tile.tile_origin_north_m+a[1]+(b[1]-a[1])*t;
  const y=tour.edge.ground_height_from_tp_m+
    (tour.edge.ground_height_to_tp_m-tour.edge.ground_height_from_tp_m)*t;
  controls.target.set(x,y+5,z);
  camera.position.set(x-130,y+180,z+180);
  controls.update();
}
function placeGroundCamera(){
  const focusE=origin.east+controls.target.x,focusN=origin.north-controls.target.z;
  let best=null;
  for(const [key,item] of active){
    if(!key.startsWith('road:'))continue;
    const tile=item.roadTile;
    for(const edge of tile.edges){
      if(!['primary','secondary','tertiary','residential','unclassified','living_street'].includes(edge.highway)||
         !Number.isFinite(edge.ground_height_from_tp_m)||!Number.isFinite(edge.ground_height_to_tp_m)||
         edge.bridge_osm_tag||edge.tunnel_osm_tag)continue;
      const [a,b]=edge.points,dx=b[0]-a[0],dz=b[1]-a[1],length=Math.hypot(dx,dz);
      if(length<12)continue;
      const midE=tile.tile_origin_east_m+(a[0]+b[0])/2;
      const midN=tile.tile_origin_north_m-(a[1]+b[1])/2;
      const distance=Math.hypot(midE-focusE,midN-focusN);
      if(distance>350)continue;
      const score=distance+(edge.highway==='unclassified'?25:0);
      if(!best||score<best.score)best={score,east:midE,north:midN,
        height:(edge.ground_height_from_tp_m+edge.ground_height_to_tp_m)/2,
        dx:dx/length,dz:dz/length};
    }
  }
  if(!best)return false;
  const x=best.east-origin.east,z=origin.north-best.north;
  camera.position.set(x,best.height+1.8,z);
  controls.target.set(x+best.dx*28,best.height+1.8,z+best.dz*28);
  controls.update();pendingGround=false;schedule(true);
  return true;
}
function teleport(east,north){
  stopWalking();
  stationInspection=false;
  if(!Number.isFinite(east)||!Number.isFinite(north))return;
  stopTour();
  const x=east-origin.east,z=origin.north-north;
  controls.target.set(x,80,z);
  if(viewMode==='ground'){camera.position.set(x-250,380,z+310);pendingGround=true;}
  else camera.position.set(x-680,850,z+820);
  controls.update();schedule(true);alignGround();
}
function setView(mode){
  stopWalking();
  stationInspection=false;
  stopTour();
  viewMode=mode;alignGround();const t=controls.target;
  if(mode==='ground'){
    pendingGround=true;
    if(!placeGroundCamera())camera.position.set(t.x-140,t.y+90,t.z+180);
    controls.maxDistance=350;
  }
  else{camera.position.set(t.x-680,t.y+770,t.z+820);controls.maxDistance=5000;}
  controls.update();$('ground').className=mode==='ground'?'':'secondary';
  $('overview').className=mode==='overview'?'':'secondary';
}
function doSearch(){
  const value=$('search').value.trim();if(!value)return;
  const coordinate=value.match(/^([+-]?\d+(?:\.\d+)?)\s*[,、\s]\s*([+-]?\d+(?:\.\d+)?)$/);
  try{
    if(coordinate){const [east,north]=projectFukushima(Number(coordinate[1]),Number(coordinate[2]));
      teleport(east,north);$('search-hint').textContent='入力座標へ移動しました（EPSG:6677へ変換）。';return;}
    const entries=manifests.search?.entries??[];
    const found=entries.find(item=>item.name===value)||entries.find(item=>item.name.includes(value));
    if(!found)throw new Error('収録済みの道路名が見つかりません。緯度, 経度でも検索できます。');
    teleport(found.east_m,found.north_m);
    $('search-hint').textContent=`「${found.name}」のOSM道路線分上の代表点へ移動しました。測量済みの地点座標ではありません。`;
  }catch(error){$('search-hint').textContent=error.message;}
}
function percentile(values,p){if(!values.length)return 0;const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.ceil(sorted.length*p)-1];}
function captureRenderPixels(){
  renderer.render(scene,camera);
  const width=renderer.domElement.width,height=renderer.domElement.height;
  const gl=renderer.getContext(),pixels=new Uint8Array(width*height*4);
  gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
  if(gl.getError()!==gl.NO_ERROR)throw new Error('WebGL画面の画素を取得できません');
  const copy=document.createElement('canvas');copy.width=width;copy.height=height;
  const context=copy.getContext('2d'),image=context.createImageData(width,height),row=width*4;
  for(let y=0;y<height;y++)image.data.set(pixels.subarray((height-y-1)*row,(height-y)*row),y*row);
  context.putImageData(image,0,0);
  return copy;
}
async function compareStationPhotos(){
  stopWalking();
  if(measure)throw new Error('10分測定の終了後に写真比較を実行してください');
  if(!photoEnabled||!manifests.photo)throw new Error('駅東口の公式写真LOD2を有効にしてください');
  const east=origin.east+controls.target.x,north=origin.north-controls.target.z;
  if(Math.hypot(east-manifests.photo.area.center_east_m,north-manifests.photo.area.center_north_m)>500)
    throw new Error('福島駅東口へ移動してから比較してください');
  const button=$('compare-photo'),result=$('compare-result');
  const previousDetail=$('photo-detail').value,previousTexture=$('building-texture').checked;
  button.disabled=true;controls.enabled=false;moveKeys.clear();stopTour();
  $('building-texture').checked=true;applyDebugDisplay();
  const samples=[];
  try{
    for(const variant of ['low','high']){
      result.textContent=`写真${variant==='low'?'Low':'元JPEG'}を読み込み、同一視点で計測中…`;
      const loadStart=performance.now();
      $('photo-detail').value=variant;schedule(true);
      const keys=manifests.photo.tiles.map(tile=>`photo-${variant}:${tile.id}`);
      const deadline=performance.now()+45000;
      while(!keys.every(key=>active.has(key))){
        if(document.hidden)throw new Error('比較中に画面が背面になりました。前面で再実行してください');
        if(performance.now()>deadline)throw new Error(`${variant}の写真読込が45秒で完了しませんでした`);
        await new Promise(resolve=>setTimeout(resolve,100));
      }
      const loadMs=performance.now()-loadStart;
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      photoComparisonFrames=[];
      await new Promise(resolve=>setTimeout(resolve,3000));
      const frames=photoComparisonFrames;photoComparisonFrames=null;
      if(document.hidden||frames.length<30)throw new Error('前面でのフレーム計測が不足しました');
      const frameSum=frames.reduce((sum,value)=>sum+value,0);
      const snapshot=captureRenderPixels();
      samples.push({variant,load_ms:Math.round(loadMs),frames:frames.length,
        average_fps:frames.length*1000/frameSum,frame_ms_p95:percentile(frames,.95),
        photo_rgba8_mip_estimate_bytes:manifests.photo.quality_variants[variant].rgba8_mip_estimate_bytes,
        webgl_texture_count:renderer.info.memory.textures,
        glb_bytes:[...active].filter(([key])=>key.startsWith(`photo-${variant}:`)).reduce((sum,[,item])=>sum+item.bytes,0),
        screenshot:snapshot});
    }
    const width=samples[0].screenshot.width,height=samples[0].screenshot.height;
    const sheet=document.createElement('canvas');sheet.width=width*2;sheet.height=height+54;
    const context=sheet.getContext('2d');context.fillStyle='#102a34';context.fillRect(0,0,sheet.width,sheet.height);
    context.font='20px system-ui';context.fillStyle='#e8f4f0';
    for(let i=0;i<samples.length;i++){
      const sample=samples[i];context.fillText(
        `${i?'Original JPEG':'Low 512px'} / ${sample.average_fps.toFixed(1)} FPS / ${(sample.photo_rgba8_mip_estimate_bytes/1048576).toFixed(0)} MiB estimate`,
        i*width+15,34);
      context.drawImage(sample.screenshot,i*width,54);
    }
    const png=await new Promise(resolve=>sheet.toBlob(resolve,'image/png'));
    if(!png)throw new Error('比較PNGを作成できません');
    const report={schema:'therabby.geoengine.station-photo-compare.v0.2',recorded_at_utc:new Date().toISOString(),
      quality_mode:quality,view_mode:viewMode,width,height,pixel_ratio:renderer.getPixelRatio(),
      camera_position:camera.position.toArray(),camera_target:controls.target.toArray(),
      browser:navigator.userAgent,gpu:gpuInfo(),baseline_pc_verified:false,
      source:'Project PLATEAU / Fukushima City 2025',
      notes:'開発環境・同一視点の各3秒計測。GPU画像容量はRGBA8+mipの理論値で実割当量ではない。',
      samples:samples.map(({screenshot,...item})=>item)};
    for(const url of comparisonUrls)URL.revokeObjectURL(url);
    comparisonUrls=[URL.createObjectURL(png),URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}))];
    $('compare-image').src=comparisonUrls[0];$('compare-image').hidden=false;
    $('compare-save').href=comparisonUrls[0];$('compare-save').download='geoengine-station-photo-low-vs-source.png';$('compare-save').hidden=false;
    $('compare-json').href=comparisonUrls[1];$('compare-json').download='geoengine-station-photo-low-vs-source.json';$('compare-json').hidden=false;
    result.textContent=`同一視点: Low ${samples[0].average_fps.toFixed(1)} FPS / 元JPEG ${samples[1].average_fps.toFixed(1)} FPS。画像・計測JSONを保存できます。基準PCの合格判定ではありません。`;
  }finally{
    photoComparisonFrames=null;
    $('photo-detail').value=previousDetail;$('building-texture').checked=previousTexture;
    applyDebugDisplay();schedule(true);controls.enabled=true;button.disabled=false;
  }
}
function gpuInfo(){
  const gl=renderer.getContext(),extension=gl.getExtension('WEBGL_debug_renderer_info');
  return {vendor:extension?gl.getParameter(extension.UNMASKED_VENDOR_WEBGL):'unavailable',
    renderer:extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):'unavailable'};
}
function resizeRender(){
  const w=measure?1280:viewport.clientWidth,h=measure?720:viewport.clientHeight;
  if(!w||!h)return;
  camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);
}
function beginMeasurement(automatic=false){
  if(measure)return true;
  stopWalking();stationPhotoSharpUniform.value=0;
  quality='light';$('quality').value='light';renderer.setPixelRatio(1);
  $('photo-detail').value='auto';
  $('roads').checked=true;
  if(!tour&&!startTour())return false;
  $('app').classList.add('measurement');
  const target=benchmarkMode==='smoke'&&automatic?8:600;
  measure={start:performance.now(),target_s:target,automatic,frames:[],hiddenIntervals:0,hiddenSince:null,
    initialFailures:loadFailures,initialLoads:loadSuccess,initialUnloads:unloads};
  resizeRender();schedule(true);
  $('measure').textContent=`測定中 0:00 / ${target===600?'10:00':'0:08'}　終了して保存`;
  return true;
}
function maybeStartAutoBenchmark(){
  if(!autoBenchmark||autoBenchmarkStarted||measure)return;
  if(![...active.keys()].some(key=>key.startsWith('road:')))return;
  autoBenchmarkStarted=beginMeasurement(true);
}
function downloadMeasurement(data){
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  if(lastMeasurementUrl)URL.revokeObjectURL(lastMeasurementUrl);
  lastMeasurementUrl=URL.createObjectURL(blob);
  const link=$('redownload');link.href=lastMeasurementUrl;
  link.download=`geoengine-citywide-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;
  link.click();
}
function saveMeasurement(reason='stopped'){
  if(!measure)return;
  if(measure.hiddenSince!==null)measure.hiddenIntervals++;
  const frameSum=measure.frames.reduce((a,b)=>a+b,0);
  const duration=(performance.now()-measure.start)/1000;
  const data={schema:'therabby.geoengine.citywide-browser-measurement.v0.1',
    recorded_at_utc:new Date().toISOString(),duration_s:Math.round(duration*100)/100,
    target_duration_s:measure.target_s,automatic:measure.automatic,completion_reason:reason,
    width:renderer.domElement.width,height:renderer.domElement.height,pixel_ratio:renderer.getPixelRatio(),
    quality,view_mode:viewMode,station_lod2_enabled:photoEnabled,
    station_lod2_buildings_loaded:[...active].reduce((sum,[key,item])=>sum+(key.startsWith('photo-')?item.photoBuildings:0),0),
    user_agent:navigator.userAgent,gpu:gpuInfo(),
    baseline_resolution_match:renderer.domElement.width===1280&&renderer.domElement.height===720,
    hidden_intervals:measure.hiddenIntervals,frames:measure.frames.length,
    average_fps:frameSum?measure.frames.length*1000/frameSum:null,
    frame_ms_p95:percentile(measure.frames,.95),frame_ms_p99:percentile(measure.frames,.99),
    frame_ms_max:measure.frames.reduce((a,b)=>Math.max(a,b),0),frames_over_50ms:measure.frames.filter(v=>v>50).length,
    frames_over_100ms:measure.frames.filter(v=>v>100).length,
    frames_around_1000ms:measure.frames.filter(v=>v>=950&&v<=1050).length,
    suspected_browser_throttling:measure.frames.length>0&&
      measure.frames.filter(v=>v>=950&&v<=1050).length/measure.frames.length>.1,
    load_failures_delta:loadFailures-measure.initialFailures,
    loads_delta:loadSuccess-measure.initialLoads,unloads_delta:unloads-measure.initialUnloads,
    road_tour_distance_m:tour?.distance_m??null,road_tour_tile_crossings:tour?.seam_crossings??null,
    notes:'描画バッファは1280×720固定。GPU文字列だけでI-RIHA101本体を認証できないため、ホスト名は別途確認する。背面化はhidden_intervalsに記録。'};
  const validity={ten_minutes:data.target_duration_s===600&&duration>=600,
    completed:data.completion_reason==='completed',resolution:data.baseline_resolution_match&&data.pixel_ratio===1,
    light_quality:data.quality==='light',foreground:data.hidden_intervals===0,
    unthrottled:!data.suspected_browser_throttling,
    road_tour:Number.isFinite(data.road_tour_distance_m)&&data.road_tour_distance_m>0&&data.road_tour_tile_crossings>0,
    no_tile_errors:data.load_failures_delta===0};
  const valid=Object.values(validity).every(Boolean);
  const gpuMatchesTarget=/Intel.*UHD.*770/i.test(data.gpu.renderer);
  data.performance_gate={checks:validity,valid_measurement:valid,
    target_gpu_reported:gpuMatchesTarget,average_30fps_met:valid&&data.average_fps>=30,
    result:!valid?'invalid_or_incomplete':!gpuMatchesTarget?'non_baseline_gpu':
      data.average_fps>=30?'provisional_pass_on_reported_gpu':'fail_on_reported_gpu',
    baseline_host_verified:false,v1_0_acceptance_complete:false};
  lastMeasurement=data;
  $('benchmark-result').hidden=false;
  $('benchmark-result').textContent=`測定結果: ${data.performance_gate.result} / 平均 ${data.average_fps?.toFixed(1)??'—'} FPS / ${data.width}×${data.height} / ${data.duration_s.toFixed(1)}秒。端末の確認後に受入判定してください。`;
  $('redownload').hidden=false;
  $('measurement-json').hidden=false;
  $('measurement-json-text').value=JSON.stringify(lastMeasurement,null,2);
  downloadMeasurement(data);
  measure=null;stopTour();$('app').classList.remove('measurement');resizeRender();$('measure').textContent='10分測定を開始';
}
function updateStatus(now){
  if(now-lastStatus<500)return;lastStatus=now;
  const buildings=[...active].filter(([key])=>key.startsWith('building:'));
  const photo=[...active].filter(([key])=>key.startsWith('photo-'));
  const osmBuildings=[...active].filter(([key])=>key.startsWith('osmBuilding:'));
  const far=[...active].filter(([key])=>key.startsWith('far:'));
  const roads=[...active].filter(([key])=>key.startsWith('road:'));
  const terrain=[...active].filter(([key])=>key.startsWith('terrain:'));
  const loaded=[...active.values()].reduce((sum,item)=>sum+item.bytes,0);
  $('tile-count').textContent=`地形 ${terrain.length} / 公式建物 ${buildings.length}+写真${photo.length}+OSM補完${osmBuildings.length}+遠景${far.length} / 道路 ${roads.length}`;
  $('building-count').textContent=`公式 ${[...buildings,...photo].reduce((sum,[,item])=>sum+item.buildings,0).toLocaleString('ja-JP')}棟 / OSM補完 ${osmBuildings.reduce((sum,[,item])=>sum+item.buildings,0).toLocaleString('ja-JP')}棟 / 遠景 ${far.reduce((sum,[,item])=>sum+item.farCells,0).toLocaleString('ja-JP')}区画`;
  $('photo-count').textContent=`${photo.reduce((sum,[,item])=>sum+item.photoBuildings,0)} / ${manifests.photo?.lod2_buildings??0}棟`;
  $('road-count').textContent=roads.reduce((sum,[,item])=>sum+item.displayed,0).toLocaleString('ja-JP');
  $('load-stats').textContent=`${loadFailures}回 / ${(loaded/1048576).toFixed(1)} MiB`;
  const avg=frameTimes.length?frameTimes.reduce((a,b)=>a+b,0)/frameTimes.length:0;
  $('fps').textContent=avg?`${(1000/avg).toFixed(1)} / ${percentile(frameTimes,.95).toFixed(1)} ms`:'—';
  $('draws').textContent=`${renderer.info.render.calls} / ${renderer.info.render.triangles.toLocaleString('ja-JP')}`;
  const buffer=renderer.getDrawingBufferSize(new THREE.Vector2());
  $('buffer-size').textContent=`${buffer.x} × ${buffer.y} px`;
  $('gpu-texture-count').textContent=`${renderer.info.memory.textures}枚（容量不明）`;
  const variant=photo.some(([key])=>key.startsWith('photo-high:'))?'high':
    photo.some(([key])=>key.startsWith('photo-medium:'))?'medium':'low';
  const bytes=manifests.photo?.quality_variants?.[variant]?.rgba8_mip_estimate_bytes;
  $('texture-memory').textContent=photo.length&&bytes?`全域上限 約${(bytes/1048576).toFixed(0)} MiB`:'—';
  if(!$('status').classList.contains('error')){
    const missing=roads.reduce((sum,[,item])=>sum+item.unknown+item.structures,0);
    setStatus(`読込中 ${pending.size}件 / 表示 ${active.size}タイル / 累積読込 ${loadSuccess}件\n`+
      `道路の地表高欠損・橋/トンネル等 ${missing}線分は塗りません。地形がない場所は空白です。`+
      (tour?`\nOSM道路線を追従中 ${tour.distance_m.toFixed(0)}m / タイル境界 ${tour.seam_crossings}回。走行可否は未確認。`:''));
  }
  if(measure){const elapsed=(now-measure.start)/1000;
    const target=measure.target_s;
    $('measure').textContent=`測定中 ${Math.floor(elapsed/60)}:${String(Math.floor(elapsed%60)).padStart(2,'0')} / ${target===600?'10:00':'0:08'}　終了して保存`;
    $('measure-stop').textContent=$('measure').textContent;
    if(elapsed>=target)saveMeasurement('completed');
  }
}
function animate(now){
  requestAnimationFrame(animate);
  if(document.hidden){lastFrame=0;return;}
  const dt=lastFrame?now-lastFrame:0;lastFrame=now;
  if(dt>0&&!document.hidden){frameTimes.push(dt);if(frameTimes.length>300)frameTimes.shift();
    if(measure)measure.frames.push(dt);
    if(photoComparisonFrames)photoComparisonFrames.push(dt);}
  if(moveKeys.size&&!measure){
    if(tour)stopTour();
    const forward=new THREE.Vector3().subVectors(controls.target,camera.position);forward.y=0;forward.normalize();
    const right=new THREE.Vector3(-forward.z,0,forward.x);
    const movement=new THREE.Vector3();
    if(moveKeys.has('w'))movement.add(forward);if(moveKeys.has('s'))movement.sub(forward);
    if(moveKeys.has('d'))movement.add(right);if(moveKeys.has('a'))movement.sub(right);
    if(movement.lengthSq()){
      movement.normalize().multiplyScalar(Math.min(dt/1000,.1)*(walking?2.6:(viewMode==='ground'?9:65))*(moveKeys.has('shift')?(walking?1.35:3):1));
      if(walking)walkStep(movement);
      else {controls.target.add(movement);camera.position.add(movement);
        if(now-lastMoveAlign>350){lastMoveAlign=now;alignGround();}}
    }
  }
  advanceTour(dt/1000);if(!walking)controls.update();schedule();photoPilot?.update(now);renderer.render(scene,camera);updateStatus(now);
}
async function initialize(){
  try{
    await Promise.all(['building','osmBuilding','far','terrain','road'].map(fetchManifest));
    try{await fetchStationRoads();}
    catch(error){console.warn('駅東口のPLATEAU道路外形を読み込めません:',error);}
    if(initialStationPhoto||photoPilotMode||photoStreamMode){
      try{await fetchPhotoOverlay();$('station-photo').checked=true;photoEnabled=true;if(stationGroundMesh)stationGroundMesh.visible=true;}
      catch(error){console.warn(error);$('station-photo').parentElement.title=error.message;}
    }
    const response=await fetch(new URL('search_index.json',assetRoots.road));
    if(response.ok){const search=await response.json();
      if(search.schema==='therabby.geoengine.citywide-search.v0.1'&&search.projected_crs.includes('EPSG:6677')){
        manifests.search=search;
        $('road-names').replaceChildren(...search.entries.map(item=>{const option=document.createElement('option');option.value=item.name;return option;}));
      }}
    $('region').onchange=()=>{const [lat,lon]=presets[$('region').value];teleport(...projectFukushima(lat,lon));};
    $('go').onclick=doSearch;$('search').onkeydown=e=>{if(e.key==='Enter')doSearch();};
    $('overview').onclick=()=>setView('overview');$('ground').onclick=()=>setView('ground');
    $('walk').onclick=()=>{
      if(walking){stopWalking();return;}
      if(!manifests.photo||!photoEnabled){$('walk-status').textContent='駅東口の公式建物を表示してから開始してください。';return;}
      setView('ground');
      const area=manifests.photo.area,east=origin.east+camera.position.x,north=origin.north-camera.position.z;
      if(!insideWalkArea(area,east,north)){$('walk-status').textContent='駅前300m区域内へ移動してから開始してください。';return;}
      const terrain=[...active].filter(([key])=>key.startsWith('terrain:')).map(([,item])=>item.root);
      const ground=walkGroundAt(camera.position.x,camera.position.z,terrain);
      if(!ground){$('walk-status').textContent='地形を読み込み中です。少し待ってから開始してください。';return;}
      const buildings=[...active].filter(([key])=>key.startsWith('photo-')).map(([,item])=>item.root);
      if(!buildings.length){$('walk-status').textContent='駅前建物を読み込み中です。少し待ってから開始してください。';return;}
      if(findWalkInterior(buildings,new THREE.Vector3(camera.position.x,ground.point.y+1.6,camera.position.z),walkRay)){
        $('walk-status').textContent='開始地点が建物内です。地上表示で別の道路へ移動してください。';return;
      }
      const direction=new THREE.Vector3().subVectors(controls.target,camera.position).normalize();
      walkYaw=Math.atan2(-direction.x,-direction.z);walkPitch=0;walking=true;stationInspection=true;
      camera.position.y=ground.point.y+1.6;controls.enabled=false;walkLook();$('walk').textContent='歩行を終了';
    };
    $('walk').disabled=false;
    renderer.domElement.addEventListener('pointerdown',e=>{if(!walking||e.button!==0)return;walkDrag={x:e.clientX,y:e.clientY};renderer.domElement.setPointerCapture(e.pointerId);});
    renderer.domElement.addEventListener('pointermove',e=>{if(!walking||!walkDrag)return;
      walkYaw-=(e.clientX-walkDrag.x)*0.003;walkPitch=THREE.MathUtils.clamp(walkPitch-(e.clientY-walkDrag.y)*0.003,-1.45,1.45);
      walkDrag={x:e.clientX,y:e.clientY};walkLook();});
    renderer.domElement.addEventListener('pointerup',()=>{walkDrag=null;});
    renderer.domElement.addEventListener('pointercancel',()=>{walkDrag=null;});
    $('road-tour').onclick=()=>{stopWalking();if(tour)stopTour();else startTour();};
    $('compare-photo').onclick=()=>compareStationPhotos().catch(error=>{
      console.warn(error);$('compare-result').textContent=`比較に失敗しました: ${error.message}`;
    });
    const updateSharpness=()=>{stationPhotoSharpUniform.value=$('station-style').value==='sharp'&&quality!=='light'?Number($('station-sharpness').value):0;};
    $('quality').onchange=()=>{
      quality=$('quality').value;
      updateSharpness();
      renderer.setPixelRatio(quality==='light'?1:Math.min(devicePixelRatio,quality==='high'?2:1.5));
      const anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),quality==='high'?8:quality==='standard'?4:2);
      for(const [key,item] of active)if(key.startsWith('road:'))item.root.traverse(object=>{
        const map=object.material?.userData?.asphaltMap;
        if(map){map.anisotropy=anisotropy;map.needsUpdate=true;}
      });
      schedule(true);
    };
    $('photo-detail').onchange=()=>schedule(true);
    $('station-style').onchange=()=>{stationStyleUniform.value=$('station-style').value==='clean'?1:0;updateSharpness();applyDebugDisplay();};
    $('station-sharpness').oninput=updateSharpness;
    $('photo-anisotropy').onchange=updatePhotoSampling;
    $('photo-filter').onchange=updatePhotoSampling;
    $('station-photo').onchange=async()=>{
      if(!$('station-photo').checked)stopWalking();
      if($('station-photo').checked&&!manifests.photo){
        try{await fetchPhotoOverlay();}
        catch(error){$('station-photo').checked=false;setStatus(`駅東口LOD2を読み込めません: ${error.message}`,true);return;}
      }
      photoEnabled=$('station-photo').checked;if(stationGroundMesh)stationGroundMesh.visible=photoEnabled;schedule(true);
    };
    $('roads').onchange=()=>{applyDebugDisplay();schedule(true);};
    for(const id of ['building-texture','building-lod','road-polygon','road-surface','road-centerline','road-height','road-guides'])
      $(id).onchange=applyDebugDisplay;
    $('measure').onclick=()=>{if(measure)saveMeasurement('stopped');else beginMeasurement(false);};
    $('measure-stop').onclick=()=>saveMeasurement('stopped');
    document.addEventListener('visibilitychange',()=>{
      if(!measure)return;
      if(document.hidden)measure.hiddenSince=performance.now();
      else if(measure.hiddenSince!==null){measure.hiddenIntervals++;measure.hiddenSince=null;lastFrame=0;}
    });
    addEventListener('keydown',e=>{
      if(e.target instanceof HTMLInputElement||e.target instanceof HTMLSelectElement)return;
      if(walking&&e.key==='Shift'){moveKeys.add('shift');return;}
      if(['w','a','s','d'].includes(e.key.toLowerCase())){e.preventDefault();moveKeys.add(e.key.toLowerCase());if(e.shiftKey)moveKeys.add('shift');return;}
      if(walking)return;
      const delta={ArrowLeft:[-150,0],ArrowRight:[150,0],ArrowUp:[0,-150],ArrowDown:[0,150]}[e.key];
      if(!delta)return;e.preventDefault();
      const move=new THREE.Vector3(delta[0],0,delta[1]);controls.target.add(move);camera.position.add(move);
      schedule(true);alignGround();
    });
    addEventListener('keyup',e=>{moveKeys.delete(e.key.toLowerCase());if(e.key==='Shift')moveKeys.delete('shift');});
    addEventListener('blur',()=>moveKeys.clear());
    new ResizeObserver(resizeRender).observe(viewport);
    teleport(...projectFukushima(...(photoEnabled?[manifests.photo.area.center_lat,manifests.photo.area.center_lon]:presets.station)));
    if(photoPilotMode||photoStreamMode){
      $('photo-detail').value='low';$('photo-detail').disabled=true;$('quality').disabled=!photoStreamFull;$('compare-photo').disabled=!photoStreamMode||photoStreamFull;
      if(photoStreamMode){
        const {createPhotoStream}=await import('./geoengine-photo-stream.js');
        photoPilot=await createPhotoStream({scene,camera,controls,renderer,active,origin,full:photoStreamFull,beforeCameraMove:()=>{stopWalking();stopTour();}});
        if(photoStreamFull){$('station-style').value='photo';$('station-style').onchange();
          $('photo-detail').querySelector('option[value="low"]').textContent='遠方Low・近距離元JPEG（自動）';
          $('quality').value='standard';$('quality').dispatchEvent(new Event('change'));}
      }else{
        const {createPhotoPilot}=await import('./geoengine-photo-pilot.js');
        photoPilot=await createPhotoPilot({scene,camera,controls,renderer,active,origin});
      }
    }
    setStatus(`目録を読み込みました。公式建物 ${manifests.building.tiles.length}、OSM補完建物 ${manifests.osmBuilding.tiles.length}、遠景 ${manifests.far.tiles.length}、地形 ${manifests.terrain.tiles.length}、道路 ${manifests.road.tiles.length} タイル。`);
    requestAnimationFrame(animate);
    maybeStartAutoBenchmark();
  }catch(error){console.error(error);setStatus(`初期化に失敗しました: ${error.message}`,true);}
}
initialize();
