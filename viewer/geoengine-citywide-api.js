// Read-only citywide GeoEngine road data. Coordinates are JGD2011 / EPSG:6677 metres.
export const CITYWIDE_CRS = 'EPSG:6677';

export function projectFukushima(lat, lon) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < 37 || lat > 39 || lon < 139 || lon > 142)
    throw new RangeError('福島周辺の緯度・経度を入力してください');
  const a=6378137, invF=298.257222101, k=.9999, e2=2/invF-1/(invF*invF), ep2=e2/(1-e2);
  const phi=lat*Math.PI/180, lam=lon*Math.PI/180, lam0=(139+50/60)*Math.PI/180, phi0=36*Math.PI/180;
  const meridional=p=>a*((1-e2/4-3*e2*e2/64-5*e2**3/256)*p-(3*e2/8+3*e2*e2/32+45*e2**3/1024)*Math.sin(2*p)+(15*e2*e2/256+45*e2**3/1024)*Math.sin(4*p)-(35*e2**3/3072)*Math.sin(6*p));
  const s=Math.sin(phi), c=Math.cos(phi), n=a/Math.sqrt(1-e2*s*s), t=Math.tan(phi)**2, cc=ep2*c*c, aa=(lam-lam0)*c;
  return [k*n*(aa+(1-t+cc)*aa**3/6+(5-18*t+t*t+72*cc-58*ep2)*aa**5/120),
    k*(meridional(phi)-meridional(phi0)+n*Math.tan(phi)*(aa**2/2+(5-t+9*cc+4*cc*cc)*aa**4/24+(61-58*t+t*t+600*cc-330*ep2)*aa**6/720))];
}

function closestOnSegment(e, n, a, b) {
  const dx=b[0]-a[0], dy=b[1]-a[1], len=dx*dx+dy*dy;
  const t=len ? Math.max(0,Math.min(1,((e-a[0])*dx+(n-a[1])*dy)/len)) : 0;
  const east=a[0]+t*dx, north=a[1]+t*dy;
  return {east_m:east,north_m:north,distance_m:Math.hypot(e-east,n-north),fraction:t};
}

export class CitywideRoadProvider {
  constructor(manifestUrl='../data/derived/fukushima-citywide-roads-v1/tileset.json', fetcher=fetch) {
    this.manifestUrl=new URL(manifestUrl,import.meta.url);
    this.fetcher=fetcher;
    this.manifest=null;
    this.tiles=new Map();
    this.pending=new Map();
    this.maxCachedTiles=24;
  }
  async loadMap() {
    if (this.manifest) return this.manifest;
    const response=await this.fetcher(this.manifestUrl);
    if (!response.ok) throw new Error(`道路目録 HTTP ${response.status}`);
    const manifest=await response.json();
    if (manifest.schema!=='therabby.geoengine.citywide-road-tiles.v0.1' ||
        manifest.status!=='complete' || !manifest.projected_crs?.includes(CITYWIDE_CRS) ||
        manifest.tile_size_m!==1000) throw new Error('道路データの形式・座標系が未対応です');
    this.manifest=manifest;
    this.byId=new Map(manifest.tiles.map(tile=>[tile.id,tile]));
    return manifest;
  }
  tileIdAt(east,north) { return `${Math.floor(east/1000)}_${Math.floor(north/1000)}`; }
  async loadTile(id) {
    await this.loadMap();
    if (this.tiles.has(id)) {
      const tile=this.tiles.get(id); this.tiles.delete(id); this.tiles.set(id,tile); return tile;
    }
    if (this.pending.has(id)) return this.pending.get(id);
    const meta=this.byId.get(id);
    if (!meta) return null;
    const task=(async()=>{
      const response=await this.fetcher(new URL(meta.path,this.manifestUrl));
      if (!response.ok) throw new Error(`道路タイル ${id} HTTP ${response.status}`);
      const data=await response.json();
      if (data.schema!=='therabby.geoengine.citywide-road-tile.v0.1' || data.tile_id!==id ||
          data.projected_crs!==CITYWIDE_CRS || data.edges.length!==meta.edge_count)
        throw new Error(`道路タイル ${id} の形式が不正です`);
      this.tiles.set(id,data);
      while(this.tiles.size>this.maxCachedTiles) this.tiles.delete(this.tiles.keys().next().value);
      return data;
    })();
    this.pending.set(id,task);
    try { return await task; } finally { this.pending.delete(id); }
  }
  async nearestRoad(east,north,maxDistance_m=50) {
    if (![east,north,maxDistance_m].every(Number.isFinite) || maxDistance_m<0 || maxDistance_m>1000)
      throw new RangeError('投影座標または探索距離が不正です');
    await this.loadMap();
    const tx=Math.floor(east/1000), ty=Math.floor(north/1000), radius=Math.ceil(maxDistance_m/1000)+1;
    const ids=[];
    for(let x=tx-radius;x<=tx+radius;x++)for(let y=ty-radius;y<=ty+radius;y++){
      const id=`${x}_${y}`;if(this.byId.has(id))ids.push(id);
    }
    const tiles=await Promise.all(ids.map(id=>this.loadTile(id)));
    let best=null;
    for (const tile of tiles) for (const edge of tile.edges) {
      const toAbsolute=([x,z])=>[tile.tile_origin_east_m+x,tile.tile_origin_north_m-z];
      const point=closestOnSegment(east,north,toAbsolute(edge.points[0]),toAbsolute(edge.points[1]));
      if(point.distance_m>maxDistance_m || (best && point.distance_m>=best.distance_m))continue;
      best={...point,id:edge.id,source_way_id:edge.source_way_id,from_node:edge.from_node,
        to_node:edge.to_node,name:edge.name,highway:edge.highway,oneway_osm_tag:edge.oneway_osm_tag,
        bridge_osm_tag:edge.bridge_osm_tag,tunnel_osm_tag:edge.tunnel_osm_tag,
        width_m:edge.width_m,width_quality:edge.width_quality,
        ground_height_tp_m:Number.isFinite(edge.ground_height_from_tp_m)&&Number.isFinite(edge.ground_height_to_tp_m)
          ? edge.ground_height_from_tp_m+(edge.ground_height_to_tp_m-edge.ground_height_from_tp_m)*point.fraction : null,
        ground_height_quality:edge.ground_height_quality,road_deck_height_m:null,
        legal_drivability:null,collision_ready:false,source:'OpenStreetMap',tile_id:tile.tile_id};
    }
    return best;
  }
  dispose(){this.tiles.clear();this.pending.clear();}
}
