"""Deterministic tile and road clipping in local X-east/Z-south metres."""
import math


def tile_bounds(half_size=100, tile_size=100):
    if half_size <= 0 or tile_size <= 0 or (2 * half_size) % tile_size:
        raise ValueError('Tile size must evenly divide the square area')
    count = int(2 * half_size / tile_size)
    for iz in range(count):
        for ix in range(count):
            x0 = -half_size + ix * tile_size
            z0 = -half_size + iz * tile_size
            yield {'id': f'{ix}_{iz}', 'ix': ix, 'iz': iz,
                   'bounds': [x0, z0, x0 + tile_size, z0 + tile_size]}


def clip_segment_rect(a, b, bounds):
    """Liang-Barsky clip, with exact shared boundary coordinates."""
    x0,z0,x1,z1 = bounds
    dx,dz = b[0]-a[0],b[1]-a[1]
    low,high = 0.0,1.0
    for p,q in ((-dx,a[0]-x0),(dx,x1-a[0]),(-dz,a[1]-z0),(dz,z1-a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        t = q/p
        if p < 0:
            low = max(low,t)
        else:
            high = min(high,t)
        if low > high:
            return None
    if high-low < 1e-10:
        return None
    def point(t):
        x,z = a[0]+dx*t,a[1]+dz*t
        for value,lo,hi in ((x,x0,x1),(z,z0,z1)):
            if not math.isfinite(value) or value < lo-1e-7 or value > hi+1e-7:
                raise ValueError('Invalid clipped coordinate')
        x = x0 if abs(x-x0)<1e-7 else x1 if abs(x-x1)<1e-7 else x
        z = z0 if abs(z-z0)<1e-7 else z1 if abs(z-z1)<1e-7 else z
        return [round(x,3),round(z,3)]
    return point(low),point(high)


def seam_node(point, half_size=100, tile_size=100):
    x,z = point
    def on_inner_grid(v):
        index = round((v + half_size) / tile_size)
        count = round(2 * half_size / tile_size)
        return 0 < index < count and abs(v - (-half_size + index * tile_size)) < 1e-6
    if on_inner_grid(x) or on_inner_grid(z):
        return f'seam:{round(x*1000)}:{round(z*1000)}'
    return None


def clip_roads(roads, bounds, half_size=100, tile_size=100):
    result = []
    for road in roads:
        fragments = []
        current = []
        for a,b in zip(road['points'],road['points'][1:]):
            clipped = clip_segment_rect(a,b,bounds)
            if clipped:
                start,end = clipped
                if current and current[-1] == start:
                    if current[-1] != end:
                        current.append(end)
                else:
                    if len(current)>1:
                        fragments.append(current)
                    current = [start,end]
            elif len(current)>1:
                fragments.append(current)
                current = []
        if len(current)>1:
            fragments.append(current)
        for index,points in enumerate(fragments):
            item = {key:value for key,value in road.items() if key != 'points'}
            item['source_road_id'] = road['id']
            item['id'] = f'{road["id"]}-tile-part-{index}'
            item['points'] = points
            item['endpoint_nodes'] = [seam_node(points[0],half_size,tile_size),seam_node(points[-1],half_size,tile_size)]
            result.append(item)
    return result
