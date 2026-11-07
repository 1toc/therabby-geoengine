// Read-only GeoEngine road contract for a simulator consumer. No vehicle physics.
export class RoadTileProvider {
  constructor(baseUrl,manifest) {
    this.baseUrl=baseUrl;
    this.manifest=manifest;
    this.network=null;
    this.nodes=new Map();
    this.surfaceCache=new Map();
    this.extentCache=new Map();
    this.terrain=null;
  }

  async loadTerrain() {
    if(this.terrain||!this.manifest.terrain_grid)return this.terrain;
    const response=await fetch(this.baseUrl+this.manifest.terrain_grid);
    if(!response.ok)throw new Error(`Terrain grid HTTP ${response.status}`);
    const grid=await response.json();
    if(grid.schema!=='therabby.geoengine.terrain-grid.v0.1'||
       grid.area_id!==this.manifest.area.id||
       !grid.vertical_datum.startsWith('T.P. (Tokyo Peil)'))
      throw new Error('Unsupported terrain grid or vertical datum');
    this.terrain=grid;
    return grid;
  }

  terrainHeightAt(x,z) {
    const grid=this.terrain;
    if(!grid)return null;
    const [x0,z0,x1,z1]=grid.bounds;
    if(x<x0||x>x1||z<z0||z>z1)return null;
    const u=(x-x0)/grid.step_m,v=(z-z0)/grid.step_m;
    const ix=Math.min(Math.floor(u),grid.heights_relative_m[0].length-2);
    const iz=Math.min(Math.floor(v),grid.heights_relative_m.length-2);
    const fx=u-ix,fz=v-iz,h=grid.heights_relative_m;
    const relative=((h[iz][ix]*(1-fx)+h[iz][ix+1]*fx)*(1-fz)+
                    (h[iz+1][ix]*(1-fx)+h[iz+1][ix+1]*fx)*fz);
    return {height_m:relative,height_tp_m:relative+grid.height_origin_tp_m,
      quality:grid.height_quality,vertical_datum:grid.vertical_datum,
      road_deck_verified:false};
  }

  async loadNetwork() {
    const response=await fetch(this.baseUrl+this.manifest.road_network);
    if(!response.ok)throw new Error(`Road network HTTP ${response.status}`);
    const network=await response.json();
    if(network.schema!=='therabby.geoengine.road-network.v0.1')
      throw new Error('Unsupported road network schema');
    this.network=network;
    this.nodes=new Map(network.nodes.map(node=>[node.id,node]));
    return network;
  }

  tileAt(x,z) {
    return this.manifest.tiles.find(tile=>x>=tile.bounds[0]&&x<tile.bounds[2]&&
                                          z>=tile.bounds[1]&&z<tile.bounds[3])??null;
  }

  async surfaceAt(x,z) {
    const tile=this.tileAt(x,z);
    if(!tile)return null;
    if(!this.surfaceCache.has(tile.id)) {
      const response=await fetch(this.baseUrl+tile.road_surface_file);
      if(!response.ok)throw new Error(`Road surface HTTP ${response.status}`);
      const data=await response.json();
      if(data.schema!=='therabby.geoengine.road-surfaces.tile.v0.1'||data.tile_id!==tile.id)
        throw new Error('Road surface tile mismatch');
      this.surfaceCache.set(tile.id,data);
    }
    const data=this.surfaceCache.get(tile.id);
    const surface=data.surfaces.find(item=>pointInPolygon([x,z],item.polygon));
    if(surface&&this.manifest.terrain_grid)await this.loadTerrain();
    const terrain=surface?this.terrainHeightAt(x,z):null;
    const extent=surface?await this.roadExtentAt(x,z):null;
    return surface?{
      tile_id:tile.id,source_road_id:surface.source_road_id,
      surface_id:surface.id,height_m:null,
      ground_height_m:terrain?.height_m??null,
      ground_height_tp_m:terrain?.height_tp_m??null,
      height_quality:surface.height_quality,width_m:surface.width_m,
      width_quality:surface.width_quality,legal_access:surface.legal_access,
      bridge:surface.bridge??'no',tunnel:surface.tunnel??'no',layer:surface.layer??'0',
      official_road_extent:extent,
      road_deck_verified:false,
      collision_ready:false,
    }:null;
  }

