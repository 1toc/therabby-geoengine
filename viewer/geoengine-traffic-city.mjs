/**
 * GeoEngine traffic lab: limited 3D station overlay.
 * City GLB world coordinates: X east / Y = absolute T.P. m / Z south.
 * Roads carry GSI DEM5A *ground* heights, not surveyed road deck heights.
 * No interpolation across absent DEM samples is presented as measured data.
 */
const LAYERS = [
  {
    kind:'terrain',
    folder:'fukushima-citywide-terrain-glb',
    schema:'therabby.geoengine.citywide-terrain-glb.v0.1'
  },
  {
    kind:'building',
    folder:'fukushima-citywide-lod1-glb',
    schema:'therabby.geoengine.citywide-lod1-glb.v0.1'
  }
];
export const TRAFFIC_3D_RADIUS_M=360;

/** Closest distance from one point to a GeoEngine 1km rectangle. */
export function tileDistance(tile,east,north) {
  if(![tile?.tile_origin_east_m,tile?.tile_origin_north_m,east,north].every(Number.isFinite)) {
    throw new Error('道路・建物・地形タイルのEPSG:6677原点が不明です');
  }
  const size=tile.tile_size_m??1000;
  if(!Number.isFinite(size)||size<=0||size>2000)throw new Error('タイルサイズが未対応です');
  const e=Math.max(tile.tile_origin_east_m,Math.min(east,tile.tile_origin_east_m+size));
  const n=Math.max(tile.tile_origin_north_m-size,Math.min(north,tile.tile_origin_north_m));
  return Math.hypot(east-e,north-n);
}

/** No silent reprojection or unsupported vertical datum fallback. */
export function selectCityTiles(manifest,kind,east,north,radius=TRAFFIC_3D_RADIUS_M,maxTiles=9){
  const spec=LAYERS.find(item=>item.kind===kind);
  if(!spec || !manifest || manifest.schema!==spec.schema ||
      !String(manifest.projected_crs||'').includes('EPSG:6677') ||
      manifest.vertical_datum!=='T.P. (Tokyo Peil)' ||
      !Array.isArray(manifest.tiles)||!['complete','complete_with_gaps','partial'].includes(manifest.status)){
    throw new Error(kind+' GLB目録の座標系・標高基準・形式が未対応です');
  }
  if(![east,north,radius].every(Number.isFinite)||radius<=0||radius>2000){
    throw new RangeError('探索座標・半径が不正です');
  }
  return manifest.tiles.map(tile=>({tile,distance:tileDistance(tile,east,north)}))
    .filter(item=>item.distance<=radius)
    .sort((a,b)=>a.distance-b.distance)
    .slice(0,maxTiles).map(item=>item.tile);
}

/** Nearest sampled OSM-edge DEM5A height (T.P.), not a traffic-surface measurement. */
export function chooseElevationReference(roadTiles,east,north,maxDistance=250){
  if(!Array.isArray(roadTiles)||![east,north,maxDistance].every(Number.isFinite))throw new TypeError('道路標高参照値が不正です');
  let best=null;
  for(const tile of roadTiles){
    if(!tile || tile.projected_crs!=='EPSG:6677')throw new Error('道路座標系が未対応です');
    for(const edge of tile.edges??[]){
      for(let k=0;k<2;k++){
        const height=k===0?edge.ground_height_from_tp_m:edge.ground_height_to_tp_m;
        if(!Number.isFinite(height)||!Array.isArray(edge.points?.[k]))continue;
        const point=edge.points[k];
        const e=tile.tile_origin_east_m+point[0],n=tile.tile_origin_north_m-point[1];
        const dist=Math.hypot(e-east,n-north);
        if(dist<=maxDistance&&(!best||dist<best.distance_m)){
          best={height_tp_m:height,distance_m:dist,source:'GSI DEM5A via OSM road node',
            quality:'ground height; road deck not measured'};
        }
      }
    }
  }
  return best;
}

