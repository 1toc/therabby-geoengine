import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoadTileProvider } from './geoengine-road-api.js';

const $ = id => document.getElementById(id);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9eb9c3);
scene.fog = new THREE.Fog(0x9eb9c3, 550, 1250);
const camera = new THREE.PerspectiveCamera(52, 1280/720, .1, 1800);
const renderer = new THREE.WebGLRenderer({antialias:true,powerPreference:'default'});
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setPixelRatio(1);
renderer.setSize(1280,720,false);
$('viewport').appendChild(renderer.domElement);
const controls = new OrbitControls(camera,renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI*.69;
scene.add(new THREE.HemisphereLight(0xf2f8ff,0x61787a,2.6));
const sun = new THREE.DirectionalLight(0xffe8ce,2.2);
sun.position.set(-220,300,160);
scene.add(sun);
const backdrop = new THREE.Mesh(new THREE.PlaneGeometry(1600,1600),
  new THREE.MeshLambertMaterial({color:0x8fa58e}));
backdrop.rotation.x=-Math.PI/2;
backdrop.position.y=-15;
scene.add(backdrop);

let size=250, base='', manifest=null, route=null, tour=null, benchmark=null;
let roadProvider=null;
let desired=new Set(), velocity=[0,0], lastTarget=null, lastFrame=0, lastSchedule=0, lastStatus=0;
let loadCount=0, unloadCount=0, failCount=0, transferred=0;
let frameTimes=[], coreLow=null, coreHigh=null, coreLoading=false, coreWanted=false, overview=null;
let generation=0;
const active=new Map(), inFlight=new Map(), ttl=new Map();
const loader=new GLTFLoader();
const cameraOffset=new THREE.Vector3(-34,44,36);
const resetOffset=new THREE.Vector3(-105,125,145);
const driveForward=new THREE.Vector3(1,0,0);

function nearestStartIndex() {
  return route.points.reduce((best,point,i)=>
    point[0]**2+point[1]**2<route.points[best][0]**2+route.points[best][1]**2?i:best,0);
}

function drivePose(x,z,dx,dz,dt=0) {
  const length=Math.hypot(dx,dz)||1;
  const direction=new THREE.Vector3(dx/length,0,dz/length);
  if(dt)driveForward.lerp(direction,Math.min(1,dt*5)).normalize();
  else driveForward.copy(direction);
  const ground=roadProvider?.terrainHeightAt(x,z)?.height_m??0;
  const aheadX=x+driveForward.x*35,aheadZ=z+driveForward.z*35;
  const aheadGround=roadProvider?.terrainHeightAt(aheadX,aheadZ)?.height_m??ground;
  controls.target.set(x,ground+1.6,z);
  camera.position.set(x,ground+1.6,z);
  camera.lookAt(aheadX,aheadGround+1.45,aheadZ);
}

function dispose(root) {
  scene.remove(root);
  const geometries=new Set(), materials=new Set(), textures=new Set();
  root.traverse(obj=>{
    if(obj.geometry)geometries.add(obj.geometry);
    for(const mat of (Array.isArray(obj.material)?obj.material:obj.material?[obj.material]:[])) {
      materials.add(mat);
      for(const value of Object.values(mat))if(value?.isTexture)textures.add(value);
    }
  });
  textures.forEach(tex=>{tex.dispose();if(typeof tex.image?.close==='function')tex.image.close();});
  materials.forEach(mat=>mat.dispose());
  geometries.forEach(geom=>geom.dispose());
  renderer.renderLists.dispose();
}

function currentTile(x,z) {
  return manifest?.tiles.find(tile=>x>=tile.bounds[0]&&x<tile.bounds[2]&&
                                   z>=tile.bounds[1]&&z<tile.bounds[3]);
}

function setFocus(x,z) {
  const shift=new THREE.Vector3(x-controls.target.x,0,z-controls.target.z);
  controls.target.add(shift);camera.position.add(shift);controls.update();
}

function reset() {
  tour=null;
  if($('view-mode').value==='drive'&&route) {
    const index=nearestStartIndex();
    const a=route.points[index],b=route.points[Math.min(index+1,route.points.length-1)];
    drivePose(a[0],a[1],b[0]-a[0],b[1]-a[1]);
  } else {
    controls.target.set(0,7,0);
    camera.position.copy(controls.target).add(resetOffset);
    controls.update();
  }
  velocity=[0,0];schedule(performance.now());
}

function routeStep(dt) {
  if(!tour||!route)return;
  let remaining=dt*12;
  while(remaining>0) {
    const next=tour.index+tour.direction;
    if(next<0||next>=route.points.length){tour.direction*=-1;continue;}
    const a=route.points[tour.index],b=route.points[next];
    const length=Math.hypot(b[0]-a[0],b[1]-a[1]);
    if(length<.001){tour.index=next;tour.distance=0;continue;}
    const travel=Math.min(remaining,length-tour.distance);
    tour.distance+=travel;remaining-=travel;
    const t=tour.distance/length;
    const x=a[0]+(b[0]-a[0])*t,z=a[1]+(b[1]-a[1])*t;
    if($('view-mode').value==='drive')drivePose(x,z,b[0]-a[0],b[1]-a[1],dt);
    else {
      controls.target.set(x,7,z);
      camera.position.copy(controls.target).add(cameraOffset);
      camera.lookAt(controls.target);
    }
    velocity=[(b[0]-a[0])/length*12,(b[1]-a[1])/length*12];
    if(tour.distance>=length-1e-6){tour.index=next;tour.distance=0;}
  }
}

async function loadModel(url) {
  const response=await fetch(url);
  if(!response.ok)throw new Error(`HTTP ${response.status}: ${url}`);
  const bytes=await response.arrayBuffer();
  const gltf=await loader.parseAsync(bytes,url.slice(0,url.lastIndexOf('/')+1));
  transferred+=bytes.byteLength;
  return {root:gltf.scene,bytes:bytes.byteLength};
}

async function loadCoreLow(token) {
  try {
    const model=await loadModel(base+manifest.core_low_model);
    if(token!==generation){dispose(model.root);return;}
    coreLow=model;scene.add(model.root);
    model.root.visible=!coreHigh;
    updateStatus(performance.now());
  } catch(error) {failCount++;$('state').textContent=`中心軽量モデル読込失敗: ${error.message}`;console.error(error);}
}

async function loadCoreHigh(token) {
  if(coreHigh||coreLoading)return;
  coreLoading=true;
  try {
    const model=await loadModel(base+manifest.core_model);
    if(token!==generation||!coreWanted){dispose(model.root);return;}
    model.root.position.y=.025;
    coreHigh=model;scene.add(model.root);
    if(coreLow)coreLow.root.visible=false;
    loadCount++;
  } catch(error) {failCount++;$('state').textContent=`中心高精細モデル読込失敗: ${error.message}`;console.error(error);}
  finally {coreLoading=false;updateStatus(performance.now());}
}

async function loadTile(tile,token) {
  if(active.has(tile.id)||inFlight.has(tile.id))return;
  const controller=new AbortController();inFlight.set(tile.id,controller);
  try {
    const response=await fetch(base+tile.glb,{signal:controller.signal});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const bytes=await response.arrayBuffer();
    const gltf=await loader.parseAsync(bytes,base);
    if(token!==generation||!desired.has(tile.id)){dispose(gltf.scene);return;}
    scene.add(gltf.scene);active.set(tile.id,{root:gltf.scene,bytes:bytes.byteLength});
    loadCount++;transferred+=bytes.byteLength;ttl.delete(tile.id);
  } catch(error) {
    if(error.name!=='AbortError'){failCount++;$('state').textContent=`${tile.id} 読込失敗: ${error.message}`;console.error(error);}
  } finally {inFlight.delete(tile.id);updateStatus(performance.now());}
}

function distanceToRect(x,z,[x0,z0,x1,z1]) {
  return Math.hypot(Math.max(x0-x,0,x-x1),Math.max(z0-z,0,z-z1));
}

function schedule(now) {
  if(!manifest)return;
  const x=controls.target.x,z=controls.target.z;
  const distance=camera.position.distanceTo(controls.target);
  const radius=Math.min(700,Math.max(size,distance*1.8));
  const candidates=manifest.tiles.filter(tile=>distanceToRect(x,z,tile.bounds)<radius);
  const ahead=[x+velocity[0]*3,z+velocity[1]*3];
  const aheadTile=currentTile(...ahead);
  if(aheadTile&&!candidates.includes(aheadTile))candidates.push(aheadTile);
  desired=new Set(candidates.map(tile=>tile.id));
  for(const [id,controller] of inFlight)if(!desired.has(id))controller.abort();
  candidates.sort((a,b)=>distanceToRect(x,z,a.bounds)-distanceToRect(x,z,b.bounds));
  for(const tile of candidates) {
    if(inFlight.size>=5)break;
    if(!active.has(tile.id)&&!inFlight.has(tile.id))loadTile(tile,generation);
  }
  for(const [id,item] of active) {
    if(desired.has(id)){ttl.delete(id);continue;}
    if(!ttl.has(id))ttl.set(id,now+1800);
    if(now>=ttl.get(id)){dispose(item.root);active.delete(id);ttl.delete(id);unloadCount++;}
  }
  coreWanted=$('quality').value==='high'&&distanceToRect(0,0,[x-radius,z-radius,x+radius,z+radius])<130;
  if(coreWanted)loadCoreHigh(generation);
  else if(coreHigh) {
    if(coreLow)coreLow.root.visible=true;
    dispose(coreHigh.root);coreHigh=null;unloadCount++;
  }
  updateStatus(now);
}

function percentile(values,p) {
  if(!values.length)return 0;
  const sorted=[...values].sort((a,b)=>a-b);
  return sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*p)-1)];
}

