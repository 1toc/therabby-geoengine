import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const base = '../dist/real/fukushima-east/';
const models = {
  photo: { label: '元写真', file: 'city_sharp.glb' },
  redrawn: { label: '全棟描き直し', file: 'city_photo_redrawn_all.glb' },
  optimized: { label: '軽量化版', file: 'city_photo_optimized.glb' },
  crisp: { label: '近景修正版', file: 'city_photo_crisp.glb' },
};
const status = document.querySelector('#status');
const metrics = document.querySelector('#metrics');
const reportBox = document.querySelector('#report');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xa3bac5);
scene.fog = new THREE.Fog(0xa3bac5, 310, 780);
const camera = new THREE.PerspectiveCamera(52, innerWidth / innerHeight, .1, 1400);
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'default' });
const gl = renderer.getContext();
const debugRenderer = gl.getExtension('WEBGL_debug_renderer_info');
const gpuRenderer = debugRenderer ? gl.getParameter(debugRenderer.UNMASKED_RENDERER_WEBGL) : null;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setPixelRatio(1);
renderer.setSize(innerWidth, innerHeight);
document.querySelector('#viewport').appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.maxPolarAngle = Math.PI * .65;
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xf2f7ff, 0x738f81, 2.4));
const sun = new THREE.DirectionalLight(0xffe8cf, 2.4);
sun.position.set(-90, 160, 85);
scene.add(sun);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(800, 800), new THREE.MeshLambertMaterial({ color: 0x8da992 }));
ground.rotation.x = -Math.PI / 2;
ground.position.y = -.12;
scene.add(ground);

let current = null;
let currentKey = null;
let loading = false;
let loadMs = null;
let textureStats = null;
let center = new THREE.Vector3();
let pose = 'overview';
let benchmark = null;
let lastReport = null;
let lastFrame = 0;
let liveFrames = [];
let lastMetrics = 0;

function view(kind) {
  pose = kind;
  if (kind === 'street') {
    // The station-front road is near x=-70 in the current local map.
    controls.target.set(-45, 8, -80);
    camera.position.set(-70, 1.7, 75);
  } else {
    controls.target.copy(center);
    camera.position.copy(center).add(new THREE.Vector3(175, 145, 185));
  }
  controls.update();
}
document.querySelector('#reset').onclick = () => view('overview');
document.querySelector('#street').onclick = () => view('street');
document.querySelector('#scale').onchange = event => {
  renderer.setPixelRatio(Number(event.target.value));
  renderer.setSize(innerWidth, innerHeight);
};
document.querySelector('#show-metrics').onchange = event => {
  metrics.hidden = !event.target.checked;
};

function disposeModel(root) {
  if (!root) return;
  scene.remove(root);
  const geometries = new Set(), materials = new Set(), textures = new Set();
  root.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of (Array.isArray(object.material) ? object.material : object.material ? [object.material] : [])) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  textures.forEach(texture => texture.dispose());
  materials.forEach(material => material.dispose());
  geometries.forEach(geometry => geometry.dispose());
  renderer.renderLists.dispose();
}

function textureInventory(gltf) {
  const unique = new Set();
  gltf.scene.traverse(object => {
    for (const material of (Array.isArray(object.material) ? object.material : object.material ? [object.material] : [])) {
      for (const value of Object.values(material)) if (value?.isTexture) unique.add(value);
    }
  });
  const items = [...unique].map(texture => {
    const image = texture.image;
    return { width: image?.width || 0, height: image?.height || 0 };
  });
  const formats = {};
  for (const image of gltf.parser.json.images || []) {
    const format = image.mimeType || image.uri?.split('.').pop() || 'unknown';
    formats[format] = (formats[format] || 0) + 1;
  }
  const pixels = items.reduce((sum, item) => sum + item.width * item.height, 0);
  return { count: items.length, formats, sizes: items, pixels,
    // RGBA8 plus full mip chain: a theoretical upper-bound-like allocation, not actual VRAM.
    rgba8MipEstimateMiB: Math.round(pixels * 4 * 4 / 3 / 1048576) };
}

