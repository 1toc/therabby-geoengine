/**
 * Visual road-paint estimates from OSM centerlines.
 * No stop lines, crossings, legal lanes or collision geometry are inferred.
 * Pure functions: no Three.js dependency, safe to test in Node.
 */
export const ROAD_PAINT_SCHEMA = 'therabby.geoengine.procedural-road-paint.v0.1';

const WALK_CLASSES = new Set(['footway','path','pedestrian','cycleway','bridleway','steps','track']);
const OFF_GROUND = value => !['', 'no', 'false', '0'].includes(String(value ?? '').toLowerCase());

export function eligiblePaintEdge(edge) {
  if (!Array.isArray(edge?.points) || edge.points.length !== 2) return false;
  if (WALK_CLASSES.has(edge.highway) || edge.road_class === 'walk') return false;
  if (OFF_GROUND(edge.bridge_osm_tag) || OFF_GROUND(edge.tunnel_osm_tag)) return false;
  if (!Number.isFinite(edge.ground_height_from_tp_m) || !Number.isFinite(edge.ground_height_to_tp_m)) return false;
  if (!Number.isFinite(edge.width_m) || edge.width_m < 4.5) return false;
  const [a, b] = edge.points;
  return a.length === 2 && b.length === 2 &&
    [...a, ...b].every(Number.isFinite) && Math.hypot(b[0]-a[0], b[1]-a[1]) > 5;
}

function isOneWay(edge) {
  return ['yes','true','1','-1'].includes(String(edge.oneway_osm_tag ?? '').toLowerCase());
}

export function estimateLineStyle(edge) {
  if (!eligiblePaintEdge(edge)) return null;
  const width = Math.min(20, Math.max(4.5, edge.width_m));
  const major = ['trunk','primary','secondary','tertiary'].includes(edge.highway);
  // Fictional visual aids. Real centre/edge lines require surveying or regulation data.
  return {
    width,
    center: !isOneWay(edge) && width >= 5.8,
    edges: major && width >= 7,
    confidence: 'estimated-visual-only',
  };
}

export function buildEstimatedRoadPaint(edges, sampleHeight = (_, linear) => linear, {maxQuads = 2400} = {}) {
  if (!Array.isArray(edges)) throw new TypeError('edges must be an array');
  if (typeof sampleHeight !== 'function') throw new TypeError('sampleHeight must be a function');
  if (!Number.isInteger(maxQuads) || maxQuads < 0) throw new RangeError('maxQuads must be a non-negative integer');
  const yellow = [], white = [];
  let quads = 0, eligible = 0, omitted = 0;
  const limit = Math.min(maxQuads, 20000);

  for (const edge of edges) {
    const style = estimateLineStyle(edge);
    if (!style) continue;
    eligible++;
    const [a,b] = edge.points;
    const dx=b[0]-a[0], dz=b[1]-a[1], length=Math.hypot(dx,dz);
    const nx=-dz/length, nz=dx/length;
    const h0=edge.ground_height_from_tp_m, h1=edge.ground_height_to_tp_m;
    const point = (metres, offset) => {
      const t=metres/length, x=a[0]+dx*t+nx*offset, z=a[1]+dz*t+nz*offset;
      const linear=h0+(h1-h0)*t;
      const sampled=sampleHeight([x,z],linear);
      const y=(Number.isFinite(sampled)?sampled:linear)+0.205;
      return [x,y,z];
    };
    const strip = (target,start,end,offset,width) => {
      if (quads >= limit) {omitted++;return false;}
      const x0=point(start,offset-width/2),x1=point(start,offset+width/2);
      const x2=point(end,offset+width/2),x3=point(end,offset-width/2);
      for (const v of [x0,x1,x2,x0,x2,x3]) target.push(v[0],v[1],v[2]);
      quads++;
      return true;
    };

    // Do not paint right into intersections; the centreline is not a lane survey.
    const margin=Math.min(3.0, length*0.14);
    if (style.center) {
      for (let s=margin; s<length-margin; s+=9) {
        if (!strip(yellow,s,Math.min(s+4,length-margin),0,0.12)) break;
      }
    }
    if (style.edges) {
      const offset=style.width/2-0.25;
      for (let s=margin; s<length-margin; s+=15) {
        const end=Math.min(s+15,length-margin);
        if (!strip(white,s,end,-offset,0.10)) break;
        if (!strip(white,s,end,offset,0.10)) break;
      }
    }
    if (quads>=limit) break;
  }
  return {schema:ROAD_PAINT_SCHEMA,white,yellow,
    diagnostics:{eligibleEdges:eligible,quads,omitted,estimated:true,collisionReady:false,legalAccessVerified:false}};
}


/**
 * Blender's bpy.data.materials.new() allocates a fresh material for each tile;
 * names in later tile GLBs can be suffixed .001, .002, ... .
 * Keep strict wall-vs-roof and official-vs-OSM matching.
 */
export function isProceduralFacadeMaterial(materialName, kind) {
  const expected={
    building:'lod1 walls / official shape',
    osmBuilding:'osm fallback walls / estimated height',
  }[kind];
  if(!expected || typeof materialName!=='string') return false;
  const canonical=materialName.trim().replace(/\s+/g,' ').replace(/\.\d{1,5}$/,'').toLowerCase();
  return canonical===expected;
}
