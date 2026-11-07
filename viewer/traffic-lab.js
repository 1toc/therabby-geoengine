import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {CitywideRoadProvider,projectFukushima} from './geoengine-citywide-api.js';
import {buildTrafficGraph,makeSyntheticTrafficTiles} from './geoengine-traffic-graph.mjs';
import {chooseElevationReference,loadCityAssets,disposeCityAssets} from './geoengine-traffic-city.mjs';

const $=id=>document.getElementById(id);
const viewport=$('viewport');
const scene=new THREE.Scene();
scene.background=new THREE.Color(0xbdd4db);
scene.fog=new THREE.Fog(0xbdd4db,450,1100);
const renderer=new THREE.WebGLRenderer({antialias:false,powerPreference:'low-power'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.25));
renderer.setSize(Math.max(1,viewport.clientWidth),Math.max(1,viewport.clientHeight));
renderer.outputColorSpace=THREE.SRGBColorSpace;
viewport.prepend(renderer.domElement);
const camera=new THREE.PerspectiveCamera(56,1,.5,1200);
camera.position.set(170,205,230);
const controls=new OrbitControls(camera,renderer.domElement);
controls.minDistance=12;controls.maxDistance=700;controls.maxPolarAngle=Math.PI*.48;
controls.enableDamping=true;controls.target.set(0,0,0);controls.update();
scene.add(new THREE.HemisphereLight(0xf0faff,0x667870,2.2));
const sun=new THREE.DirectionalLight(0xffefcf,1.5);sun.position.set(-70,150,-70);scene.add(sun);
const root=new THREE.Group();scene.add(root);
const ground=new THREE.Mesh(new THREE.PlaneGeometry(900,900),new THREE.MeshLambertMaterial({color:0x8faea3,side:THREE.DoubleSide}));
ground.rotation.x=-Math.PI/2;ground.position.y=-.025;root.add(ground);
const materialRoad=new THREE.MeshLambertMaterial({color:0x394952});
const materialFoot=new THREE.MeshLambertMaterial({color:0xc6bbb0});
const materialOther=new THREE.MeshLambertMaterial({color:0x909997});
const lineMaterial=new THREE.LineBasicMaterial({color:0xf2cd78,transparent:true,opacity:.72});
const agents=[];let graph=null,paused=false,currentMode='demo',loading=false,centerInfo='';
let guideLines=null,frameCounter=0,fps=0,fpsElapsed=0,lastStats=0;
let cityEnabled=false,cityLayer=null,cityStats=null,cityAbort=null,cityGeneration=0;
let realTiles=null,realCenter=null,referenceAltitude=null;
function roadY(height,offset=.22){
  return cityEnabled&&Number.isFinite(height)?height-referenceAltitude+offset:offset;
}
function removeCity(){
  cityGeneration++;
  cityAbort?.abort();cityAbort=null;
  disposeCityAssets(cityLayer);cityLayer=null;
  cityEnabled=false;cityStats=null;referenceAltitude=null;
  ground.visible=true;
}
const clock=new THREE.Clock();
function setStatus(value){$('status').textContent=value;}
function disposeMesh(object) {
  if(object.geometry)object.geometry.dispose();
  if(object.material&&!([materialRoad,materialFoot,materialOther,lineMaterial].includes(object.material)))
    object.material.dispose();
}
function clearWorld() {
  for(const obj of [...root.children])if(obj!==ground){
    root.remove(obj);obj.traverse(disposeMesh);
  }
  guideLines=null;agents.length=0;
}
// Batch all road ribbons of each type into one mesh (three draw calls, not one per edge).
function roadBatch(segments,kind,material) {
  const positions=[],normals=[];
  const triangle=(p,q,r)=>{
    for(const [x,y,z] of [p,q,r]){positions.push(x,y,z);normals.push(0,1,0);}
  };
  for(const s of segments) {
    if(s.kind!==kind)continue;
    if(cityEnabled&&(!Number.isFinite(s.groundFromTp)||!Number.isFinite(s.groundToTp)))continue;
    const dx=s.b[0]-s.a[0],dz=s.b[1]-s.a[1];
    const half=(kind==='footpath'?Math.min(3,s.width_m):s.width_m)/2;
    const nx=-dz/s.length*half,nz=dx/s.length*half;
    const pieces=cityEnabled?Math.max(1,Math.min(12,Math.ceil(s.length/10))):1;
    for(let j=0;j<pieces;j++){
      const t0=j/pieces,t1=(j+1)/pieces;
      const at=t=>[s.a[0]+dx*t,s.a[1]+dz*t];
      const p=at(t0),q=at(t1);
      const h0=cityEnabled?roadY(s.groundFromTp+(s.groundToTp-s.groundFromTp)*t0):.04;
      const h1=cityEnabled?roadY(s.groundFromTp+(s.groundToTp-s.groundFromTp)*t1):.04;
      const a=[p[0]+nx,h0,p[1]+nz],b=[q[0]+nx,h1,q[1]+nz];
      const c=[p[0]-nx,h0,p[1]-nz],d=[q[0]-nx,h1,q[1]-nz];
      triangle(a,b,c);triangle(b,d,c);
    }
  }
  if(!positions.length)return null;
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));
  return new THREE.Mesh(geometry,material);
}
function actorMesh(mode,index) {
  if(mode==='vehicle') {
    const g=new THREE.Group();
    const shell=new THREE.Mesh(new THREE.BoxGeometry(2,1.15,3.8),new THREE.MeshLambertMaterial({
      color:[0x307bad,0xdb6642,0xb8a641,0x638f66][index%4]}));
    shell.position.y=.7;g.add(shell);
    const roof=new THREE.Mesh(new THREE.BoxGeometry(1.7,.5,1.8),new THREE.MeshLambertMaterial({color:0xd3e6e9}));
    roof.position.set(0,1.5,.0);g.add(roof);
    return g;
  }
  const g=new THREE.Group();
  const body=new THREE.Mesh(new THREE.CylinderGeometry(.27,.34,1.1,7),
    new THREE.MeshLambertMaterial({color:0x286f78}));
  body.position.y=.77;g.add(body);
  const head=new THREE.Mesh(new THREE.SphereGeometry(.29,10,7),new THREE.MeshLambertMaterial({color:0xe9c399}));
  head.position.y=1.55;g.add(head);
  return g;
}
function chooseNextArc(mode,atNode,previousEdge,seed) {
  const options=(graph?.adjacency[mode].get(atNode)||[]).filter(a=>
    !cityEnabled||(Number.isFinite(a.groundFromTp)&&Number.isFinite(a.groundToTp)));
  if(!options.length)return null;
  const forward=options.filter(item=>item.edgeId!==previousEdge);
  const candidates=forward.length?forward:options;
  return candidates[seed%candidates.length];
}
function createAgents() {
  for(const actor of agents){root.remove(actor.mesh);actor.mesh.traverse(disposeMesh);}
  agents.length=0;
  for(const [mode,max,speed] of [['vehicle',4,8],['pedestrian',3,1.35]]) {
    const pool=[...graph.adjacency[mode].values()].flat().filter(a=>
      a.length>2 && Math.hypot((a.a[0]+a.b[0])/2,(a.a[1]+a.b[1])/2)<210 &&
      (!cityEnabled||(Number.isFinite(a.groundFromTp)&&Number.isFinite(a.groundToTp))));
    // Spread initial positions over distinct OSM segments. Do not spawn on missing footways.
    const chosen=[];const chosenSegments=new Set();
    for(const arc of pool.sort((a,b)=>b.length-a.length)) {
      if(chosenSegments.has(arc.edgeId))continue;
      chosen.push(arc);chosenSegments.add(arc.edgeId);
      if(chosen.length===max)break;
    }
    for(let i=0;i<chosen.length;i++){
      const arc=chosen[i],mesh=actorMesh(mode,i);
      root.add(mesh);
      agents.push({mode,arc,mesh,distance:Math.min(arc.length*.7,(i+.25)*arc.length/(max+1)),
        speed,seed:i+3,stopped:false});
    }
  }
  for(const actor of agents)placeAgent(actor);
}
function placeAgent(actor){
  const t=Math.max(0,Math.min(1,actor.distance/actor.arc.length));
  const a=actor.arc.a,b=actor.arc.b;
  const tp=Number.isFinite(actor.arc.groundFromTp)&&Number.isFinite(actor.arc.groundToTp)
    ?actor.arc.groundFromTp+(actor.arc.groundToTp-actor.arc.groundFromTp)*t:null;
  actor.mesh.position.set(a[0]+(b[0]-a[0])*t,cityEnabled?roadY(tp,.28):.08,a[1]+(b[1]-a[1])*t);
  actor.mesh.rotation.y=Math.atan2(b[0]-a[0],b[1]-a[1]);
}
function advance(dt){
  for(const actor of agents) {
    if(actor.stopped)continue;
    actor.distance+=dt*actor.speed;
    let turns=0;
    while(actor.distance>=actor.arc.length&&turns++<8) {
      actor.distance-=actor.arc.length;
      const next=chooseNextArc(actor.mode,actor.arc.to,actor.arc.edgeId,++actor.seed);
      if(!next) {actor.stopped=true;actor.distance=actor.arc.length;break;}
      actor.arc=next;
    }
    if(turns>=8)actor.distance=0;
    placeAgent(actor);
  }
}
function renderGraph(next,mode){
  graph=next;currentMode=mode;clearWorld();
  const positions=[];
  for(const [kind,material] of [['road',materialRoad],['footpath',materialFoot],['other',materialOther]]) {
    const batch=roadBatch(graph.segments,kind,material);if(batch)root.add(batch);
  }
  for(const segment of graph.segments) {
    if(cityEnabled&&(!Number.isFinite(segment.groundFromTp)||!Number.isFinite(segment.groundToTp)))continue;
    const y0=cityEnabled?roadY(segment.groundFromTp,.36):.105;
    const y1=cityEnabled?roadY(segment.groundToTp,.36):.105;
    positions.push(segment.a[0],y0,segment.a[1],segment.b[0],y1,segment.b[1]);
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  guideLines=new THREE.LineSegments(geometry,lineMaterial);
  guideLines.visible=$('show-lines').checked;root.add(guideLines);
  createAgents();
  const bounding=Math.min(400,Math.max(150,graph.segments.reduce((acc,s)=>{
    return Math.max(acc,Math.abs(s.a[0]),Math.abs(s.a[1]),Math.abs(s.b[0]),Math.abs(s.b[1]));
  },0)));
  const distance=mode==='demo'?220:Math.min(360,bounding*1.05);
  camera.position.set(distance*.70,distance*.88,distance);
  controls.target.set(0,0,0);controls.update();
  ground.visible=!cityEnabled;
  $('mode-label').textContent=mode==='demo'?'架空の試験データ':
    cityEnabled?'福島市 PLATEAU＋DEM5A＋OSM（試作）':'福島市 OSM道路（位置概略）';
  const vehicle=agents.filter(a=>a.mode==='vehicle').length;
  const pedestrians=agents.filter(a=>a.mode==='pedestrian').length;
  setStatus((mode==='demo'?'【架空デモ】実在の福島市を表していません。':'【実OSM道路】福島駅周辺の中心線データを使用。')+
    '\n' + graph.segments.length+'線分を表示、車両'+vehicle+'台、歩行者'+pedestrians+'人。'+
    '\n高さ・車線・信号・通行可能性・衝突は未検証。');
  updateStats(true);
}
function updateStats(force=false) {
  const now=performance.now();
  if(!force&&now-lastStats<500)return;
  lastStats=now;
  if(!graph)return;
  $('stats').textContent='モード: '+(currentMode==='demo'?'架空':'OSM実道路')+
    '\n線分: '+graph.segments.length+
    '\n車両: '+agents.filter(a=>a.mode==='vehicle').length+
    '\n歩行者: '+agents.filter(a=>a.mode==='pedestrian').length+
    '\n推定幅の線分: '+graph.counts.estimated_width+
    '\n未採用/範囲外: '+(graph.counts.bad+graph.counts.far)+
    '\n3D建物・地形: '+(cityEnabled?'表示中':'非表示')+
    (cityStats?' / PLATEAU '+cityStats.building+'/'+cityStats.building_expected+
      ' / DEM '+cityStats.terrain+'/'+cityStats.terrain_expected:'')+
    '\n描画負荷（draw calls）: '+renderer.info.render.calls+
    '\nFPS（参考）: '+fps+
    '\n状態: '+(paused?'停止中':'再生中')+
    '\n精度: '+(cityEnabled?'DEM5A地表高による推定表示':'2D概略')+' / 非臨床';
}
function displayDemo() {
  removeCity();
  realTiles=null;realCenter=null;
  $('city-3d').disabled=true;
  $('city-status').textContent='架空デモ：実際の建物・地形は読み込みません。';
  const next=buildTrafficGraph(makeSyntheticTrafficTiles(),55500,194500,280);
  renderGraph(next,'demo');
}
// Fetch must be invoked as a function, not as an unbound Window method through provider.fetcher.
// The wrapper keeps browser-native fetch's required global receiver while preserving API defaults.
const provider=new CitywideRoadProvider(undefined, (...args)=>globalThis.fetch(...args));
async function displayReal() {
  if(loading)return;
  loading=true;$('use-real').disabled=true;
  setStatus('福島市の道路タイルを読み込んでいます…');
  try {
    await provider.loadMap();
    const [east,north]=projectFukushima(37.7548,140.4597);
    const tx=Math.floor(east/1000),ty=Math.floor(north/1000);
    const ids=[];
    for(let x=tx-1;x<=tx+1;x++)for(let y=ty-1;y<=ty+1;y++)ids.push(x+'_'+y);
    const loaded=await Promise.all(ids.map(id=>provider.loadTile(id)));
    const tiles=loaded.filter(Boolean);
    if(!tiles.length)throw new Error('福島駅付近に道路タイルがありません');
    const next=buildTrafficGraph(tiles,east,north,280);
    if(!next.segments.length)throw new Error('指定範囲の道路線分がありません');
    removeCity();realTiles=tiles;realCenter={east,north};
    $('city-3d').disabled=false;
    renderGraph(next,'real');
    if($('city-3d').checked)await enableCity();
  }catch(error){
    setStatus('実データを開けませんでした。架空デモを表示したままにしています。\n'+
      String(error?.message||error)+'\n開発PCの data/derived/ を確認してください。');
  }finally {
    loading=false;$('use-real').disabled=false;
  }
}
async function enableCity(){
  if(currentMode!=='real'||!realTiles||!realCenter)return;
  const token=++cityGeneration;
  cityAbort?.abort();
  const controller=new AbortController();cityAbort=controller;
  $('city-status').textContent='PLATEAU建物・DEM5A地形を読み込み中…（最大18タイル）';
  const groundRef=chooseElevationReference(realTiles,realCenter.east,realCenter.north);
  if(!groundRef){
    $('city-status').textContent='近隣のDEM地表高がありません。高さを推測しないため2Dのままです。';
    $('city-3d').checked=false;
    return;
  }
  try {
    const {group,stats,referenceHeight}=await loadCityAssets({
      THREE,GLTFLoader,centerEast:realCenter.east,centerNorth:realCenter.north,
      referenceHeight:groundRef.height_tp_m,signal:controller.signal
    });
    if(token!==cityGeneration||currentMode!=='real'||!$('city-3d').checked){
      disposeCityAssets(group);return;
    }
    disposeCityAssets(cityLayer);
    cityLayer=group;scene.add(group);cityEnabled=true;
    cityStats=stats;referenceAltitude=referenceHeight;
    renderGraph(graph,'real');
    $('city-status').textContent='公式建物 '+stats.building+'/'+stats.building_expected+
      'タイル、DEM5A地形 '+stats.terrain+'/'+stats.terrain_expected+'タイル。'+
      '\n基準標高 '+referenceHeight.toFixed(2)+'m T.P.／道路・車両はDEM地表高に概略追従。'+
      (stats.errors.length?'\n未読込: '+stats.errors.slice(0,3).join(' / '):'');
  }catch(error){
    if(error.name==='AbortError'||token!==cityGeneration)return;
    $('city-3d').checked=false;
    removeCity();renderGraph(graph,'real');
    $('city-status').textContent='3D地形・建物は読み込めませんでした。2D道路表示は維持します。\n'+
      error.message+'\nローカルの data/derived/...-glb/tileset.json を確認してください。';
  }
}
function disableCity(){
  removeCity();
  if(currentMode==='real'&&graph)renderGraph(graph,'real');
  $('city-status').textContent='3D表示はオフです。';
}
function resize() {
  const w=Math.max(1,viewport.clientWidth),h=Math.max(1,viewport.clientHeight);
  renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
}
$('use-demo').addEventListener('click',displayDemo);
$('use-real').addEventListener('click',displayReal);
$('show-lines').addEventListener('change',()=>{if(guideLines)guideLines.visible=$('show-lines').checked;});
$('city-3d').addEventListener('change',()=>{$('city-3d').checked?enableCity():disableCity();});
$('pause').addEventListener('click',()=>{
  paused=!paused;$('pause').textContent=paused?'再開':'一時停止';updateStats(true);
});
$('reset').addEventListener('click',()=>{if(graph)createAgents();});
window.addEventListener('resize',resize);
function animate(){
  requestAnimationFrame(animate);
  const dt=Math.min(clock.getDelta(),.06);
  if(!paused&&graph)advance(dt);
  controls.update();
  renderer.render(scene,camera);
  fpsElapsed+=dt;frameCounter++;
  if(fpsElapsed>=1){fps=Math.round(frameCounter/fpsElapsed);fpsElapsed=0;frameCounter=0;}
  updateStats();
}
resize();displayDemo();animate();