async function loadModel(key) {
  if (loading || !models[key] || key === currentKey) return;
  loading = true;
  document.querySelectorAll('[data-model]').forEach(button => button.disabled = true);
  if (benchmark) finishBenchmark(true);
  disposeModel(current);
  current = null;
  currentKey = null;
  textureStats = null;
  status.textContent = `${models[key].label}を読み込み中…`;
  // One GLB at a time, so other variants do not inflate the measurement.
  const start = performance.now();
  try {
    const gltf = await new GLTFLoader().loadAsync(base + models[key].file);
    loadMs = Math.round(performance.now() - start);
    current = gltf.scene;
    currentKey = key;
    textureStats = textureInventory(gltf);
    scene.add(current);
    new THREE.Box3().setFromObject(current).getCenter(center);
    view(pose);
    liveFrames = [];
    lastFrame = 0;
    status.textContent = `${models[key].label}｜読込 ${loadMs} ms`;
    reportBox.textContent = '';
  } catch (error) {
    status.textContent = `読込失敗: ${error.message}`;
    console.error(error);
  } finally {
    loading = false;
    document.querySelectorAll('[data-model]').forEach(button => {
      button.disabled = false;
      button.classList.toggle('active', button.dataset.model === currentKey);
    });
  }
}
document.querySelectorAll('[data-model]').forEach(button => button.onclick = () => loadModel(button.dataset.model));

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil(sorted.length * p) - 1];
}
function summary(samples, durationMs) {
  if (!samples.length) return { frames: 0, averageFps: 0, meanFrameMs: null,
    p95FrameMs: null, maxFrameMs: null, over50ms: 0, over100ms: 0 };
  return { frames: samples.length, averageFps: +(samples.length * 1000 / durationMs).toFixed(1),
    meanFrameMs: +(samples.reduce((sum, v) => sum + v, 0) / samples.length).toFixed(2),
    p95FrameMs: +percentile(samples, .95).toFixed(2),
    maxFrameMs: +Math.max(...samples).toFixed(2),
    over50ms: samples.filter(v => v > 50).length,
    over100ms: samples.filter(v => v > 100).length };
}
function beginBenchmark() {
  if (!current || loading || benchmark) return;
  view('overview');
  benchmark = { start: performance.now(), static: [], moving: [] };
  document.querySelector('#bench').disabled = true;
  status.textContent = '30秒計測中：最初の5秒は静止、残り25秒は自動移動';
}
function finishBenchmark(cancelled = false) {
  if (!benchmark) return;
  const b = benchmark;
  benchmark = null;
  document.querySelector('#bench').disabled = false;
  if (cancelled) return;
  lastReport = { schema: 'therabby.geoengine.benchmark.v1', model: currentKey,
    file: models[currentKey].file, timestamp: new Date().toISOString(),
    browser: navigator.userAgent, gpuRenderer, hardwareConcurrency: navigator.hardwareConcurrency ?? null,
    deviceMemoryGiB: navigator.deviceMemory ?? null, viewportCss: [innerWidth, innerHeight],
    drawingBuffer: [renderer.domElement.width, renderer.domElement.height],
    devicePixelRatio: devicePixelRatio, renderScale: renderer.getPixelRatio(),
    loadMs, drawCallsLastFrame: renderer.info.render.calls,
    trianglesLastFrame: renderer.info.render.triangles,
    textureStats, rendererTextureCount: renderer.info.memory.textures,
    jsHeapBytes: performance.memory?.usedJSHeapSize ?? null,
    static: summary(b.static, 5000), moving: summary(b.moving, 25000),
    note: 'Frame intervals and draw calls are browser observations. Texture MiB is a theoretical RGBA8+mips estimate, not measured GPU memory.' };
  reportBox.textContent = JSON.stringify({ model: currentKey, static: lastReport.static,
    moving: lastReport.moving, loadMs, drawCalls: lastReport.drawCallsLastFrame,
    gpuRenderer, textureMiBEstimate: textureStats.rgba8MipEstimateMiB }, null, 2);
  document.querySelector('#download').disabled = false;
  status.textContent = `${models[currentKey].label}の計測完了。移動中 ${lastReport.moving.averageFps} FPS / p95 ${lastReport.moving.p95FrameMs} ms`;
}
document.querySelector('#bench').onclick = beginBenchmark;
document.querySelector('#download').onclick = () => {
  if (!lastReport) return;
  const blob = new Blob([JSON.stringify(lastReport, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `geoengine-${lastReport.model}-benchmark.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

function animate(now) {
  requestAnimationFrame(animate);
  const interval = lastFrame ? now - lastFrame : 0;
  lastFrame = now;
  if (interval > 0 && interval < 1000) {
    liveFrames.push(interval);
    if (liveFrames.length > 120) liveFrames.shift();
  }
  if (benchmark) {
    const elapsed = now - benchmark.start;
    if (elapsed >= 30000) finishBenchmark();
    else if (elapsed >= 5000) {
      if (interval > 0 && interval < 1000) benchmark.moving.push(interval);
      const angle = (elapsed - 5000) / 25000 * Math.PI * 2;
      camera.position.copy(center).add(new THREE.Vector3(155 * Math.cos(angle), 55 + 25 * Math.sin(angle * 2), 155 * Math.sin(angle)));
      camera.lookAt(center);
    } else if (interval > 0 && interval < 1000) benchmark.static.push(interval);
  } else controls.update();
  renderer.render(scene, camera);
  if (now - lastMetrics > 500 && textureStats) {
    const fps = liveFrames.length ? (1000 * liveFrames.length / liveFrames.reduce((sum, v) => sum + v, 0)).toFixed(1) : '—';
    metrics.textContent = `FPS ${fps} / p95 ${percentile(liveFrames, .95)?.toFixed(1) ?? '—'} ms\n` +
      `Draw calls ${renderer.info.render.calls} / 三角形 ${renderer.info.render.triangles}\n` +
      `テクスチャ ${textureStats.count}枚 (${JSON.stringify(textureStats.formats)})\n` +
      `画像画素 ${textureStats.pixels.toLocaleString()} / RGBA8+mip概算 ${textureStats.rgba8MipEstimateMiB} MiB\n` +
      `WebGL登録テクスチャ ${renderer.info.memory.textures} / JS heap ${performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) + ' MiB' : '取得不可'}\n` +
      `読込 ${loadMs} ms / 描画 ${renderer.domElement.width}×${renderer.domElement.height}`;
    lastMetrics = now;
  }
}
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
view('overview');
requestAnimationFrame(animate);
loadModel('optimized');
