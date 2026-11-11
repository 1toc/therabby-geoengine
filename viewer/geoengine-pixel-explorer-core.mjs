// Geometry and kinematics shared by Pixel Explorer and its dependency-free tests.
// EPSG:6677 tile coordinates map to scene x=easting-origin.east, z=origin.north-northing.
const DRIVE_CLASSES = new Set(['motorway','trunk','primary','secondary','tertiary','residential','unclassified','living_street','service']);
const clamp = (n, a, b) => Math.min(b, Math.max(a, n));
const yes = tag => !['', 'no', 'false', '0', 'undefined', 'null'].includes(String(tag ?? '').toLowerCase());

export function isDriveEdge(edge) {
  return DRIVE_CLASSES.has(edge?.highway) && edge?.highway !== 'steps' &&
    !yes(edge.bridge_osm_tag) && !yes(edge.tunnel_osm_tag) &&
    Number.isFinite(edge.ground_height_from_tp_m) &&
    Number.isFinite(edge.ground_height_to_tp_m) &&
    Array.isArray(edge.points) && edge.points.length === 2 &&
    edge.points.every(p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite));
}

export function closestDriveRoad(active, origin, x, z, maxDistance = 25) {
  if (!Number.isFinite(x) || !Number.isFinite(z)) return null;
  let best = null;
  const limit2 = maxDistance * maxDistance;
  for (const [key, item] of active) {
    if (!key.startsWith('road:') || !item.roadTile) continue;
    const tile = item.roadTile;
    const ox = tile.tile_origin_east_m - origin.east;
    const oz = origin.north - tile.tile_origin_north_m;
    for (const edge of tile.edges) {
      if (!isDriveEdge(edge)) continue;
      const a = edge.points[0], b = edge.points[1];
      const ax = ox + a[0], az = oz + a[1], bx = ox + b[0], bz = oz + b[1];
      if (x < Math.min(ax,bx)-maxDistance || x > Math.max(ax,bx)+maxDistance ||
          z < Math.min(az,bz)-maxDistance || z > Math.max(az,bz)+maxDistance) continue;
      const dx = bx-ax, dz = bz-az, len2 = dx*dx+dz*dz;
      if (len2 < 0.01) continue;
      const t = clamp(((x-ax)*dx+(z-az)*dz)/len2, 0, 1);
      const px = ax+dx*t, pz = az+dz*t;
      const dist2 = (x-px)**2 + (z-pz)**2;
      if (dist2 < limit2 && (!best || dist2 < best.distance**2)) {
        best = { x:px, z:pz, t, distance:Math.sqrt(dist2),
          y:edge.ground_height_from_tp_m+(edge.ground_height_to_tp_m-edge.ground_height_from_tp_m)*t,
          dx, dz, width:clamp(Number(edge.width_m)||5, 2, 20), edge, tile };
      }
    }
  }
  return best;
}

// Locally positive yaw turns the model left (model's forward axis is -Z).
export function advanceVehicle(state, keys, dt) {
  dt = clamp(Number(dt)||0,0,0.05);
  const forward = keys.has('w') || keys.has('arrowup');
  const backward = keys.has('s') || keys.has('arrowdown');
  const left = keys.has('a') || keys.has('arrowleft');
  const right = keys.has('d') || keys.has('arrowright');
  let speed = state.speed;
  if (forward !== backward) speed += (forward ? 4.5 : -5.5) * dt;
  else speed = Math.sign(speed) * Math.max(0, Math.abs(speed)-3.0*dt);
  if (keys.has(' ')) speed = Math.sign(speed)*Math.max(0,Math.abs(speed)-12*dt);
  speed = clamp(speed,-3.5,12);
  const steering = Number(left)-Number(right);
  const yaw = state.yaw + steering * Math.sign(speed) * Math.min(1, Math.abs(speed)/3) * 1.15 * dt;
  return { ...state, speed, yaw, x:state.x-Math.sin(yaw)*speed*dt,
    z:state.z-Math.cos(yaw)*speed*dt };
}