  async roadExtentAt(x,z) {
    const tile=this.tileAt(x,z);
    if(!tile?.road_extent_file)return null;
    if(!this.extentCache.has(tile.id)) {
      const response=await fetch(this.baseUrl+tile.road_extent_file);
      if(!response.ok)throw new Error(`Road extent HTTP ${response.status}`);
      const data=await response.json();
      if(data.schema!=='therabby.geoengine.road-extents.tile.v0.1'||data.tile_id!==tile.id)
        throw new Error('Official road extent tile mismatch');
      this.extentCache.set(tile.id,data);
    }
    const data=this.extentCache.get(tile.id);
    const extent=data.extents.find(item=>pointInPolygon([x,z],item.polygon));
    return extent?{source_road_id:extent.source_road_id,
      source:extent.source,geometry_quality:extent.geometry_quality,
      height_m:null,drivable:null,legal_access:'not-verified',collision_ready:false}:null;
  }

  nearestRoad(x,z,maxDistance=30) {
    if(!this.network)throw new Error('Call loadNetwork() first');
    let best=null;
    for(const edge of this.network.edges) {
      if(!edge.drivable)continue;
      const a=this.nodes.get(edge.from).position;
      const b=this.nodes.get(edge.to).position;
      const dx=b[0]-a[0],dz=b[1]-a[1],length2=dx*dx+dz*dz;
      if(length2<.01)continue;
      const t=Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[1])*dz)/length2));
      const px=a[0]+t*dx,pz=a[1]+t*dz;
      const distance=Math.hypot(x-px,z-pz);
      if(!best||distance<best.distance_m) {
        const reverse=edge.direction==='reverse';
        best={edge_id:edge.id,source_road_id:edge.source_road_id,
          position:[px,pz],heading:[(reverse?-dx:dx)/Math.sqrt(length2),
                                    (reverse?-dz:dz)/Math.sqrt(length2)],
          distance_m:distance,oneway:edge.direction,width_m:edge.width_m,
          width_quality:edge.width_quality,elevation_m:null,
          ground_terrain_height_m:edge.ground_height_from_m==null?null:
            edge.ground_height_from_m*(1-t)+edge.ground_height_to_m*t,
          ground_grade_estimate:edge.ground_grade_estimate??null,
          ground_height_quality:edge.ground_height_quality??'not-provided',
          bridge:edge.bridge??'no',tunnel:edge.tunnel??'no',layer:edge.layer??'0',
          lanes_osm_tag:edge.lanes_osm_tag??null,
          official_extent_coverage_ratio:edge.official_extent_coverage_ratio??null,
          official_extent_source_ids:edge.official_extent_source_ids??[],
          legal_access:edge.legal_access,collision_ready:false};
      }
    }
    return best&&best.distance_m<=maxDistance?best:null;
  }
}

function pointInPolygon(point,polygon) {
  let inside=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
    const a=polygon[i],b=polygon[j];
    const cross=(point[0]-a[0])*(b[1]-a[1])-(point[1]-a[1])*(b[0]-a[0]);
    if(Math.abs(cross)<1e-6&&point[0]>=Math.min(a[0],b[0])-1e-6&&
       point[0]<=Math.max(a[0],b[0])+1e-6&&point[1]>=Math.min(a[1],b[1])-1e-6&&
       point[1]<=Math.max(a[1],b[1])+1e-6)return true;
    if((a[1]>point[1])!==(b[1]>point[1])&&
       point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
  }
  return inside;
}
