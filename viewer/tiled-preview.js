import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const base = '../dist/real/fukushima-east/tiles-crisp/';
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xa3bac5);
scene.fog = new THREE.Fog(0xa3bac5, 260, 650);
const camera = new THREE.PerspectiveCamera(52,innerWidth/innerHeight,.1,1000);
const renderer = new THREE.WebGLRenderer({antialias:true,powerPreference:'default'});
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setPixelRatio(1);
renderer.setSize(innerWidth,innerHeight);
document.querySelector('#viewport').appendChild(renderer.domElement);
const controls = new OrbitControls(camera,renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI*.65;
scene.add(new THREE.HemisphereLight(0xf2f7ff,0x738f81,2.4));
const sun = new THREE.DirectionalLight(0xffe8cf,2.4);
sun.position.set(-90,160,85);
scene.add(sun);
const background = new THREE.Mesh(new THREE.PlaneGeometry(800,800),new THREE.MeshLambertMaterial({color:0x8da992}));
background.rotation.x = -Math.PI/2;
background.position.y = -.15;
scene.add(background);

const state = document.querySelector('#state');
const perf = document.querySelector('#perf');
const tilePanel = document.querySelector('#tiles');
const route = [[-50,-50],[50,-50],[50,50],[-50,50],[-50,-50]];
const cameraOffset = new THREE.Vector3(-35,48,-35);
let manifest = null;
let tour = null;
let desired = new Set();
let currentId = null;
let velocity = [0,0];
let lastTarget = null;
let lastFrame = 0;
let lastSchedule = 0;
let lastStatus = 0;
let lastPerf = 0;
let frameTimes = [];
let loads = 0, unloads = 0, failures = 0;
const active = new Map();
const inFlight = new Map();
const ttl = new Map();

function pointTile(x,z) {
  if (!manifest) return null;
  if (x < -100 || x >= 100 || z < -100 || z >= 100) return null;
  const boundedX = Math.max(-99.999,Math.min(99.999,x));
  const boundedZ = Math.max(-99.999,Math.min(99.999,z));
  return manifest.tiles.find(tile => boundedX >= tile.bounds[0] && boundedX < tile.bounds[2] &&
                                     boundedZ >= tile.bounds[1] && boundedZ < tile.bounds[3]);
}

function setFocus(x,z) {
  const previous = controls.target.clone();
  controls.target.set(x,7,z);
  camera.position.add(controls.target.clone().sub(previous));
  controls.update();
}

function reset() {
  tour = null;
  controls.target.set(-50,7,-50);
  camera.position.copy(controls.target).add(cameraOffset);
  controls.update();
  velocity = [0,0];
  schedule(performance.now());
}
document.querySelector('#reset').onclick = reset;
document.querySelector('#tour').onclick = () => { reset(); tour = {leg:0,distance:0}; schedule(performance.now()); };
document.querySelector('#stop').onclick = () => { tour = null; velocity=[0,0]; schedule(performance.now()); };
addEventListener('keydown',event => {
  const step = 6;
  const delta = {ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[event.key];
  if (!delta) return;
  event.preventDefault();
  tour = null;
  setFocus(controls.target.x+delta[0],controls.target.z+delta[1]);
  velocity = delta;
  schedule(performance.now());
});

function dispose(root) {
  scene.remove(root);
  const geometries = new Set(),materials = new Set(),textures = new Set();
  root.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of (Array.isArray(object.material)?object.material:object.material?[object.material]:[])) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  textures.forEach(texture => {
    texture.dispose();
    // GLTFLoader may keep decoded ImageBitmap pixels after the GPU texture is freed.
    if (typeof texture.image?.close === 'function') texture.image.close();
  });
  materials.forEach(material => material.dispose());
  geometries.forEach(geometry => geometry.dispose());
  renderer.renderLists.dispose();
}

async function loadTile(tile) {
  if (active.has(tile.id) || inFlight.has(tile.id)) return;
  const controller = new AbortController();
  inFlight.set(tile.id,controller);
  try {
    const response = await fetch(base+tile.glb,{signal:controller.signal});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const bytes = await response.arrayBuffer();
    const gltf = await new GLTFLoader().parseAsync(bytes,base);
    if (!desired.has(tile.id)) {
      dispose(gltf.scene);
      return;
    }
    scene.add(gltf.scene);
    active.set(tile.id,{scene:gltf.scene,bytes:bytes.byteLength});
    loads++;
    ttl.delete(tile.id);
  } catch (error) {
    if (error.name !== 'AbortError') {
      failures++;
      state.textContent = `${tile.id} 読込失敗: ${error.message}`;
      console.error(error);
    }
  } finally {
    inFlight.delete(tile.id);
    updateStatus(performance.now());
  }
}

function schedule(now) {
  if (!manifest) return;
  const x = controls.target.x,z = controls.target.z;
  const current = pointTile(x,z);
  currentId = current?.id ?? null;
  const wanted = new Set(current ? [current.id] : []);
  const ahead = pointTile(x+velocity[0]*1.5,z+velocity[1]*1.5);
  if (ahead) wanted.add(ahead.id);
  // Hold neighbors around the internal seams while the camera crosses them.
  if (Math.abs(x)<14) {
    const neighbor=pointTile(x<0?x+16:x-16,z);
    if (neighbor) wanted.add(neighbor.id);
  }
  if (Math.abs(z)<14) {
    const neighbor=pointTile(x,z<0?z+16:z-16);
    if (neighbor) wanted.add(neighbor.id);
  }
  desired = wanted;
  for (const [id,controller] of inFlight) if (!wanted.has(id)) controller.abort();
  for (const tile of manifest.tiles) if (wanted.has(tile.id)) loadTile(tile);
  for (const [id,item] of active) {
    if (wanted.has(id)) { ttl.delete(id); continue; }
    if (!ttl.has(id)) ttl.set(id,now+1200);
    if (now>=ttl.get(id)) {
      dispose(item.scene);
      active.delete(id);
      ttl.delete(id);
      unloads++;
    }
  }
  updateStatus(now);
}

function updateStatus(now) {
  if (!manifest || now-lastStatus<180) return;
  tilePanel.innerHTML = manifest.tiles.map(tile => {
    const status = active.has(tile.id)?'loaded':inFlight.has(tile.id)?'loading':'';
    return `<span class="tile ${status} ${tile.id===currentId?'current':''}">${tile.id} ${status==='loaded'?'表示':status==='loading'?'読込中':'未読込'}</span>`;
  }).join('');
  const loadedBytes = [...active.values()].reduce((sum,item)=>sum+item.bytes,0);
  state.textContent = `地点 X ${controls.target.x.toFixed(1)}m / Z ${controls.target.z.toFixed(1)}m\n`+
    `現在 ${currentId??'範囲外'} / 表示 ${active.size} / 読込中 ${inFlight.size}\n`+
    `読込 ${loads}回 / 解放 ${unloads}回 / 失敗 ${failures}回 / 表示GLB ${(loadedBytes/1048576).toFixed(1)} MiB`;
  lastStatus=now;
}

function percentile(values,p) {
  if (!values.length) return 0;
  const sorted=[...values].sort((a,b)=>a-b);
  return sorted[Math.ceil(values.length*p)-1];
}

function animate(now) {
  requestAnimationFrame(animate);
  const dt = lastFrame ? Math.min((now-lastFrame)/1000,.1) : 0;
  if (lastFrame && now-lastFrame<1000) {
    frameTimes.push(now-lastFrame);
    if (frameTimes.length>180) frameTimes.shift();
  }
  lastFrame=now;
  if (tour) {
    let a=route[tour.leg],b=route[tour.leg+1];
    const length=Math.hypot(b[0]-a[0],b[1]-a[1]);
    tour.distance += dt*17;
    if (tour.distance>=length) {
      tour.distance-=length;
      tour.leg=(tour.leg+1)%(route.length-1);
      a=route[tour.leg]; b=route[tour.leg+1];
    }
    const t=tour.distance/Math.hypot(b[0]-a[0],b[1]-a[1]);
    const x=a[0]+(b[0]-a[0])*t,z=a[1]+(b[1]-a[1])*t;
    controls.target.set(x,7,z);
    camera.position.copy(controls.target).add(cameraOffset);
    camera.lookAt(controls.target);
    velocity=[(b[0]-a[0])/length*17,(b[1]-a[1])/length*17];
  } else {
    controls.update();
    if (lastTarget) velocity=[(controls.target.x-lastTarget.x)/Math.max(dt,.016),
                              (controls.target.z-lastTarget.z)/Math.max(dt,.016)];
  }
  lastTarget=controls.target.clone();
  if (now-lastSchedule>200) { schedule(now); lastSchedule=now; }
  renderer.render(scene,camera);
  if (now-lastPerf>400 && manifest) {
    const fps=frameTimes.length?1000*frameTimes.length/frameTimes.reduce((sum,v)=>sum+v,0):0;
    perf.textContent=`FPS ${fps.toFixed(1)} / p95 ${percentile(frameTimes,.95).toFixed(1)} ms\n`+
      `Draw calls ${renderer.info.render.calls} / 三角形 ${renderer.info.render.triangles} / WebGL画像 ${renderer.info.memory.textures}`;
    lastPerf=now;
  }
}

addEventListener('resize',()=>{
  camera.aspect=innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth,innerHeight);
});
reset();
fetch(base+'tileset.json').then(response => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then(data => {
  if (data.schema!=='therabby.geoengine.tileset.prototype.v0.1' || data.tiles.length!==4) throw new Error('Unsupported tile manifest');
  manifest=data;
  schedule(performance.now());
}).catch(error => { state.textContent=`タイル目録の読込失敗: ${error.message}`; console.error(error); });
requestAnimationFrame(animate);