function updateStatus(now) {
  if(!manifest||now-lastStatus<200)return;
  const tile=currentTile(controls.target.x,controls.target.z);
  $('tiles').innerHTML=manifest.tiles.map(t=>{
    const status=active.has(t.id)?'loaded':inFlight.has(t.id)?'loading':'';
    return `<span class="tile ${status} ${tile?.id===t.id?'current':''}">${t.id}</span>`;
  }).join('');
  const bytes=[...active.values()].reduce((sum,item)=>sum+item.bytes,0)+(coreLow?.bytes??0)+(coreHigh?.bytes??0);
  $('state').textContent=`視点 ${$('view-mode').value==='drive'?'道路':'俯瞰'} / 地点 X ${controls.target.x.toFixed(0)} m / Z ${controls.target.z.toFixed(0)} m\n`+
    `タイル ${tile?.id??'区域外'} / 表示 ${active.size} / 読込中 ${inFlight.size} / 中心 ${coreHigh?'高精細':coreLow?'軽量':'読込中'}\n`+
    `読込 ${loadCount} / 解放 ${unloadCount} / 失敗 ${failCount} / 表示GLB ${(bytes/1048576).toFixed(1)} MiB`;
  lastStatus=now;
}

function downloadBenchmark(partial=false) {
  if(!benchmark)return;
  const elapsed=performance.now()-benchmark.start;
  const frames=benchmark.frames;
  const gl=renderer.getContext();
  const debugRenderer=gl.getExtension('WEBGL_debug_renderer_info');
  const report={schema:'therabby.geoengine.benchmark.v0.1',timestamp:new Date().toISOString(),
    tile_size_m:size,quality:$('quality').value,partial,duration_s:Math.round(elapsed/1000),
    drawing_buffer:[renderer.domElement.width,renderer.domElement.height],
    user_agent:navigator.userAgent,renderer:gl.getParameter(gl.RENDERER),
    unmasked_renderer:debugRenderer?gl.getParameter(debugRenderer.UNMASKED_RENDERER_WEBGL):null,
    hidden_frames:benchmark.hiddenFrames,
    valid_for_comparison:!partial&&benchmark.hiddenFrames===0&&frames.length>0,
    route_length_m:route.length_m,frames:frames.length,
    mean_fps:frames.length?+(1000*frames.length/frames.reduce((sum,v)=>sum+v,0)).toFixed(2):0,
    frame_p95_ms:+percentile(frames,.95).toFixed(2),frame_p99_ms:+percentile(frames,.99).toFixed(2),
    over_100ms:frames.filter(v=>v>100).length,
    max_frame_ms:frames.reduce((max,v)=>Math.max(max,v),0),
    peak_loaded_glb_bytes:benchmark.peakBytes,peak_webgl_textures:benchmark.peakTextures,
    peak_draw_calls:benchmark.peakCalls,loads:loadCount-benchmark.loads,
    unloads:unloadCount-benchmark.unloads,failures:failCount-benchmark.failures,
    transferred_bytes:transferred-benchmark.transferred,
    note:'GLB bytes and WebGL texture count are not GPU memory measurements. Verify separately on Intel UHD 770 target PC.'};
  const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;
  link.download=`geoengine-1km-${size}m-${Math.round(elapsed/1000)}s.json`;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  $('benchmark-state').textContent=`計測保存: ${report.duration_s}秒 / 平均 ${report.mean_fps} FPS / p95 ${report.frame_p95_ms} ms`;
  benchmark=null;
}

