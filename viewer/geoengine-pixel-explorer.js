import * as THREE from 'three';
import {closestDriveRoad, advanceVehicle} from './geoengine-pixel-explorer-core.mjs';

// Pixel Explorer: stylized renderer + orthographic city view + experimental road-constrained car.
// Keep source PLATEAU textures, geometry and geospatial coordinates unchanged.
export function createPixelExplorer({scene,renderer,camera,controls,active,origin,
  onBeforeDrive=()=>{},onDriveChange=()=>{},onMessage=()=>{},photoVisible=()=>true,getWalking=()=>false}) {
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
  const avatar=buildWalker();avatar.visible=false;scene.add(avatar);

  function placeIso() {
    const focus=carState ? new THREE.Vector3(carState.x,carState.y+1,carState.z) : avatar.visible ? avatar.position.clone().add(new THREE.Vector3(0,1.3,0)) : controls.target;
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
  // Stylize each source facade photo independently while preserving its UV transform.
  // This is a faithful, non-generative starting point, not a replacement for authored pixel art.
  function pixelizeTexture(original){
    const image=original.image;
    if(!image?.width||!image?.height)return null;
    try{
      const ratio=Math.min(1,512/Math.max(image.width,image.height));
      const width=Math.max(1,Math.round(image.width*ratio));
      const height=Math.max(1,Math.round(image.height*ratio));
      const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
      const ctx=canvas.getContext('2d',{willReadFrequently:true});
      ctx.drawImage(image,0,0,width,height);
      const pixels=ctx.getImageData(0,0,width,height),data=pixels.data;
      const gray=new Uint8Array(width*height);
      for(let i=0,j=0;i<data.length;i+=4,j++)
        gray[j]=(77*data[i]+150*data[i+1]+29*data[i+2])>>8;
      for(let y=0;y<height;y++)for(let x=0;x<width;x++){
        const p=y*width+x,i=p*4;
        const edge=Math.max(Math.abs(gray[p]-gray[Math.min(x+1,width-1)+y*width]),
          Math.abs(gray[p]-gray[x+Math.min(y+1,height-1)*width]));
        const ink=edge>44?0.82:1;
        for(let k=0;k<3;k++)data[i+k]=Math.min(255,Math.round(data[i+k]/17)*17*ink);
      }
      ctx.putImageData(pixels,0,0);
      const result=new THREE.CanvasTexture(canvas);
      result.name='pixel-art-derivative-of-'+(original.name||'PLATEAU-photo');
      result.colorSpace=original.colorSpace;
      result.flipY=original.flipY;
      result.wrapS=original.wrapS;result.wrapT=original.wrapT;
      result.offset.copy(original.offset);result.repeat.copy(original.repeat);
      result.center.copy(original.center);result.rotation=original.rotation;
      result.magFilter=THREE.NearestFilter;
      result.minFilter=THREE.NearestMipmapNearestFilter;
      result.anisotropy=1;
      result.needsUpdate=true;
      return result;
    }catch(error){console.warn('ピクセル写真の処理に失敗:',error);return null;}
  }
  function syncPhotos(photosVisible=photoVisible()){
    for(const [key,item] of active){
      if(!key.startsWith('photo-'))continue;
      item.root.traverse(object=>{
        for(const mat of Array.isArray(object.material)?object.material:object.material?[object.material]:[]){
          const original=mat.userData.officialPhotoMap;
          if(!original)continue;
          if(pixelEnabled&&photosVisible&&!mat.userData.pixelArtPhotoMap)
            mat.userData.pixelArtPhotoMap=pixelizeTexture(original);
          const next=photosVisible?(pixelEnabled&&mat.userData.pixelArtPhotoMap||
            original):null;
          if(mat.map!==next){mat.map=next;mat.needsUpdate=true;}
        }
      });
    }
  }
  function setPixel(enabled){
    pixelEnabled=Boolean(enabled);
    if(widget.pixel)widget.pixel.checked=pixelEnabled;
    syncPhotos();
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
  function buildWalker(){
    const root=new THREE.Group();
    bodyPart(root,new THREE.BoxGeometry(0.63,0.74,0.33),0x487aa1,0,1.05,0);
    bodyPart(root,new THREE.BoxGeometry(0.49,0.51,0.48),0xf0c8a3,0,1.68,0);
    bodyPart(root,new THREE.BoxGeometry(0.54,0.16,0.53),0x30353c,0,2.0,0);
    for(const x of [-0.19,0.19])
      bodyPart(root,new THREE.BoxGeometry(0.24,0.53,0.29),0x293b56,x,0.42,0);
    return root;
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
    avatar.visible=isoEnabled && !vehicle && getWalking();
    if(avatar.visible)avatar.position.set(camera.position.x,camera.position.y-1.6,camera.position.z);
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
  return {render,update,bindUI,setPixel,setIsometric,startDriving,stopDriving,syncPhotos,
    get driving(){return Boolean(vehicle);},
    dispose(){stopDriving();scene.remove(avatar);
      avatar.traverse(node=>{node.geometry?.dispose();node.material?.dispose();});
      target.dispose();quad.geometry.dispose();material.dispose();}};
}
