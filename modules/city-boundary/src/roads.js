'use strict';
/* STEP 1-2. Real OSM road geometry comes only from local, provenance-tagged generated tiles.
 * Never mistake a rendered line for a verified drivable lane or route graph. */
window.createRoadController = function createRoadController(map) {
  const $ = id => document.getElementById(id);
  const empty = {type:'FeatureCollection',features:[]};
  let manifest = null;
  let enabled = true;
  let showWalk = false;
  let active = 0;
  let lastKeys = '';
  let waitTimer = null;
  const cache = new Map();

  function setNotice(t, kind='') {
    $('road-message').textContent = t;
    $('road-message').dataset.kind = kind;
  }
  function setCounter(ways, segments) {
    $('road-count').textContent = Number(ways).toLocaleString('ja-JP');
    $('road-visible').textContent = Number(segments).toLocaleString('ja-JP');
  }
  function remember(key, data) {
    if(cache.has(key))cache.delete(key);
    cache.set(key,data);
    while(cache.size > 45)cache.delete(cache.keys().next().value);
  }
  async function loadTile(tile) {
    if(cache.has(tile.id)) {
      const value = cache.get(tile.id);
      remember(tile.id,value);
      return value;
    }
    const tilePath=tile.file.split('/').map(encodeURIComponent).join('/');
    const response=await fetch('./data/roads/'+tilePath);
    if(!response.ok)throw new Error(`道路タイル ${tile.file}: HTTP ${response.status}`);
    const data=await response.json();
    if(data.type!=='FeatureCollection'||!Array.isArray(data.features))throw new Error(`GeoJSONが不正: ${tile.file}`);
    remember(tile.id,data.features);
    return data.features;
  }
  function setVisibleRoads(features) {
    const src=map.getSource('osm-road-network');
    if(src)src.setData({type:'FeatureCollection',features});
    setCounter(manifest?.way_count || 0,features.length);
  }
  function relevant(tile,bounds) {
    const [w,s,e,n] = tile.bbox;
    return !(e < bounds.getWest() || w > bounds.getEast() || n < bounds.getSouth() || s > bounds.getNorth());
  }
  async function refresh() {
    const id=++active;
    if(!manifest || manifest.status!=='ready')return;
    if(!enabled) {setVisibleRoads([]);setNotice('道路表示：オフ');return;}
    if(map.getZoom()<10.5) {
      setVisibleRoads([]);
      setNotice('道路線はズーム10.5以上で表示します。市内の道路に拡大してください。');
      return;
    }
    const candidates=manifest.tiles.filter(tile=>relevant(tile,map.getBounds()));
    if(candidates.length>48) {
      setVisibleRoads([]);setNotice('表示範囲が広すぎます。もう少し拡大してください。','warn');return;
    }
    if(!candidates.length) {
      setVisibleRoads([]);setNotice(manifest.coverage==='station_test_area'?'福島駅周辺のみ試験取得済みです。':'この地点には抽出済みの道路データがありません。');
      return;
    }
    const key=candidates.map(x=>x.id).sort().join('|')+';walk='+showWalk;
    if(lastKeys===key)return;
    setNotice(`道路タイルを読み込み中（${candidates.length}分割）…`);
    const gathered=await Promise.allSettled(candidates.map(loadTile));
    if(id!==active)return;
    const failures=gathered.filter(r=>r.status==='rejected');
    const features=gathered.flatMap(r=>r.status==='fulfilled'?r.value:[]).filter(f=>showWalk||f.properties?.road_class!=='walk');
    lastKeys=key;
    setVisibleRoads(features);
    if(failures.length) {
      setNotice(`${failures.length}個のタイルが読み込めませんでした。${features.length}区間表示。`,'warn');
    } else {
      setNotice(`OSM実道路 ${features.length.toLocaleString('ja-JP')}区間表示（${candidates.length}タイル）`);
    }
  }
  function queue() {
    lastKeys='';
    clearTimeout(waitTimer);
    waitTimer=setTimeout(()=>refresh().catch(e=>setNotice(e.message,'error')),180);
  }
  function addLayers() {
    map.addSource('osm-road-network',{
      type:'geojson',data:empty,
      attribution:'<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors (ODbL)</a>'
    });
    map.addLayer({id:'roads-major',type:'line',source:'osm-road-network',filter:['==',['get','road_class'],'major'],
      paint:{'line-color':'#dc6743','line-opacity':.84,'line-width':['interpolate',['linear'],['zoom'],10,1,13,2.5,16,5]}});
    map.addLayer({id:'roads-local',type:'line',source:'osm-road-network',filter:['==',['get','road_class'],'local'],
      paint:{'line-color':'#217cba','line-opacity':.76,'line-width':['interpolate',['linear'],['zoom'],10,.75,13,1.8,16,3]}});
    map.addLayer({id:'roads-walk',type:'line',source:'osm-road-network',filter:['==',['get','road_class'],'walk'],
      paint:{'line-color':'#9d55b7','line-opacity':.8,'line-dasharray':[2,2], 'line-width':['interpolate',['linear'],['zoom'],11,.8,15,2.4]}});
  }
  async function init() {
    addLayers();
    $('roads-on').addEventListener('change',e=>{enabled=e.target.checked;queue();});
    $('walk-on').addEventListener('change',e=>{showWalk=e.target.checked;queue();});
    $('reload-roads').addEventListener('click',async()=>{
      lastKeys='';cache.clear();
      await readManifest(true);
      queue();
    });
    map.on('moveend',queue);
    await readManifest(false);
    queue();
  }
  async function readManifest(reload) {
    try {
      const r=await fetch('./data/roads/index.json'+(reload?'?t='+Date.now():''),{cache:'no-store'});
      if(!r.ok)throw new Error('index.json: HTTP '+r.status);
      const index=await r.json();
      if(index.schema!=='therabby.geodata.roads.v1'||!Array.isArray(index.tiles))throw new Error('道路インデックスの形式が不正です');
      manifest=index;
      const coverageLabel=index.coverage==='station_test_area'?'駅周辺テスト':index.coverage==='municipality'?'市内抽出済':index.coverage==='local_json_import'?'範囲限定データ':'範囲未確認';
      $('road-import').textContent=index.status==='ready'?coverageLabel:'未取込';
      $('road-source').textContent=index.status==='ready'?`${index.source} / ${index.boundary_quality==='official_2026'?'正式境界':'暫定境界'}`:'未取込';
      setCounter(index.way_count||0,0);
      if(index.status!=='ready')setNotice('道路は未取込です。まず README のコマンドでOSM道路データを作成してください。','warn');
      else setNotice(index.warning||'実道路データを読み込みました。表示は実道路中心線であり車線や走行可能性は未保証です。',index.warning?'warn':'');
    }catch(e) {
      manifest=null;
      $('road-import').textContent='データ取得失敗';
      $('road-source').textContent='—';
      setNotice(`道路インデックスを読み込めません：${e.message}`,'error');
    }
  }
  return {init};
};
