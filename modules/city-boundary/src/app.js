'use strict';
// STEP 1-1: explicit 2D administrative boundary, not a road network or 3D model.
const $ = id => document.getElementById(id);
const station = [140.4597,37.7548]; // Fukushima Station approx; map navigation marker only
const status = (message,kind='') => { $('status').textContent = message; $('status').className = `notice ${kind}`; };
function geometryPositions(geom){
  const result=[];
  function traverse(a){ if (typeof a?.[0] === 'number' && typeof a[1] === 'number') result.push(a); else if(Array.isArray(a))a.forEach(traverse); }
  traverse(geom.coordinates);return result;
}
function bbox(featureCollection){
  const coords=featureCollection.features.flatMap(f=>geometryPositions(f.geometry));
  if(!coords.length)throw new Error('境界データに座標がありません');
  let minx=Infinity,miny=Infinity,maxx=-Infinity,maxy=-Infinity;
  for(const [x,y] of coords){minx=Math.min(minx,x);miny=Math.min(miny,y);maxx=Math.max(maxx,x);maxy=Math.max(maxy,y);}
  const b=[minx,miny,maxx,maxy];
  if(!(b[0]>139&&b[2]<142&&b[1]>36&&b[3]<40))throw new Error('福島市の座標範囲として不適切です');
  return b;
}
function pointInRing(point,ring){
  let inside=false;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){
    const a=ring[i],b=ring[j];
    if(((a[1]>point[1]) !== (b[1]>point[1])) && point[0] < (b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
  }
  return inside;
}
function insideGeometry(point,g){
  if(g.type==='Polygon')return !!g.coordinates.length && pointInRing(point,g.coordinates[0])&&!g.coordinates.slice(1).some(hole=>pointInRing(point,hole));
  if(g.type==='MultiPolygon')return g.coordinates.some(rings=>insideGeometry(point,{type:'Polygon',coordinates:rings}));
  return false;
}
async function init(){
  let boundary,meta;
  try {
    const [g,m]=await Promise.all([fetch('./data/fukushima_city_boundary.geojson'),fetch('./data/boundary_metadata.json')]);
    if(!g.ok||!m.ok)throw new Error('GeoJSONまたはメタデータを読み込めません');
    [boundary,meta]=await Promise.all([g.json(),m.json()]);
    if(boundary.type!=='FeatureCollection'||!boundary.features.length)throw new Error('GeoJSON形式が不正です');
  }catch(e){
    status(`${e.message}。READMEの手順でHTTPサーバーから起動してください。`,'error');
    $('loading').innerHTML=`<div class="loading-title">DATA LOAD FAILED</div><p>GeoJSONの取得に失敗しました。ローカルHTTPサーバーをご利用ください。</p>`;
    return;
  }
  const bounds=bbox(boundary);
  const isPreview=meta.status!=='official_2026';
  $('quality').textContent=isPreview?'暫定プレビュー':'2026年版 N03';
  $('source-year').textContent=isPreview?'未確認（正式版未導入）':'2026 / 01 / 01';
  $('area').textContent=meta.area_km2_geodesic!=null?`${meta.area_km2_geodesic.toFixed(1)} km²`:'約767.7 km²（参考）';
  $('source-name').textContent=meta.source||'記載なし';
  if(meta.source_page)$('source-link').href=meta.source_page;
  $('source-warning').textContent=meta.warning||(isPreview?'正式データではありません。':'' );
  status(isPreview?'暫定プレビューを表示中。正式な2026年版N03への更新を推奨します。':'2026年版の実データを読み込みました。',''+(isPreview?'warn':''));
  if(typeof maplibregl === 'undefined'){
    $('loading').innerHTML='<div class="loading-title">MAPLIBRE UNAVAILABLE</div><p>地図表示ライブラリを読み込めません。ネットワークを確認してください。</p>';
    status('地図ライブラリを読み込めませんでした。ネット接続が必要です。','error');return;
  }
  const map=new maplibregl.Map({
    container:'map',center:station,zoom:10, minZoom:7,maxZoom:18,pitch:0,bearing:0,
    dragRotate:false,touchPitch:false,
    style:{version:8, sources:{gsi:{type:'raster',tiles:['https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">国土地理院</a>'}},layers:[{id:'gsi-background',type:'raster',source:'gsi'}]},
    attributionControl:true,
  });
  map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');
  map.on('load',()=>{
    map.addSource('fukushima-boundary',{type:'geojson',data:boundary});
    map.addLayer({id:'city-fill',type:'fill',source:'fukushima-boundary',paint:{'fill-color':'#41bf87','fill-opacity':0.14}});
    map.addLayer({id:'city-outline',type:'line',source:'fukushima-boundary',paint:{'line-color':'#047c65','line-width':3,'line-opacity':0.95}});
    // Road layer uses the same WGS84 coordinate space as city boundary.
    if(typeof window.createRoadController==='function'){
      window.createRoadController(map).init().catch(err=>console.error('Road controller',err));
    }
    fit(); $('loading').classList.add('hidden');
  });
  map.on('error',e=>{console.warn('GeoEngine map',e.error);});
  function fit(){map.fitBounds([[bounds[0],bounds[1]],[bounds[2],bounds[3]]],{padding:60,maxZoom:12,duration:900});}
  $('fit').addEventListener('click',fit);
  $('station').addEventListener('click',()=>map.flyTo({center:station,zoom:15,duration:850}));
  $('boundary-on').addEventListener('change',e=>{if(map.getLayer('city-outline'))map.setLayoutProperty('city-outline','visibility',e.target.checked?'visible':'none');});
  $('fill-on').addEventListener('change',e=>{if(map.getLayer('city-fill'))map.setLayoutProperty('city-fill','visibility',e.target.checked?'visible':'none');});
  $('download').addEventListener('click',()=>{
    const blob=new Blob([JSON.stringify(boundary)],{type:'application/geo+json'});
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`fukushima_07201_${isPreview?'preview':'2026'}.geojson`;
    document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),300);
  });
  map.on('click',e=>{
    const pt=[e.lngLat.lng,e.lngLat.lat];
    const inside=boundary.features.some(f=>insideGeometry(pt,f.geometry));
    const label=`${pt[1].toFixed(6)}, ${pt[0].toFixed(6)}　/　${inside?'福島市内':'市域外'}`;
    $('coords').textContent=label;
    new maplibregl.Popup({closeButton:false,maxWidth:'260px'}).setLngLat(pt).setHTML(`<div style="color:#173b38;font-size:12px"><strong>${inside?'福島市内':'市域外'}</strong><br>Lat ${pt[1].toFixed(6)}<br>Lon ${pt[0].toFixed(6)}</div>`).addTo(map);
  });
}
init().catch(e=>{console.error(e);status(e.message,'error');$('loading').textContent='初期化できませんでした。コンソールとREADMEを確認してください。';});