export function groundFromEdge(edge,fraction=0){
  const a=edge?.ground_height_from_tp_m,b=edge?.ground_height_to_tp_m;
  if(!Number.isFinite(a)||!Number.isFinite(b)||!Number.isFinite(fraction))return null;
  return a+(b-a)*Math.max(0,Math.min(1,fraction));
}

export function disposeCityAssets(group) {
  if(!group)return;
  const meshes=new Set(),materials=new Set(),textures=new Set();
  group.traverse(obj=>{
    if(obj.geometry)meshes.add(obj.geometry);
    for(const material of Array.isArray(obj.material)?obj.material:obj.material?[obj.material]:[]){
      materials.add(material);
      for(const value of Object.values(material))if(value?.isTexture)textures.add(value);
    }
  });
  for(const texture of textures)texture.dispose();
  for(const material of materials)material.dispose();
  for(const mesh of meshes)mesh.dispose();
  group.parent?.remove(group);
}

/** Independent asset loader. Constructs a detached group; caller commits it only on success. */
export async function loadCityAssets({
  THREE,GLTFLoader,centerEast,centerNorth,referenceHeight,
  radius=TRAFFIC_3D_RADIUS_M,
  fetcher=(...args)=>globalThis.fetch(...args),
  signal
}){
  if(![centerEast,centerNorth,referenceHeight].every(Number.isFinite))
    throw new Error('実道路のDEM標高がないため、3D高さ合わせを行いません');
  const group=new THREE.Group();
  group.name='PLATEAU/DEM5A real data; reference altitude subtracted for viewer';
  const stats={terrain:0,building:0,terrain_expected:0,building_expected:0,bytes:0,errors:[]};
  const loader=new GLTFLoader();
  try {
    for(const config of LAYERS) {
      if(signal?.aborted)throw new DOMException('aborted','AbortError');
      const manifestUrl=new URL('../data/derived/'+config.folder+'/tileset.json',import.meta.url);
      const response=await fetcher(manifestUrl,{signal});
      if(!response.ok)throw new Error(config.kind+'目録 HTTP '+response.status);
      const manifest=await response.json();
      const selected=selectCityTiles(manifest,config.kind,centerEast,centerNorth,radius,9);
      stats[config.kind+'_expected']=selected.length;
      if(!selected.length)throw new Error(config.kind+'対象タイルがありません');
      // Sequential fetch/parse avoids large parallel GLB allocations on 8GB clients.
      for(const tile of selected){
        if(signal?.aborted)throw new DOMException('aborted','AbortError');
        try{
          if(typeof tile.glb!=='string'||!Number.isInteger(tile.byte_length)||tile.byte_length<1)
            throw new Error('GLB目録にファイル長情報がありません');
          const glbUrl=new URL(tile.glb,manifestUrl);
          const result=await fetcher(glbUrl,{signal});
          if(!result.ok)throw new Error('HTTP '+result.status);
          const buffer=await result.arrayBuffer();
          if(buffer.byteLength!==tile.byte_length)throw new Error('GLBサイズ不一致');
          const gltf=await loader.parseAsync(buffer,new URL('.',glbUrl).href);
          if(signal?.aborted){
            disposeCityAssets(gltf.scene);
            throw new DOMException('aborted','AbortError');
          }
          gltf.scene.position.set(tile.tile_origin_east_m-centerEast,-referenceHeight,centerNorth-tile.tile_origin_north_m);
          group.add(gltf.scene);
          stats[config.kind]++;
          stats.bytes+=buffer.byteLength;
        }catch(error){
          if(error.name==='AbortError')throw error;
          stats.errors.push(config.kind+'/'+tile.id+': '+error.message);
        }
      }
    }
    if(!stats.terrain||!stats.building)
      throw new Error('実地形と公式建物の両方を読み込めませんでした: '+stats.errors.join('; '));
    return {group,stats,referenceHeight};
  }catch(error){
    disposeCityAssets(group);
    throw error;
  }
}
