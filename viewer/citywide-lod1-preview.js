'use strict';
(() => {
  const $=id=>document.getElementById(id), station=[140.4597,37.7548];
  const root='../data/derived/fukushima-citywide-lod1-v2/';
  const CACHE_LIMIT=30, REQUEST_LIMIT=36;
  let map, tileset, boundary, enabled=true, serial=0, lastKey='', timer=0, terrainEnabled=false;
  const cache=new Map();
  const setStatus=(text,kind='')=>{$('status').textContent=text;$('status').className=`note ${kind}`;};

  function forward(lat,lon){
    const a=6378137, invF=298.257222101, scale=.9999, e2=2/invF-1/(invF*invF), ep2=e2/(1-e2);
    const phi=lat*Math.PI/180, lam=lon*Math.PI/180, lam0=(139+50/60)*Math.PI/180, phi0=36*Math.PI/180;
    const meridional=p=>a*((1-e2/4-3*e2*e2/64-5*e2*e2*e2/256)*p-(3*e2/8+3*e2*e2/32+45*e2*e2*e2/1024)*Math.sin(2*p)+(15*e2*e2/256+45*e2*e2*e2/1024)*Math.sin(4*p)-(35*e2*e2*e2/3072)*Math.sin(6*p));
    const s=Math.sin(phi),c=Math.cos(phi),n=a/Math.sqrt(1-e2*s*s),t=Math.tan(phi)**2,cc=ep2*c*c,aa=(lam-lam0)*c;
    const east=scale*n*(aa+(1-t+cc)*aa**3/6+(5-18*t+t*t+72*cc-58*ep2)*aa**5/120);
    const north=scale*(meridional(phi)-meridional(phi0)+n*Math.tan(phi)*(aa**2/2+(5-t+9*cc+4*cc*cc)*aa**4/24+(61-58*t+t*t+600*cc-330*ep2)*aa**6/720));
    return [east,north];
  }
  function inverse(east,north){
    let lat=37.8,lon=140.4;
    for(let i=0;i<5;i++){
      const [e,n]=forward(lat,lon),[el,nl]=forward(lat+1e-5,lon),[eo,no]=forward(lat,lon+1e-5);
      const a=(el-e)/1e-5,b=(eo-e)/1e-5,c=(nl-n)/1e-5,d=(no-n)/1e-5,det=a*d-b*c;
      if(!Number.isFinite(det)||Math.abs(det)<1e-8)throw new Error('EPSG:6677の逆変換に失敗しました');
      const de=east-e,dn=north-n;lat+=(d*de-b*dn)/det;lon+=(-c*de+a*dn)/det;
    }
    return [lon,lat];
  }
  function tileBounds(tile){
    const [tx,ty]=tile.id.split('_').map(Number);
    return [tx*1000,ty*1000,(tx+1)*1000,(ty+1)*1000];
  }
  function candidates(){
    const b=map.getBounds(), corners=[[b.getWest(),b.getSouth()],[b.getWest(),b.getNorth()],[b.getEast(),b.getSouth()],[b.getEast(),b.getNorth()]].map(([lon,lat])=>forward(lat,lon));
    const xs=corners.map(p=>p[0]),ys=corners.map(p=>p[1]);
    const minX=Math.floor(Math.min(...xs)/1000)-1,maxX=Math.floor(Math.max(...xs)/1000)+1;
    const minY=Math.floor(Math.min(...ys)/1000)-1,maxY=Math.floor(Math.max(...ys)/1000)+1;
    return tileset.tiles.filter(t=>{const [x,y]=t.id.split('_').map(Number);return x>=minX&&x<=maxX&&y>=minY&&y<=maxY;});
  }
  function ringToLngLat(ring,tile){
    const [tx,ty]=tile.id.split('_').map(Number),e0=tile.tile_origin_east_m??tx*1000,n0=tile.tile_origin_north_m??(ty+1)*1000;
    return ring.map(([x,z])=>inverse(e0+x,n0-z));
  }
  function featureOf(building,tile){
    const rings=[ringToLngLat(building.footprint,tile),...(building.holes||[]).map(r=>ringToLngLat(r,tile))];
    return {type:'Feature',id:building.id,properties:{height_m:building.height_m,base_elevation_m:building.base_elevation_m,quality:building.height_quality,ground_quality:building.ground_height_quality,source:building.source},geometry:{type:'Polygon',coordinates:rings}};
  }
  async function loadTile(tile){
    if(cache.has(tile.id)){const value=cache.get(tile.id);cache.delete(tile.id);cache.set(tile.id,value);return value;}
    const response=await fetch(root+tile.path.split('/').map(encodeURIComponent).join('/'));
    if(!response.ok)throw new Error(`タイル ${tile.id} を取得できません（HTTP ${response.status}）`);
    const data=await response.json();
    if(!Array.isArray(data.buildings))throw new Error(`建物タイル ${tile.id} の形式が不正です`);
    const features=data.buildings.map(b=>featureOf(b,tile));
    cache.set(tile.id,features);while(cache.size>CACHE_LIMIT)cache.delete(cache.keys().next().value);
    return features;
  }
  async function refresh(){
    const id=++serial;
    if(!enabled){map.getSource('plateau-buildings')?.setData({type:'FeatureCollection',features:[]});$('loaded-tiles').textContent='0';$('visible-buildings').textContent='0';setStatus('建物の表示をオフにしました。');return;}
    if(map.getZoom()<15){map.getSource('plateau-buildings')?.setData({type:'FeatureCollection',features:[]});$('loaded-tiles').textContent='0';$('visible-buildings').textContent='0';setStatus('DEM5A地形と建物はズーム15以上で表示します。駅周辺ボタンから拡大できます。');return;}
    const selected=candidates();
    if(selected.length>REQUEST_LIMIT){setStatus(`表示範囲に${selected.length}タイルあります。もう少し拡大してください。`,'warn');return;}
    const key=selected.map(t=>t.id).sort().join('|');if(key===lastKey)return;
    setStatus(`建物タイルを読み込み中（${selected.length}タイル）…`);
    const results=await Promise.allSettled(selected.map(loadTile));if(id!==serial)return;
    const features=results.flatMap(r=>r.status==='fulfilled'?r.value:[]).filter(f=>Number.isFinite(f.properties.base_elevation_m));
    map.getSource('plateau-buildings')?.setData({type:'FeatureCollection',features});
    $('loaded-tiles').textContent=String(results.filter(r=>r.status==='fulfilled').length);
    $('visible-buildings').textContent=features.length.toLocaleString('ja-JP');lastKey=key;
    const errors=results.filter(r=>r.status==='rejected');
    if(errors.length)setStatus(`${errors.length}タイルの読み込みに失敗しました。${features.length.toLocaleString('ja-JP')}棟を表示中。`,'warn');
    else setStatus(`${features.length.toLocaleString('ja-JP')}棟を地形に合わせて表示中。標高欠損の建物は非表示です。`);
  }
  function queue(){clearTimeout(timer);timer=setTimeout(()=>refresh().catch(e=>setStatus(e.message,'error')),180);}
  function syncTerrain(){
    const shouldEnable=map.getZoom()>=15;
    if(shouldEnable&&!terrainEnabled){map.setTerrain({source:'gsi-dem5a',exaggeration:1});terrainEnabled=true;}
    else if(!shouldEnable&&terrainEnabled){map.setTerrain(null);terrainEnabled=false;}
  }
  async function init(){
    try{
      const [tm,bm]=await Promise.all([fetch(root+'tileset.json'),fetch('../modules/city-boundary/data/fukushima_city_boundary.geojson')]);
      if(!tm.ok||!bm.ok)throw new Error('市全域タイルまたは行政区域を取得できません');
      [tileset,boundary]=await Promise.all([tm.json(),bm.json()]);
      if(!tileset.tiles?.length||tileset.projected_crs.indexOf('EPSG:6677')<0)throw new Error('タイル一覧または座標系の情報が不正です');
      $('building-count').textContent=Number(tileset.statistics.tiled_buildings).toLocaleString('ja-JP')+'棟';
      $('tile-count').textContent=tileset.tiles.length.toLocaleString('ja-JP')+'（1km）';
      $('terrain-count').textContent=Number(tileset.statistics.base_elevation_sampled||0).toLocaleString('ja-JP')+'棟';
      if(typeof maplibregl==='undefined')throw new Error('地図ライブラリを読み込めません。ネット接続を確認してください');
      map=new maplibregl.Map({container:'map',center:station,zoom:11,pitch:45,bearing:-12,minZoom:7,maxZoom:19,style:{version:8,sources:{gsi:{type:'raster',tiles:['https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noreferrer">国土地理院</a>'}},layers:[{id:'gsi',type:'raster',source:'gsi'}]},attributionControl:true});
      map.addControl(new maplibregl.NavigationControl(),'top-right');
      map.on('load',()=>{
        map.addSource('fukushima-boundary',{type:'geojson',data:boundary});
        map.addLayer({id:'city-fill',type:'fill',source:'fukushima-boundary',paint:{'fill-color':'#51b98c','fill-opacity':.08}});
        map.addLayer({id:'city-edge',type:'line',source:'fukushima-boundary',paint:{'line-color':'#65c8a6','line-width':1.5,'line-opacity':.8}});
        map.addSource('plateau-buildings',{type:'geojson',data:{type:'FeatureCollection',features:[]},attribution:'Project PLATEAU / 福島市'});
        if(tileset.terrain?.tile_template){map.addSource('gsi-dem5a',{type:'raster-dem',tiles:[root+tileset.terrain.tile_template],tileSize:256,minzoom:15,maxzoom:15,encoding:'mapbox',bounds:[140.2292804,37.6242045,140.5700106,37.9766444],attribution:'<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noreferrer">© 国土地理院 DEM5A</a>'});}
        map.addLayer({id:'plateau-extrusions',type:'fill-extrusion',source:'plateau-buildings',paint:{'fill-extrusion-color':['interpolate',['linear'],['get','height_m'],3,'#a8d7c4',12,'#4bb698',35,'#247d78',80,'#235b70'],'fill-extrusion-height':['max',2,['get','height_m']],'fill-extrusion-base':0,'fill-extrusion-opacity':.86,'fill-extrusion-vertical-gradient':true}});
        map.on('click','plateau-extrusions',e=>{const f=e.features?.[0];if(!f)return;new maplibregl.Popup().setLngLat(e.lngLat).setHTML(`<b>PLATEAU LOD1</b><br>高さ: ${Number(f.properties.height_m).toFixed(1)} m<br>基部標高: T.P. ${Number(f.properties.base_elevation_m).toFixed(2)} m<br>地形: ${f.properties.ground_quality}`).addTo(map);});
        map.on('mouseenter','plateau-extrusions',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','plateau-extrusions',()=>map.getCanvas().style.cursor='');
        map.on('moveend',()=>{syncTerrain();queue();});map.on('zoomend',()=>{syncTerrain();queue();});$('loading').classList.add('hidden');syncTerrain();queue();
      });
      $('station').addEventListener('click',()=>{map.flyTo({center:station,zoom:15.4,pitch:58,bearing:-18,duration:900});});
      $('city').addEventListener('click',()=>{map.fitBounds([[140.2292804,37.6242045],[140.5700106,37.9766444]],{padding:45,maxZoom:10.4,pitch:35,duration:850});});
      $('buildings').addEventListener('change',e=>{enabled=e.target.checked;lastKey='';queue();});
      map.on('error',e=>console.warn('Citywide preview map',e.error));
    }catch(e){console.error(e);$('loading').innerHTML=`<div>DATA LOAD FAILED</div><p>${e.message}</p>`;setStatus(e.message,'error');}
  }
  init();
})();
