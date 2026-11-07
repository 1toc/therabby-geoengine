"""Roadway surface and network exports for the flat 1km driving preview.

Coordinates are projected local X east / Z south metres. Road widths are OSM
class estimates, and flat Y=0 is a visual prototype rather than surveyed grade.
"""
import math


NON_DRIVING={'footway','path','cycleway','steps','pedestrian','bridleway','track'}


def road_is_drivable(road):
    return (road.get('highway') not in NON_DRIVING and
            road.get('access')!='no' and road.get('motor_vehicle')!='no')


def point_id(point):
    return f'n:{round(point[0]*1000)}:{round(point[1]*1000)}'


def point_in_polygon(point,polygon):
    x,z=point;inside=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        cross=(x-a[0])*(b[1]-a[1])-(z-a[1])*(b[0]-a[0])
        if abs(cross)<1e-6 and min(a[0],b[0])-1e-6<=x<=max(a[0],b[0])+1e-6 and \
                min(a[1],b[1])-1e-6<=z<=max(a[1],b[1])+1e-6:
            return True
        if (a[1]>z)!=(b[1]>z) and x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]:
            inside=not inside
    return inside


def annotate_official_extent(network,extents):
    """Record whether OSM edge samples overlap official *road extents*.

    This is evidence of alignment, never proof of legal/carriageway access.
    """
    candidates=[]
    for extent in extents:
        polygon=extent['polygon']
        candidates.append((min(x for x,_ in polygon),min(z for _,z in polygon),
                           max(x for x,_ in polygon),max(z for _,z in polygon),extent))
    nodes={node['id']:node['position'] for node in network['nodes']}
    for edge in network['edges']:
        a,b=nodes[edge['from']],nodes[edge['to']]
        found=[];covered=0
        for t in (.25,.5,.75):
            x,z=a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t
            match=next((item for x0,z0,x1,z1,item in candidates
                        if x0<=x<=x1 and z0<=z<=z1 and
                        point_in_polygon((x,z),item['polygon'])),None)
            if match:
                covered+=1
                if match['source_road_id'] not in found:found.append(match['source_road_id'])
        edge['official_extent_samples']=covered
        edge['official_extent_coverage_ratio']=round(covered/3,3)
        edge['official_extent_source_ids']=found
        edge['official_extent_quality']='PLATEAU LOD1 road extent, not carriageway or legal access'
    network['official_extent_source']='PLATEAU CityGML transportation Road LOD1'
    network['official_extent_mean_sample_coverage']=round(
        sum(edge['official_extent_samples'] for edge in network['edges'] if edge['drivable'])/
        max(1,3*sum(edge['drivable'] for edge in network['edges'])),3)
    return network


def clip_polygon_rect(polygon,bounds):
    """Sutherland-Hodgman clip with millimetre-snapped common seam vertices."""
    x0,z0,x1,z1=bounds
    vertices=[list(point) for point in polygon]
    for axis,value,keep_above in ((0,x0,True),(0,x1,False),(1,z0,True),(1,z1,False)):
        if not vertices:break
        output=[];previous=vertices[-1]
        previous_inside=previous[axis]>=value-1e-9 if keep_above else previous[axis]<=value+1e-9
        for current in vertices:
            current_inside=current[axis]>=value-1e-9 if keep_above else current[axis]<=value+1e-9
            if previous_inside!=current_inside:
                denom=current[axis]-previous[axis]
                if abs(denom)>1e-12:
                    t=(value-previous[axis])/denom
                    cross=[previous[i]+t*(current[i]-previous[i]) for i in (0,1)]
                    cross[axis]=value
                    output.append(cross)
            if current_inside:output.append(current)
            previous,previous_inside=current,current_inside
        vertices=output
    result=[]
    for x,z in vertices:
        point=[round(x,3),round(z,3)]
        if not result or point!=result[-1]:result.append(point)
    if len(result)>1 and result[0]==result[-1]:result.pop()
    if len(result)<3:return []
    area=sum(result[i][0]*result[(i+1)%len(result)][1]-
             result[(i+1)%len(result)][0]*result[i][1] for i in range(len(result)))/2
    return result if abs(area)>.001 else []


def segment_quad(a,b,width):
    dx,dz=b[0]-a[0],b[1]-a[1]
    length=math.hypot(dx,dz)
    if length<.1:return []
    nx,nz=-dz/length*width/2,dx/length*width/2
    return [[a[0]+nx,a[1]+nz],[a[0]-nx,a[1]-nz],
            [b[0]-nx,b[1]-nz],[b[0]+nx,b[1]+nz]]


def road_surfaces(roads,bounds):
    surfaces=[]
    for road in roads:
        if not road_is_drivable(road):continue
        for index,(a,b) in enumerate(zip(road['points'],road['points'][1:])):
            polygon=clip_polygon_rect(segment_quad(a,b,road['width_m']),bounds)
            if not polygon:continue
            surfaces.append({'id':f'{road["id"]}:segment:{index}',
                'source_road_id':road['id'],'segment_index':index,
                'polygon':polygon,'highway':road['highway'],
                'bridge':road.get('bridge','no'),'tunnel':road.get('tunnel','no'),
                'layer':road.get('layer','0'),
                'width_m':road['width_m'],'width_quality':road['width_quality'],
                'height_m':0,'height_quality':'flat-prototype-not-surveyed',
                'legal_access':'not-verified'})
    return surfaces


def road_network(roads,coordinate_system):
    nodes={};edges=[];degree={}
    for road in roads:
        points=road['points']
        for index,(a,b) in enumerate(zip(points,points[1:])):
            length=math.dist(a,b)
            if length<.1:continue
            aid,bid=point_id(a),point_id(b)
            nodes.setdefault(aid,{'id':aid,'position':a})
            nodes.setdefault(bid,{'id':bid,'position':b})
            degree[aid]=degree.get(aid,0)+1
            degree[bid]=degree.get(bid,0)+1
            oneway=road.get('oneway','no')
            direction=('forward' if oneway in ('yes','true','1') else
                       'reverse' if oneway=='-1' else 'both')
            edges.append({'id':f'{road["id"]}:segment:{index}',
                'source_road_id':road['id'],'from':aid,'to':bid,
                'length_m':round(length,3),'width_m':road['width_m'],
                'width_quality':road['width_quality'],'highway':road['highway'],
                'name':road.get('name',''),'direction':direction,
                'drivable':road_is_drivable(road),
                'bridge':road.get('bridge','no'),'tunnel':road.get('tunnel','no'),
                'layer':road.get('layer','0'),'lanes_osm_tag':road.get('lanes'),
                'surface_osm_tag':road.get('surface'),
                'legal_access':'not-verified','elevation_m':None})
    for key,node in nodes.items():node['degree']=degree[key]
    return {'schema':'therabby.geoengine.road-network.v0.1',
            'coordinate_system':coordinate_system,
            'source':'OpenStreetMap road centreline',
            'attribution':'© OpenStreetMap contributors / ODbL 1.0',
            'surface_quality':'OSM centreline, estimated class width, flat preview',
            'nodes':list(nodes.values()),'edges':edges}
