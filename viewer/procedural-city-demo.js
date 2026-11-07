import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {ProceduralCity,createEstimatedMarkingMeshes} from './geoengine-procedural-city.js';

const viewport=document.getElementById('viewport');
const renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'low-power'});
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.setPixelRatio(Math.min(1.5,window.devicePixelRatio||1));
renderer.setSize(viewport.clientWidth,viewport.clientHeight);
viewport.append(renderer.domElement);
const renderCheck=document.getElementById('render-check');
let shaderFailed=false;
renderer.debug.onShaderError=(gl,program,vertexShader,fragmentShader)=>{
  shaderFailed=true;
  renderCheck.dataset.state='error';
  renderCheck.textContent='Shader compile failed';
  document.getElementById('error').textContent=
    gl.getProgramInfoLog(program)||gl.getShaderInfoLog(vertexShader)||gl.getShaderInfoLog(fragmentShader)||'Unknown shader error';
};
const scene=new THREE.Scene();
scene.background=new THREE.Color(0xa8c0cf);
scene.fog=new THREE.Fog(0xa8c0cf,120,360);
const camera=new THREE.PerspectiveCamera(58,viewport.clientWidth/viewport.clientHeight,0.1,500);
const controls=new OrbitControls(camera,renderer.domElement);
controls.enableDamping=true;
controls.target.set(0,7,0);camera.position.set(68,59,125);
controls.update();
scene.add(new THREE.HemisphereLight(0xf4f9ff,0x536c63,2));
const hemisphere=scene.children.find(x=>x.isHemisphereLight);
const sunlight=new THREE.DirectionalLight(0xffe5b8,2.1);
sunlight.position.set(-65,110,50);
scene.add(sunlight);
const procedural=new ProceduralCity({scene,sunlight,hemisphere});
procedural.setQuality('standard');
procedural.setEnabled(true);

const mat=(color,params={})=>new THREE.MeshStandardMaterial({color,roughness:0.92,...params});
const terrain=new THREE.Mesh(new THREE.PlaneGeometry(260,500),mat(0x677d69));
terrain.rotation.x=-Math.PI/2;terrain.position.y=-.12;scene.add(terrain);
function asphalt(x,z,width,length,rotation=0){
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(width,.12,length),mat(0x3b4148,{roughness:.98}));
  mesh.position.set(x,0,z);mesh.rotation.y=rotation;scene.add(mesh);return mesh;
}
asphalt(0,0,13,360);
for(const z of [-105,0,105])asphalt(0,z,12,175,Math.PI/2);

let seed=20261107;
const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
const facades=new THREE.Group(),wall=mat(0x8b9a95),roof=mat(0x687b7e);
wall.name='LOD1 walls / official shape';roof.name='LOD1 roofs / official shape';
for(let row=-6;row<=6;row++){
  for(const side of [-1,1]){
    if(row===0)continue;
    for(let col=0;col<2;col++){
      const width=9+random()*8,depth=10+random()*8,height=7+random()*30;
      const x=side*(18+col*18+random()*3),z=row*24+random()*5;
      const body=new THREE.Mesh(new THREE.BoxGeometry(width,height,depth),wall);
      body.position.set(x,height/2,z);
      facades.add(body);
      const cap=new THREE.Mesh(new THREE.BoxGeometry(width+.5,.3,depth+.5),roof);
      cap.position.set(x,height+.15,z);facades.add(cap);
      if(height<15&&random()>.55){
        const block=new THREE.Mesh(new THREE.BoxGeometry(width*.25,1.5,depth*.25),roof);
        block.position.set(x,height+1,z);facades.add(block);
      }
    }
  }
}
scene.add(facades);
procedural.installFacades(facades,'building');

const roads=new THREE.Group();scene.add(roads);
const fakeEdges=[{points:[[0,-177],[0,177]],width_m:13,highway:'primary',
  oneway_osm_tag:'no',ground_height_from_tp_m:0,ground_height_to_tp_m:0}];
for(const z of [-105,0,105]){
 fakeEdges.push({points:[[-85,z],[85,z]],width_m:12,highway:'secondary',
  oneway_osm_tag:'no',ground_height_from_tp_m:0,ground_height_to_tp_m:0});
}
roads.userData.geoProceduralRoadFactory=()=>createEstimatedMarkingMeshes({edges:fakeEdges},(_,h)=>h);
procedural.installRoadPaint(roads);