function animate(now) {
  requestAnimationFrame(animate);
  const dt=lastFrame?Math.min((now-lastFrame)/1000,.1):0;
  if(lastFrame) {
    const ms=now-lastFrame;
    if(ms<1000){frameTimes.push(ms);if(frameTimes.length>180)frameTimes.shift();}
    if(benchmark&&now-benchmark.start>=5000){
      benchmark.frames.push(ms);
      if(document.visibilityState!=='visible')benchmark.hiddenFrames++;
    }
  }
  lastFrame=now;
  if(tour)routeStep(dt);
  else if($('view-mode').value==='orbit') {
    controls.update();
    if(lastTarget)velocity=[(controls.target.x-lastTarget.x)/Math.max(dt,.016),
                            (controls.target.z-lastTarget.z)/Math.max(dt,.016)];
  }
  lastTarget=controls.target.clone();
  if(now-lastSchedule>140){schedule(now);lastSchedule=now;}
  renderer.render(scene,camera);
  if(benchmark) {
    const bytes=[...active.values()].reduce((sum,item)=>sum+item.bytes,0)+(coreLow?.bytes??0)+(coreHigh?.bytes??0);
    benchmark.peakBytes=Math.max(benchmark.peakBytes,bytes);
    benchmark.peakTextures=Math.max(benchmark.peakTextures,renderer.info.memory.textures);
    benchmark.peakCalls=Math.max(benchmark.peakCalls,renderer.info.render.calls);
    $('benchmark-state').textContent=`計測中 ${Math.floor((now-benchmark.start)/1000)} / 600 秒`;
    if(now-benchmark.start>=600000)downloadBenchmark(false);
  }
  if(manifest&&Math.floor(now/400)!==Math.floor((now-dt*1000)/400)) {
    const fps=frameTimes.length?1000*frameTimes.length/frameTimes.reduce((sum,v)=>sum+v,0):0;
    $('perf').textContent=`FPS ${fps.toFixed(1)} / p95 ${percentile(frameTimes,.95).toFixed(1)} ms / p99 ${percentile(frameTimes,.99).toFixed(1)} ms\n`+
      `Draw calls ${renderer.info.render.calls} / 三角形 ${renderer.info.render.triangles} / WebGL画像 ${renderer.info.memory.textures}`;
  }
}

