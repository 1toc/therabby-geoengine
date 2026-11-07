"""Deterministic, crisp procedural facades for wide-area LOD1 street views.

Building footprints/heights are source geometry. Colors, windows and shopfront
patterns are visual estimates, never surveyed or photo-verified attributes.
"""
import hashlib
import math


PALETTE={
    'facade_0':(.68,.67,.62), 'facade_1':(.57,.62,.62),
    'facade_2':(.61,.49,.43), 'facade_3':(.51,.56,.59),
    'facade_4':(.75,.71,.64), 'facade_5':(.69,.72,.70),
    'roof':(.38,.43,.44), 'window':(.14,.25,.31),
    'frame':(.80,.82,.79), 'shop_glass':(.12,.22,.27),
    'plinth':(.38,.40,.39), 'trim':(.48,.52,.51),
}


def style_index(building_id):
    return int.from_bytes(hashlib.sha256(building_id.encode('utf-8')).digest()[:2],'big')%6


def point_segment_distance(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    denom=dx*dx+dy*dy
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/denom)) if denom else 0
    nearest=(a[0]+t*dx,a[1]+t*dy)
    return math.dist(point,nearest),nearest


def road_segments(roads):
    """Only road centreline segments relevant for plausible street-facing walls."""
    index={}
    for road in roads:
        if road.get('highway') in {'footway','path','cycleway','steps','pedestrian'}:continue
        for a,b in zip(road['points'],road['points'][1:]):
            x0=min(a[0],b[0])-22;x1=max(a[0],b[0])+22
            z0=min(a[1],b[1])-22;z1=max(a[1],b[1])+22
            for ix in range(math.floor(x0/25),math.floor(x1/25)+1):
                for iz in range(math.floor(z0/25),math.floor(z1/25)+1):
                    index.setdefault((ix,iz),[]).append((a,b))
    return index


def road_facing(midpoint,outward,index):
    nearest_distance=float('inf');nearest=None
    cell=(math.floor(midpoint[0]/25),math.floor(midpoint[1]/25))
    for a,b in index.get(cell,[]):
        distance,point=point_segment_distance(midpoint,a,b)
        if distance<nearest_distance:nearest_distance,nearest=distance,point
    if nearest is None or nearest_distance>20:return False
    dx=nearest[0]-midpoint[0];dy=-(nearest[1]-midpoint[1])
    return dx*outward[0]+dy*outward[1]>-1


def build_facade_batches(buildings,origin,core_ids,roads,height_fn=None):
    """Return material-keyed (vertices, faces), in Blender X-east/Y-north/Z-up."""
    groups={key:{'vertices':[],'faces':[]} for key in PALETTE}
    road_index=road_segments(roads)
    stats={'buildings':0,'street_facing_walls':0,'windows':0,'shopfronts':0}
    x0,z0=origin
    base_height=0

    def add(key,points):
        group=groups[key];offset=len(group['vertices'])
        group['vertices'].extend((x,y,z+base_height) for x,y,z in points)
        group['faces'].append(tuple(offset+i for i in range(len(points))))

    for building in buildings:
        if building['id'] in core_ids:continue
        raw=building['footprint']
        ring=[]
        for x,z in raw:
            if not ring or math.dist(ring[-1],(x,z))>.05:ring.append((x,z))
        if len(ring)>2 and math.dist(ring[0],ring[-1])<.05:ring.pop()
        if len(ring)<3:continue
        height=float(building['height_m'])
        if not 1<=height<500:continue
        if height_fn:
            cx=sum(x for x,_ in ring)/len(ring)
            cz=sum(z for _,z in ring)/len(ring)
            base_height=height_fn(cx,cz)
        else:base_height=0
        stats['buildings']+=1
        style=f'facade_{style_index(building["id"])}'
        local=[(x-x0,-(z-z0)) for x,z in ring]
        signed=sum(local[i][0]*local[(i+1)%len(local)][1]-
                   local[(i+1)%len(local)][0]*local[i][1] for i in range(len(local)))
        sign=1 if signed>=0 else -1
        add('roof',[(x,y,height) for x,y in local])
        for i,(a,b) in enumerate(zip(local,local[1:]+local[:1])):
            dx,dy=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dy)
            if length<.6:continue
            ux,uy=dx/length,dy/length
            outward=(sign*uy,-sign*ux)
            add(style,[(a[0],a[1],0),(b[0],b[1],0),
                       (b[0],b[1],height),(a[0],a[1],height)])
            # A thin parapet helps the roof read as architecture from the road.
            if height>=6:
                add('roof',[(a[0]+outward[0]*.018,a[1]+outward[1]*.018,height-.24),
                            (b[0]+outward[0]*.018,b[1]+outward[1]*.018,height-.24),
                            (b[0]+outward[0]*.018,b[1]+outward[1]*.018,height),
                            (a[0]+outward[0]*.018,a[1]+outward[1]*.018,height)])
            world_mid=((ring[i][0]+ring[(i+1)%len(ring)][0])/2,
                       (ring[i][1]+ring[(i+1)%len(ring)][1])/2)
            if length<2.4 or not road_facing(world_mid,outward,road_index):continue
            stats['street_facing_walls']+=1
            floors=min(32,max(1,round(height/3.2)))
            columns=min(16,max(1,int(length/2.7)))
            cell_width=length/columns
            floor_height=height/floors
            def panel(key,centre,width,bottom,top,offset):
                left=centre-width/2;right=centre+width/2
                def at(u,h):
                    return (a[0]+ux*u+outward[0]*offset,
                            a[1]+uy*u+outward[1]*offset,h)
                add(key,[at(left,bottom),at(right,bottom),at(right,top),at(left,top)])
            commercial=(height>=10 and length>=5 and building['source']=='PLATEAU CityGML')
            if commercial:
                panel('plinth',length/2,length-.25,0,.38,.026)
            # Narrow horizontal reveals give each floor a readable scale from
            # a driver's camera without assigning a surveyed facade design.
            if floors>1 and length>=3:
                for floor in range(1,floors):
                    level=floor*floor_height
                    panel('trim',length/2,length-.08,level-.055,level+.025,.024)
            for floor in range(floors):
                bottom=floor*floor_height
                for col in range(columns):
                    centre=(col+.5)*cell_width
                    width=min(1.28,cell_width*.55)
                    if commercial and floor==0:
                        width=min(1.8,cell_width*.70)
                        low=.62;high=min(floor_height-.38,2.65)
                        if high<=low+.3:continue
                        panel('frame',centre,width+.16,low-.12,high+.12,.028)
                        panel('shop_glass',centre,width,low,high,.035)
                        if col==columns//2:
                            panel('trim',centre,.055,low,high,.039)
                        stats['shopfronts']+=1
                    else:
                        low=bottom+floor_height*.35
                        high=min(bottom+floor_height*.76,height-.35)
                        if high<=low+.3:continue
                        panel('frame',centre,width+.13,low-.09,high+.09,.028)
                        panel('window',centre,width,low,high,.036)
                        panel('trim',centre,width+.24,low-.15,low-.09,.041)
                        stats['windows']+=1
    return {key:value for key,value in groups.items() if value['faces']},stats
