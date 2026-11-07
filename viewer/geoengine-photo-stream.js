import * as THREE from 'three';

const mib=1048576;
const estimate=p=>Math.ceil(p.size[0]*p.size[1]*4*4/3);

export async function createPhotoStream({scene,camera,controls,renderer,active,origin,full=false,beforeCameraMove=()=>{}}){
  const base=new URL('../data/derived/station-photo-pilot/',import.meta.url);
  const response=await fetch(new URL(full?'stream-full.json':'stream.json',base));
  if(!response.ok)throw new Error(`写真目録 HTTP ${response.status}`);
  const config=await response.json();
  if(config.schema!=='therabby.station-photo-stream.v0.3'||!config.projected_crs.includes('EPSG:6677')||config.photos.length!==(full?117:10))
    throw new Error('写真目録の形式・座標系が未対応です');
  const areaSize=2*config.area.half_size_m;
  const upgradable=config.photos.filter(p=>p.size.some((size,i)=>size>p.low_size[i])).length;
  const panel=document.createElement('section');
  panel.innerHTML=`<h2>v0.3 / 写真${config.photos.length}枚${full?`（高画質化${upgradable}枚）`:''}</h2><button id="stream-area">${areaSize}m区域</button> <button id="stream-near">選択写真へ接近</button> <button id="stream-far">離脱</button>
    <label>写真<select id="stream-target"></select></label><label class="switch"><input type="checkbox" id="stream-boundary" ${full?'':'checked'}>${areaSize}m境界</label>
    <label>高画質にする距離 m<input id="stream-near-distance" type="number" min="1" value="${config.near_m}"></label>
    <label>Lowへ戻す距離 m<input id="stream-far-distance" type="number" min="2" value="${config.far_m}"></label>
    <label>同時取得上限<input id="stream-concurrent" type="number" min="1" max="10" value="3"></label>
    <label>画像容量予算 MiB<input id="stream-budget" type="number" min="1" value="${config.budget_mib}"></label>
    <label>再訪用JPEG容量 MiB<input id="stream-jpeg-cache" type="number" min="0" max="32" value="4"></label>
    <button id="stream-save">視点保存</button> <button id="stream-restore">視点復元</button>
    <button id="stream-fail">次の取得を404で試験</button> <button id="stream-stress">30往復試験</button>
    <button id="stream-image">現在の3D画面PNGを保存</button> <button id="stream-log">通信・負荷JSONを保存</button><p class="fine" id="stream-status" role="status"></p>`;
  document.querySelector('aside').prepend(panel);
  const $=id=>document.getElementById(id),events=[],samples=[];
  panel.hidden=true;
  const toggle=$('stream-settings-toggle');
  if(toggle){toggle.hidden=false;toggle.onclick=()=>{panel.hidden=!panel.hidden;
    toggle.textContent=panel.hidden?'写真の詳細設定を表示':'写真の詳細設定を閉じる';};}
  const states=config.photos.map((photo,index)=>({photo,index,box:new THREE.Box3(),bindings:[],surfaces:[],root:null,
    texture:null,asset:null,pending:null,sequence:0,lastAccess:0,retryAt:0,blockedUntil:0,distance:Infinity,visible:false,
    upgrade:!full||photo.size.some((size,i)=>size>photo.low_size[i])}));
  const compressedCache=new Map();
  $('stream-target').replaceChildren(...states.map((s,i)=>{const o=document.createElement('option');o.value=String(i);o.textContent=`${i+1}: ${s.photo.photo_id.slice(0,8)} / ${s.photo.size.join('×')}px`;return o;}));
  const area=config.area,center=new THREE.Vector3(area.center_east_m-origin.east,72,origin.north-area.center_north_m);
  const half=areaSize/2,points=[[-half,-half],[half,-half],[half,half],[-half,half],[-half,-half]].map(([x,z])=>new THREE.Vector3(center.x+x,72,center.z+z));
  const boundary=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:0xff55ff,depthTest:false}));
  boundary.renderOrder=10;boundary.visible=!full;scene.add(boundary);
  let inFlight=0,peakInFlight=0,networkInFlight=0,peakNetwork=0,requests=0,cacheHits=0,
    loaded=0,failed=0,aborted=0,transferred=0,lastUpdate=0,
    next404=false,stress=null,started=performance.now();
  const record=(event,s,extra={})=>events.push({event,photo_id:s?.photo.photo_id??null,time_ms:Math.round(performance.now()-started),
    textures:renderer.info.memory.textures,in_flight:inFlight,...extra});
  const held=()=>states.reduce((sum,s)=>sum+(s.texture?estimate(s.asset):0),0);
  const chosen=s=>({...s.photo,base,kind:'official'});
  const frustum=new THREE.Frustum(),projection=new THREE.Matrix4();
  const cacheBytes=()=>[...compressedCache.values()].reduce((sum,item)=>sum+item.bytes.byteLength,0);
  function trimCache(){
    const limit=Math.max(0,Number($('stream-jpeg-cache').value)||0)*mib;
    while(cacheBytes()>limit){
      const oldest=[...compressedCache].sort((a,b)=>a[1].last-b[1].last)[0];
      if(!oldest)break;compressedCache.delete(oldest[0]);record('jpeg-cache-evict',null,{photo_id:oldest[0]});
    }
  }
  function restore(s){
    for(const b of s.bindings){b.material.userData.officialPhotoMap=b.low;
      b.material.map=$('building-texture').checked?b.low:null;b.material.needsUpdate=true;}
  }
  function release(s,reason){
    if(s.pending){s.pending.abort();s.pending=null;s.sequence++;aborted++;record('abort',s,{reason});}
    if(!s.texture)return;
    restore(s);const bitmap=s.texture.image;s.texture.dispose();bitmap?.close?.();s.texture=null;s.asset=null;
    record('release',s,{reason,estimated_held_bytes:held()});
  }
  function discover(s){
    const root=active.get(`photo-low:${s.photo.tile_id}`)?.root;
    if(s.root===root&&s.bindings.length)return;
    release(s,'tile-change');s.root=root;s.bindings=[];s.surfaces=[];s.box.makeEmpty();
    root?.updateMatrixWorld(true);
    root?.traverse(object=>{
      const materials=Array.isArray(object.material)?object.material:object.material?[object.material]:[];
      for(const material of materials)if(material.name===s.photo.material&&material.userData.officialPhotoMap){
        if(!s.bindings.some(b=>b.material===material))s.bindings.push({material,low:material.userData.officialPhotoMap});
        if(object.geometry){s.surfaces.push(object);object.geometry.computeBoundingBox();s.box.union(object.geometry.boundingBox.clone().applyMatrix4(object.matrixWorld));}
      }
    });
  }
  function evictFor(bytes,protectedState,budget){
    if(bytes>budget)return false;
    const victims=states.filter(s=>s.texture&&s!==protectedState&&(!s.visible||s.distance>protectedState.distance))
      .sort((a,b)=>Number(a.visible)-Number(b.visible)||b.distance-a.distance||a.lastAccess-b.lastAccess);
    for(const s of victims){if(held()+bytes<=budget)break;release(s,'lru-budget');s.blockedUntil=performance.now()+3000;}
    return held()+bytes<=budget;
  }
  async function fetchPhoto(s){
    const controller=new AbortController(),sequence=++s.sequence;s.pending=controller;
    const asset=chosen(s),cacheKey=asset.sha256;
    const test404=next404;next404=false;
    const url=new URL(test404?'missing-test.jpg':asset.jpeg,asset.base);
    inFlight++;peakInFlight=Math.max(peakInFlight,inFlight);
    try{
      let bytes;
      const cached=test404?null:compressedCache.get(cacheKey);
      if(cached){cached.last=performance.now();bytes=cached.bytes;cacheHits++;record('jpeg-cache-hit',s);}
      else{
        requests++;networkInFlight++;peakNetwork=Math.max(peakNetwork,networkInFlight);
        record('request',s,{url:url.href,estimated_bytes:estimate(asset),kind:asset.kind,test404});
        try{const response=await fetch(url,{signal:controller.signal});
          if(!response.ok)throw new Error(`JPEG HTTP ${response.status}`);
          bytes=await response.arrayBuffer();
        }finally{networkInFlight--;}
      }
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      if(hash!==asset.sha256)throw new Error('JPEG SHA mismatch');
      if(!cached&&!controller.signal.aborted){
        transferred+=bytes.byteLength;
        compressedCache.set(cacheKey,{bytes,last:performance.now()});trimCache();
      }
      const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/jpeg'}),{imageOrientation:'none'});
      if(s.pending!==controller||s.sequence!==sequence||controller.signal.aborted||!s.bindings.length||
        chosen(s).sha256!==asset.sha256||s.distance>Number($('stream-far-distance').value)){
        bitmap.close();record('discard-stale',s);return;
      }
      const currentBudget=Math.max(1,Number($('stream-budget').value)||128)*mib;
      if(!evictFor(estimate(asset),s,currentBudget)){bitmap.close();record('budget-reject',s);s.blockedUntil=performance.now()+3000;return;}
      const texture=s.bindings[0].low.clone();texture.source=new THREE.Source(bitmap);texture.flipY=false;
      texture.userData.dynamicHigh=true;
      const anisotropy=document.getElementById('photo-anisotropy')?.value??'auto';
      texture.anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),anisotropy==='auto'?8:Number(anisotropy));
      texture.minFilter=document.getElementById('photo-filter')?.value==='linear'?THREE.LinearFilter:THREE.LinearMipmapLinearFilter;
      texture.needsUpdate=true;
      s.texture=texture;s.asset=asset;s.lastAccess=performance.now();
      for(const b of s.bindings){b.material.userData.officialPhotoMap=texture;
        b.material.map=$('building-texture').checked?texture:null;b.material.needsUpdate=true;}
      loaded++;
      record('loaded',s,{kind:asset.kind,bytes:bytes.byteLength,width:bitmap.width,height:bitmap.height,estimated_held_bytes:held()});
    }catch(error){if(error.name!=='AbortError'){
      failed++;s.retryAt=performance.now()+10000;record('failure',s,{message:error.message});
    }}finally{if(s.pending===controller)s.pending=null;inFlight--;}
  }
  function move(near){beforeCameraMove();const s=states[Number($('stream-target').value)];discover(s);if(s.box.isEmpty())return;
    let best=null;
    for(const mesh of s.surfaces){const geometry=mesh.geometry,positions=geometry.getAttribute('position'),indices=geometry.index;
      const triangles=indices?indices.count/3:positions.count/3;
      for(let i=0;i<triangles;i++){
        const read=j=>new THREE.Vector3().fromBufferAttribute(positions,indices?indices.getX(3*i+j):3*i+j).applyMatrix4(mesh.matrixWorld);
        const a=read(0),b=read(1),c=read(2),normal=new THREE.Vector3().crossVectors(b.clone().sub(a),c.clone().sub(a));
        const area=normal.length();if(area<.01)continue;normal.normalize();
        const score=area*(Math.abs(normal.y)<.7?3:1);
        if(!best||score>best.score)best={score,center:a.add(b).add(c).multiplyScalar(1/3),normal};
      }
    }
    const c=best?.center??s.box.getCenter(new THREE.Vector3());
    if(best&&best.normal.dot(c.clone().sub(s.box.getCenter(new THREE.Vector3())))<0)best.normal.negate();
    controls.target.copy(c);
    camera.position.copy(c).add(best?best.normal.clone().multiplyScalar(near?25:130):new THREE.Vector3(0,8,near?25:130));
    camera.position.y+=3;controls.update();}
  $('stream-near').onclick=()=>move(true);$('stream-far').onclick=()=>move(false);
  $('stream-area').onclick=()=>{beforeCameraMove();controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(0,160,100));controls.update();};
  $('stream-boundary').onchange=()=>boundary.visible=$('stream-boundary').checked;
  $('stream-save').onclick=()=>localStorage.setItem('geoengine-stream-camera',JSON.stringify({position:camera.position.toArray(),target:controls.target.toArray()}));
  $('stream-restore').onclick=()=>{try{const saved=JSON.parse(localStorage.getItem('geoengine-stream-camera'));
    if(!saved||![saved.position,saved.target].every(a=>Array.isArray(a)&&a.length===3&&a.every(Number.isFinite)))return;
    beforeCameraMove();camera.position.fromArray(saved.position);controls.target.fromArray(saved.target);controls.update();}catch{record('invalid-camera',null);}};
  $('stream-fail').onclick=()=>{next404=true;record('inject-next-404',null);};
  $('stream-stress').onclick=()=>{stress={step:0,next:0};record('stress-start',null);};
  $('stream-image').onclick=()=>{
    renderer.render(scene,camera);
    const gl=renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
    const pixels=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;
    const context=canvas.getContext('2d'),image=context.createImageData(w,h);
    for(let y=0;y<h;y++)image.data.set(pixels.subarray((h-y-1)*w*4,(h-y)*w*4),y*w*4);
    context.putImageData(image,0,0);
    canvas.toBlob(blob=>{
    if(!blob){record('screenshot-failed',null);return;}
    const url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download='station-photo-stream-current.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    },'image/png');
  };
  $('stream-log').onclick=()=>{const network=performance.getEntriesByType('resource').filter(e=>e.name.includes('station-photo-pilot'))
    .map(e=>({url:e.name,duration_ms:e.duration,transfer_bytes:e.transferSize,encoded_bytes:e.encodedBodySize}));
    const payload={schema:'therabby.station-photo-stream-observation.v0.3',config,metrics:{elapsed_ms:performance.now()-started,
      requests,cache_hits:cacheHits,loaded,failed,aborted,transferred_jpeg_bytes:transferred,
      peak_in_flight:peakInFlight,peak_http_in_flight:peakNetwork,
      in_flight:inFlight,held_count:states.filter(s=>s.texture).length,estimated_held_bytes:held(),
      compressed_jpeg_cache_bytes:cacheBytes(),renderer_texture_count:renderer.info.memory.textures,
      js_heap_bytes:performance.memory?.usedJSHeapSize??null},
      states:states.map(s=>({photo_id:s.photo.photo_id,status:s.texture?'high':s.pending?'loading':'low',
        last_access_ms:s.lastAccess-started,binding_count:s.bindings.length,distance_m:s.distance})),samples,events,network,
      note:'Estimated image bytes are RGBA8+mip; renderer count is not GPU memory. HTTP transferSize reflects browser cache.'};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='station-photo-stream-log.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  record('start',null);
  return {update(now){if(now-lastUpdate<180)return;lastUpdate=now;
    if(document.getElementById('station-style')?.value==='clean'){
      for(const s of states)release(s,'estimated-style');
      $('stream-status').textContent='推定スタイル表示中：元JPEGの追加取得を停止';
      return;
    }
    camera.updateMatrixWorld();projection.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);
    frustum.setFromProjectionMatrix(projection);
    for(const s of states){discover(s);s.distance=s.box.isEmpty()?Infinity:s.box.distanceToPoint(camera.position);
      s.visible=!s.box.isEmpty()&&frustum.intersectsBox(s.box);}
    const near=Number($('stream-near-distance').value),far=Number($('stream-far-distance').value),
      limit=Math.min(10,Math.max(1,Number($('stream-concurrent').value)||3)),
      budget=Math.max(1,Number($('stream-budget').value)||128)*mib;
    if(!(near>0&&far>near)){$('stream-status').textContent='解放距離は高画質化距離より大きくしてください';return;}
    for(const s of states)if(s.distance>far)release(s,'distance');
    for(const s of states.filter(s=>s.texture).sort((a,b)=>a.lastAccess-b.lastAccess)){
      if(held()<=budget)break;
      release(s,'budget-reduced');s.blockedUntil=now+3000;
    }
    if(stress&&now>=stress.next){$('stream-target').value=String(Math.floor(stress.step/2)%10);
      move(stress.step%2===0);stress.step++;stress.next=now+320;
      if(stress.step>=60){record('stress-complete',null);stress=null;}}
    const queue=states.filter(s=>s.upgrade&&s.bindings.length&&(!full||s.visible)&&!s.texture&&!s.pending&&s.distance<near&&now>=s.retryAt&&now>=s.blockedUntil)
      .sort((a,b)=>a.distance-b.distance);
    for(const s of queue){if(inFlight>=limit)break;if(!evictFor(estimate(chosen(s)),s,budget)){
      record('budget-reject',s);s.blockedUntil=now+3000;continue;}fetchPhoto(s);}
    for(const s of states)if(s.texture&&s.distance<near)s.lastAccess=now;
    trimCache();
    if(samples.length<3000)samples.push({time_ms:Math.round(now-started),held_count:states.filter(s=>s.texture).length,
      in_flight:inFlight,estimated_held_bytes:held(),textures:renderer.info.memory.textures,
      fps:document.getElementById('fps')?.textContent??null});
    $('stream-status').textContent=`写真 ${states.filter(s=>s.texture).length}枚 高画質 / HTTP ${networkInFlight}/${limit} (最大${peakNetwork}) / 取得${loaded}・再訪${cacheHits}・失敗${failed}・中断${aborted} / 推定${(held()/mib).toFixed(1)}/${(budget/mib).toFixed(0)}MiB / JPEG保管${(cacheBytes()/mib).toFixed(1)}MiB / textures ${renderer.info.memory.textures}${stress?' / 30往復中':''}`;
  }};
}