async function selectTiles(value) {
  if(benchmark){downloadBenchmark(true);tour=null;}
  generation++;
  for(const controller of inFlight.values())controller.abort();
  inFlight.clear();desired.clear();ttl.clear();
  for(const item of active.values())dispose(item.root);
  active.clear();
  if(coreLow){dispose(coreLow.root);coreLow=null;}
  if(coreHigh){dispose(coreHigh.root);coreHigh=null;}
  if(overview){dispose(overview);overview=null;}
  coreLoading=false;manifest=null;route=null;roadProvider=null;size=value;
  base=`../dist/real/fukushima-east-1km/tiles-${size}/`;
  $('state').textContent=`${size} m タイルを読み込み中…`;
  const token=generation;
  try {
    const [m,r]=await Promise.all([fetch(base+'tileset.json').then(res=>res.json()),
                                   fetch(base+'route.json').then(res=>res.json())]);
    if(token!==generation)return;
    if(m.schema!=='therabby.geoengine.tileset.wide.v0.1'||m.tile_size_m!==size||
       m.tiles.length!==(1000/size)**2||r.schema!=='therabby.geoengine.route.v0.1')
      throw new Error('Unsupported wide tileset or route');
    manifest=m;route=r;
    roadProvider=new RoadTileProvider(base,m);
    await roadProvider.loadTerrain();
    if(token!==generation)return;
    new THREE.TextureLoader().load(base+m.overview_ground,texture=>{
      if(token!==generation){texture.dispose();return;}
      texture.colorSpace=THREE.SRGBColorSpace;
      texture.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());
      overview=new THREE.Mesh(new THREE.PlaneGeometry(1000,1000),
        new THREE.MeshLambertMaterial({map:texture,side:THREE.DoubleSide}));
      overview.rotation.x=-Math.PI/2;
      overview.position.y=(roadProvider.terrain?.min_relative_m??0)-.115;
      scene.add(overview);
    },undefined,error=>{failCount++;console.error(error);});
    loadCoreLow(token);reset();
  } catch(error){$('state').textContent=`読込失敗: ${error.message}`;console.error(error);}
}

