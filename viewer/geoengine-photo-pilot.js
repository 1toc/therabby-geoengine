import * as THREE from 'three';

export async function createPhotoPilot({scene,camera,controls,renderer,active,origin}){
  const base=new URL('../data/derived/station-photo-pilot/',import.meta.url);
  const response=await fetch(new URL('pilot.json',base));
  if(!response.ok)throw new Error(`pilot ${response.status}`);
  const config=await response.json();
  if(!config.projected_crs.includes('EPSG:6677'))throw new Error('Unsupported pilot CRS');
  const panel=document.createElement('section');
  panel.innerHTML='<h2>v0.3 / 100m写真検証</h2><button id="pilot-area">100m区域へ</button> <button id="pilot-near">対象写真へ接近</button> <button id="pilot-far">対象写真から離れる</button><label><input id="pilot-boundary" type="checkbox" checked>100m境界</label><label>高画質にする距離 m<input id="pilot-near-distance" type="number" min="1" value="35"></label><label>解放する距離 m<input id="pilot-far-distance" type="number" min="2" value="55"></label><button id="pilot-save">視点保存</button> <button id="pilot-restore">視点復元</button> <button id="pilot-log">通信・解放記録を保存</button><p id="pilot-status" role="status"></p>';
  document.querySelector('aside').prepend(panel);
  const $=id=>document.getElementById(id),events=[];
  let bindings=[],box=new THREE.Box3(),high=null,pending=null,retryAt=0,last=0;
  const center=new THREE.Vector3(config.area.center_east_m-origin.east,72,origin.north-config.area.center_north_m);
  const points=[[-50,-50],[50,-50],[50,50],[-50,50],[-50,-50]].map(([x,z])=>new THREE.Vector3(center.x+x,72,center.z+z));
  const boundary=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:0xff55ff,depthTest:false}));
  boundary.renderOrder=10;scene.add(boundary);
  const record=(event,extra={})=>events.push({event,time_ms:performance.now(),textures:renderer.info.memory.textures,...extra});
  function release(){
    if(pending){pending.abort();pending=null;record('abort');}
    for(const b of bindings){b.material.userData.officialPhotoMap=b.low;b.material.map=$('building-texture').checked?b.low:null;b.material.needsUpdate=true;}
    if(high){high.dispose();high.image.close?.();high=null;record('release');}
  }
  function discover(){
    const root=active.get(`photo-low:${config.tile_id}`)?.root;
    if(bindings.length&&bindings[0].root===root)return;
    release();bindings=[];box.makeEmpty();
    root?.updateMatrixWorld(true);
    root?.traverse(object=>{
      const materials=Array.isArray(object.material)?object.material:object.material?[object.material]:[];
      for(const material of materials)if(material.name===config.material&&material.userData.officialPhotoMap){
        if(!bindings.some(b=>b.material===material))bindings.push({material,low:material.userData.officialPhotoMap,root});
        if(object.geometry){object.geometry.computeBoundingBox();box.union(object.geometry.boundingBox.clone().applyMatrix4(object.matrixWorld));}
      }
    });
  }
  async function load(){
    const controller=new AbortController();pending=controller;record('request',{url:new URL(config.jpeg,base).href});
    try{
      const r=await fetch(new URL(config.jpeg,base),{signal:controller.signal});
      if(!r.ok)throw new Error(`JPEG HTTP ${r.status}`);
      const bytes=await r.arrayBuffer();
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
      if(hash!==config.sha256)throw new Error('JPEG SHA mismatch');
      const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/jpeg'}),{imageOrientation:'none'});
      if(pending!==controller||controller.signal.aborted){bitmap.close();return;}
      high=bindings[0].low.clone();high.source=new THREE.Source(bitmap);high.flipY=false;high.needsUpdate=true;
      for(const b of bindings){b.material.userData.officialPhotoMap=high;b.material.map=$('building-texture').checked?high:null;b.material.needsUpdate=true;}
      record('loaded',{bytes:bytes.byteLength,sha256:hash,width:bitmap.width,height:bitmap.height});
    }catch(error){if(error.name!=='AbortError'){record('failure',{message:error.message});retryAt=performance.now()+10000;}}
    finally{if(pending===controller)pending=null;}
  }
  $('pilot-boundary').onchange=()=>boundary.visible=$('pilot-boundary').checked;
  $('pilot-area').onclick=()=>{controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(0,160,100));};
  function move(near){discover();if(box.isEmpty())return;const c=box.getCenter(new THREE.Vector3());controls.target.copy(c);camera.position.set(c.x,box.max.y+8,box.max.z+(near?25:130));controls.update();}
  $('pilot-near').onclick=()=>move(true);$('pilot-far').onclick=()=>move(false);
  $('pilot-save').onclick=()=>{localStorage.setItem('geoengine-pilot-camera',JSON.stringify({position:camera.position.toArray(),target:controls.target.toArray()}));record('camera-saved');};
  $('pilot-restore').onclick=()=>{try{const s=JSON.parse(localStorage.getItem('geoengine-pilot-camera'));if(!s||![s.position,s.target].every(a=>Array.isArray(a)&&a.length===3&&a.every(Number.isFinite)))return;camera.position.fromArray(s.position);controls.target.fromArray(s.target);controls.update();}catch{record('invalid-saved-camera');}};
  $('pilot-log').onclick=()=>{const network=performance.getEntriesByType('resource').filter(e=>e.name.includes('station-photo-pilot')).map(e=>({url:e.name,initiator:e.initiatorType,duration_ms:e.duration,transfer_bytes:e.transferSize,encoded_bytes:e.encodedBodySize}));const a=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify({config,events,network,note:'ResourceTiming transfer may be zero for browser cache; texture count is not GPU bytes.'},null,2)],{type:'application/json'}));a.href=url;a.download='station-photo-pilot-log.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  record('start');
  return {update(now){if(now-last<200)return;last=now;discover();if(!bindings.length)return;
    const near=Number($('pilot-near-distance').value),far=Number($('pilot-far-distance').value);
    if(!(near>0&&far>near)){$('pilot-status').textContent='解放距離は高画質化距離より大きくしてください';release();return;}
    const distance=box.distanceToPoint(camera.position);
    if(distance>far)release();else if(distance<near&&!high&&!pending&&now>=retryAt)load();
    $('pilot-status').textContent=`対象まで ${distance.toFixed(1)}m / ${high?'元JPEG':pending?'取得中・Low表示':'Low'} / textures ${renderer.info.memory.textures} / 取得 ${events.filter(e=>e.event==='loaded').length} / 解放 ${events.filter(e=>e.event==='release').length}`;
  }};
}