// Small, shared tree meshes and lampposts; no external textures or models.
const trunkMaterial=mat(0x534b3b),leafMaterial=mat(0x335f48),lampMaterial=mat(0x39474b);
const bulbMaterial=mat(0xf5e1b2,{emissive:0xd19e55,emissiveIntensity:0.6});
const trunk=new THREE.CylinderGeometry(.12,.2,2.2,5),leaf=new THREE.IcosahedronGeometry(1.75,0);
const pole=new THREE.CylinderGeometry(.07,.09,6.5,6);
for(let z=-164;z<=164;z+=24){
  for(const side of [-1,1]){
    if(Math.abs(z)%105<13)continue;
    const x=side*(9.6+random());
    const tree=new THREE.Mesh(trunk,trunkMaterial);tree.position.set(x,1.1,z);scene.add(tree);
    const crown=new THREE.Mesh(leaf,leafMaterial);crown.position.set(x,3,z);scene.add(crown);
    if((Math.floor(z/24)+6)%2===0){
      const post=new THREE.Mesh(pole,lampMaterial);post.position.set(side*8,3.25,z+8);scene.add(post);
      const light=new THREE.Mesh(new THREE.SphereGeometry(.25,6,5),bulbMaterial);
      light.position.set(side*8,6.5,z+8);scene.add(light);
    }
  }
}
const vehicleMaterial=[mat(0xe8e6df),mat(0xbd4741),mat(0x547d8c),mat(0xd9a75f)];
const wheels=mat(0x222629);
const traffic=[];
for(let i=0;i<10;i++){
  const car=new THREE.Group();
  const body=new THREE.Mesh(new THREE.BoxGeometry(1.6,.65,3.2),vehicleMaterial[i%4]);
  body.position.y=.65;car.add(body);
  const cabin=new THREE.Mesh(new THREE.BoxGeometry(1.3,.58,1.55),mat(0x303b45));
  cabin.position.set(0,1.25,-.1);car.add(cabin);
  for(const side of [-1,1])for(const end of [-1,1]){
    const wheel=new THREE.Mesh(new THREE.CylinderGeometry(.28,.28,.2,8),wheels);
    wheel.rotation.z=Math.PI/2;wheel.position.set(side*.82,.31,end*1.04);car.add(wheel);
  }
  scene.add(car);traffic.push({car,offset:i*40,dir:i%2===0?1:-1,x:i%2===0?-3.3:3.3});
}
const clock=document.getElementById('clock'),hour=document.getElementById('hour'),mode=document.getElementById('mode'),cars=document.getElementById('cars');
function apply(){
  procedural.setEnabled(mode.checked);
  procedural.toggleRoadPaint(roads);
  procedural.setTime(Number(hour.value));
  clock.textContent=`${String(Math.floor(Number(hour.value))).padStart(2,'0')}:${Number(hour.value)%1?'30':'00'}`;
}
mode.onchange=apply;hour.oninput=apply;
document.getElementById('reset').onclick=()=>{camera.position.set(68,59,125);controls.target.set(0,7,0);controls.update();};
const resize=new ResizeObserver(()=>{
  const w=viewport.clientWidth,h=viewport.clientHeight;
  if(w<1||h<1)return;
  camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h);
});
resize.observe(viewport);
let last=0,travel=0;
function draw(now){
  requestAnimationFrame(draw);
  const dt=Math.min(.05,last?(now-last)/1000:0);last=now;
  if(cars.checked)travel+=dt*7;
  traffic.forEach(({car,offset,dir,x})=>{
    car.position.set(x,.02,dir*((travel+offset)%340-170));
    car.rotation.y=dir===1?0:Math.PI;
    car.visible=cars.checked;
  });
  controls.update();
  renderer.render(scene,camera);
  if(!shaderFailed&&renderer.info.programs?.length&&renderCheck.dataset.state==='pending'){
    renderCheck.dataset.state='rendered';
    renderCheck.textContent='WebGL描画中（この架空シーンの表示確認）';
  }
}
try{apply();requestAnimationFrame(draw);}
catch(error){document.getElementById('error').textContent=error.stack||String(error);}