$('tile-size').onchange=event=>selectTiles(Number(event.target.value));
$('quality').onchange=()=>schedule(performance.now());
$('view-mode').onchange=()=>{controls.enabled=$('view-mode').value==='orbit';reset();};
function beginTour() {
  if(!route)return;
  const index=nearestStartIndex();
  tour={index,distance:0,direction:1};
}
$('tour').onclick=()=>{reset();beginTour();};
$('stop').onclick=()=>{tour=null;velocity=[0,0];};
$('reset').onclick=reset;
$('overview').onclick=()=>{tour=null;$('view-mode').value='orbit';controls.enabled=true;controls.target.set(0,7,0);camera.position.set(-470,620,500);controls.update();schedule(performance.now());};
$('benchmark').onclick=()=>{
  if(!route||benchmark)return;
  $('view-mode').value='drive';controls.enabled=false;
  reset();beginTour();
  benchmark={start:performance.now(),frames:[],hiddenFrames:0,peakBytes:0,peakTextures:0,peakCalls:0,
             loads:loadCount,unloads:unloadCount,failures:failCount,transferred};
};
$('benchmark-stop').onclick=()=>downloadBenchmark(true);
addEventListener('keydown',event=>{
  if($('view-mode').value==='drive')return;
  const delta={ArrowLeft:[-8,0],ArrowRight:[8,0],ArrowUp:[0,-8],ArrowDown:[0,8]}[event.key];
  if(!delta)return;event.preventDefault();tour=null;
  setFocus(controls.target.x+delta[0],controls.target.z+delta[1]);
  velocity=delta;schedule(performance.now());
});
const requestedSize=Number(new URLSearchParams(location.search).get('tile'));
const initialSize=[100,250,500].includes(requestedSize)?requestedSize:250;
$('tile-size').value=String(initialSize);
if(new URLSearchParams(location.search).get('quality')==='high')$('quality').value='high';
if(new URLSearchParams(location.search).get('view')==='orbit')$('view-mode').value='orbit';
controls.enabled=$('view-mode').value==='orbit';
selectTiles(initialSize);
requestAnimationFrame(animate);
