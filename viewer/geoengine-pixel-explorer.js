import * as THREE from 'three';
import {closestDriveRoad, advanceVehicle} from './geoengine-pixel-explorer-core.mjs';

// Pixel Explorer: stylized renderer + orthographic city view + experimental road-constrained car.
// Keep source PLATEAU textures, geometry and geospatial coordinates unchanged.
export function createPixelExplorer({scene,renderer,camera,controls,active,origin,
  onBeforeDrive=()=>{},onDriveChange=()=>{},onMessage=()=>{}}) {
  const target = new THREE.WebGLRenderTarget(2,2,{
    minFilter:THREE.NearestFilter, magFilter:THREE.NearestFilter,
    depthBuffer:true, stencilBuffer:false
  });
  target.texture.generateMipmaps=false;
  const ortho = new THREE.OrthographicCamera(-200,200,125,-125,0.1,6000);
  const outputScene = new THREE.Scene();
  const outputCamera = new THREE.OrthographicCamera(-1,1,1,-1,0,1);
  const material = new THREE.ShaderMaterial({
    uniforms:{tFrame:{value:target.texture}, uStep:{value:new THREE.Vector2(1/2,1/2)},
      uPalette:{value:12},uOutlines:{value:0.44}},
    vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.0,1.0);}',
    fragmentShader:[
      'varying vec2 vUv;',
      'uniform sampler2D tFrame;',
      'uniform vec2 uStep;',
      'uniform float uPalette;',
      'uniform float uOutlines;',
      'float brightness(vec3 c){return dot(c,vec3(0.299,0.587,0.114));}',
      'void main(){',
      '  vec3 c=texture2D(tFrame,vUv).rgb;',
      '  float l=brightness(c);',
      '  float dx=abs(l-brightness(texture2D(tFrame,vUv+vec2(uStep.x,0.0)).rgb));',
      '  float dy=abs(l-brightness(texture2D(tFrame,vUv+vec2(0.0,uStep.y)).rgb));',
      '  float edge=smoothstep(0.13,0.31,max(dx,dy));',
      '  c=floor(c*uPalette+0.5)/uPalette;',
      '  c*=1.0-uOutlines*edge*0.48;',
      '  gl_FragColor=vec4(c,1.0);',
      '}'
    ].join('\n')
  });
  const quad=new THREE.Mesh(new THREE.PlaneGeometry(2,2),material);
  quad.frustumCulled=false;outputScene.add(quad);
  let pixelEnabled=false,isoEnabled=false,pixelScale=2,isoSpan=240,vehicle=null,carState=null;
  let lastStatus=0,wasOutside=false,widget={};
  const tilt=new THREE.Vector3(-1,1.14,1).normalize();

  function placeIso() {
    const focus=carState ? new THREE.Vector3(carState.x,carState.y+1,carState.z) : controls.target;
    const w=Math.max(1,renderer.domElement.width),h=Math.max(1,renderer.domElement.height);
    const aspect=w/h,half=isoSpan/2;
    ortho.left=-half*aspect;ortho.right=half*aspect;
    ortho.top=half;ortho.bottom=-half;
    ortho.updateProjectionMatrix();
    ortho.position.copy(focus).addScaledVector(tilt,900);
    ortho.lookAt(focus);
  }
  function render(bypass=false){
    const view=bypass?camera:isoEnabled?(placeIso(),ortho):camera;
    if(bypass || !pixelEnabled){renderer.render(scene,view);return;}
    const w=Math.max(1,renderer.domElement.width),h=Math.max(1,renderer.domElement.height);
    const sw=Math.max(1,Math.floor(w/pixelScale)),sh=Math.max(1,Math.floor(h/pixelScale));
    if(target.width!==sw || target.height!==sh)target.setSize(sw,sh);
    material.uniforms.uStep.value.set(1/sw,1/sh);
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(scene,view);
    renderer.setRenderTarget(null);
    renderer.render(outputScene,outputCamera);
  }
  function setPixel(enabled){
    pixelEnabled=Boolean(enabled);
    if(widget.pixel)widget.pixel.checked=pixelEnabled;
  }
  function setIsometric(enabled){
    isoEnabled=Boolean(enabled);
    if(widget.iso)widget.iso.setAttribute('aria-pressed',String(isoEnabled));
    if(widget.normal)widget.normal.setAttribute('aria-pressed',String(!isoEnabled));
    if(widget.iso)widget.iso.className=isoEnabled?'':'secondary';
    if(widget.normal)widget.normal.className=isoEnabled?'secondary':'';
  }
  function bodyPart(parent,shape,color,x,y,z){
    const mesh=new THREE.Mesh(shape,new THREE.MeshLambertMaterial({color,flatShading:true}));
    mesh.position.set(x,y,z);parent.add(mesh);return mesh;
  }
  function buildCar(){
    const root=new THREE.Group();
    bodyPart(root,new THREE.BoxGeometry(1.85,0.65,3.7),0xb94f46,0,0.67,0);
    bodyPart(root,new THREE.BoxGeometry(1.57,0.58,1.95),0xd36b55,0,1.25,0.28);
    bodyPart(root,new THREE.BoxGeometry(1.37,0.38,0.06),0x527a87,0,1.3,-0.72);
    bodyPart(root,new THREE.BoxGeometry(1.35,0.36,0.06),0x6f9aa7,0,1.3,1.24);
    for(const x of [-0.92,0.92])for(const z of [-1.18,1.18])
      bodyPart(root,new THREE.BoxGeometry(0.36,0.65,0.73),0x30363e,x,0.36,z);
    for(const x of [-0.6,0.6]){
      bodyPart(root,new THREE.BoxGeometry(0.36,0.16,0.05),0xf7d8a0,x,0.7,-1.88);
      bodyPart(root,new THREE.BoxGeometry(0.36,0.15,0.05),0xba3032,x,0.7,1.88);
    }
    return root;
  }
  function driveStatus(message){
    if(widget.status)widget.status.textContent=message;
    onMessage(message);
  }
  function positionVehicle(){
    if(!vehicle||!carState)return;
    vehicle.position.set(carState.x,carState.y+0.13,carState.z);
    vehicle.rotation.y=carState.yaw;
    const f=new THREE.Vector3(-Math.sin(carState.yaw),0,-Math.cos(carState.yaw));
    controls.target.set(carState.x,carState.y+1.4,carState.z);
    if(!isoEnabled){
      camera.position.set(carState.x-f.x*11,carState.y+6.6,carState.z-f.z*11);
      camera.lookAt(carState.x+f.x*4,carState.y+1.4,carState.z+f.z*4);
    }
  }
  function startDriving(){
    if(vehicle)return true;
    const road=closestDriveRoad(active,origin,controls.target.x,controls.target.z,90);
    if(!road){
      driveStatus('走行できるOSM道路が近くにありません。道路タイルの読込後、道路付近へ移動してください。');
      return false;
    }
    onBeforeDrive();
    const yaw=Math.atan2(-road.dx,-road.dz);
    carState={x:road.x,z:road.z,y:road.y,yaw,speed:0};
    vehicle=buildCar();scene.add(vehicle);
    setPixel(true);setIsometric(false);controls.enabled=false;onDriveChange(true);
    if(widget.drive)widget.drive.textContent='運転を終了';
    positionVehicle();
    driveStatus('試験走行：W/S 加速・後退、A/D ハンドル、Space ブレーキ。走行範囲は推定道路幅です。');
    return true;
  }
  function stopDriving(){
    if(!vehicle)return;
    const old=vehicle;vehicle=null;scene.remove(old);
    old.traverse(node=>{node.geometry?.dispose();node.material?.dispose();});
    carState=null;controls.enabled=true;onDriveChange(false);
    if(widget.drive)widget.drive.textContent='車を運転する';
    driveStatus('簡易運転を終了しました。道路位置・車線・走行可否は保証されません。');
  }
  function update(dt,keys,now=performance.now()){
    if(!vehicle||!carState)return;
    const proposed=advanceVehicle(carState,keys,dt);
    const road=closestDriveRoad(active,origin,proposed.x,proposed.z,16);
    // Require wheels to remain close to a plausible road surface; no lane or sign compliance.
    const tolerance=road?Math.max(1.45,road.width/2-0.75):0;
    if(road&&road.distance<=tolerance){
      carState={...proposed,y:road.y};
      wasOutside=false;
    }else{
      carState.speed=0;
      wasOutside=true;
    }
    positionVehicle();
    if(now-lastStatus>240){
      lastStatus=now;
      driveStatus('速度 '+Math.abs(carState.speed*3.6).toFixed(1)+' km/h'+
        (wasOutside?' ／ 推定道路の外周に接近（停止）':' ／ OSM道路（幅・車線は推定）'));
    }
  }
  function bindUI({pixel,iso,normal,scale,zoom,drive,status,initialPixel=false}){
    widget={pixel,iso,normal,scale,zoom,drive,status};
    setPixel(initialPixel);setIsometric(false);
    pixel.addEventListener('change',()=>setPixel(pixel.checked));
    iso.addEventListener('click',()=>{if(!vehicle){setPixel(true);}setIsometric(true);});
    normal.addEventListener('click',()=>setIsometric(false));
    scale.addEventListener('change',()=>{pixelScale=Number(scale.value)||2;});
    zoom.addEventListener('input',()=>{isoSpan=Number(zoom.value)||240;});
    drive.addEventListener('click',()=>vehicle?stopDriving():startDriving());
  }
  return {render,update,bindUI,setPixel,setIsometric,startDriving,stopDriving,
    get driving(){return Boolean(vehicle);},
    dispose(){stopDriving();target.dispose();quad.geometry.dispose();material.dispose();}};
}
