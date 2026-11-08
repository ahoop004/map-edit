"""Offline variable-width corridor checks using all retained polygon edges."""
from dataclasses import asdict
import math
import numpy as np
from .curves import GeometryError
from .spatial import (_index,_cells,_bounds,edges,self_intersects,segment_distance,minimum_boundary_separation,
                      _segments_intersect)
from .validation import footprint_corners,_nonlocal_gap_certificate,validate_raster_footprint
from map_editor.models.annotations import Point2D


def _segment_distances(a,b,c,d):
    """Vectorized exact segment distances, including proper/collinear crossings."""
    a=np.asarray(a);b=np.asarray(b);c=np.asarray(c);d=np.asarray(d)
    def cross(x,y):return x[...,0]*y[...,1]-x[...,1]*y[...,0]
    def orientation(p,q,r):
        value=cross(q-p,r-q)
        return np.where(abs(value)<1e-9,0,np.where(value>0,1,2))
    def on(p,q,r):return np.all((q>=np.minimum(p,r))&(q<=np.maximum(p,r)),axis=-1)
    o1,o2,o3,o4=orientation(a,b,c),orientation(a,b,d),orientation(c,d,a),orientation(c,d,b)
    hit=((o1!=o2)&(o3!=o4))|((o1==0)&on(a,c,b))|((o2==0)&on(a,d,b))|((o3==0)&on(c,a,d))|((o4==0)&on(c,b,d))
    def point_distance(p,q,r):
        delta=r-q;norm=np.sum(delta*delta,axis=-1)
        t=np.clip(np.sum((p-q)*delta,axis=-1)/np.maximum(norm,1e-30),0,1)
        return np.linalg.norm(p-q-t[...,None]*delta,axis=-1)
    distance=np.minimum.reduce([point_distance(a,c,d),point_distance(b,c,d),point_distance(c,a,b),point_distance(d,a,b)])
    return np.where(hit,0.,distance)


def vectorized_boundary_separation(first,second):
    """Same global opposing-wall metric as legacy, vectorizing the narrow phase."""
    left,right=edges(first,True),edges(second,True)
    if not left or not right:raise GeometryError('Two closed boundaries required')
    best=segment_distance(*left[0],*right[0])
    if best==0:return 0.
    size=max(best,1e-6);grid=_index(right,size)
    coordinates=np.array([[(p.x,p.y) for p in edge] for edge in right])
    lower=coordinates.min(axis=1);upper=coordinates.max(axis=1)
    for a,b in left:
        x0,y0,x1,y1=_bounds((a,b))
        candidates=sorted(set(j for cell in _cells((x0-best,y0-best,x1+best,y1+best),size) for j in grid.get(cell,())))
        if not candidates:continue
        indices=np.array(candidates)
        gap=np.maximum(np.maximum(lower[indices]-[x1,y1],[x0,y0]-upper[indices]),0.)
        indices=indices[np.sum(gap*gap,axis=1)<=best*best]
        if len(indices):
            best=min(best,float(_segment_distances([a.x,a.y],[b.x,b.y],coordinates[indices,0],coordinates[indices,1]).min()))
        if best==0:return 0.
    return best


class WallIndex:
    def __init__(self,walls,size):
        self.segments=[edge for wall in walls for edge in edges(wall,True)]
        self.size=size;self.grid=_index(self.segments,size)
        self.array=np.array([[(p.x,p.y) for p in edge] for edge in self.segments])

    def ray(self,point,direction,maximum):
        p=np.array([point.x,point.y]);n=np.asarray(direction);end=p+maximum*n
        bounds=(*np.minimum(p,end)-1e-6,*np.maximum(p,end)+1e-6)
        candidates=sorted(set(j for cell in _cells(bounds,self.size) for j in self.grid.get(cell,())))
        if not candidates:raise GeometryError('Missing boundary along centerline normal')
        segment=self.array[candidates];a=segment[:,0];edge=segment[:,1]-a;rel=a-p
        denominator=n[0]*edge[:,1]-n[1]*edge[:,0];valid=abs(denominator)>1e-12
        den=denominator[valid];rel=rel[valid];edge=edge[valid]
        distance=(rel[:,0]*edge[:,1]-rel[:,1]*edge[:,0])/den
        u=(rel[:,0]*n[1]-rel[:,1]*n[0])/den
        hits=distance[(u>=-1e-8)&(u<=1+1e-8)&(distance>=0)&(distance<=maximum+1e-6)]
        if not len(hits):raise GeometryError('Missing boundary along centerline normal')
        return float(min(hits))


def variable_boundaries(sampled,left,right,maximum_offset_curvature=.95):
    states=sampled.states[:-1]
    if len(left)!=len(states) or len(right)!=len(states):raise GeometryError('Width arrays must match centerline')
    if any(p.curvature*l>=maximum_offset_curvature or -p.curvature*r>=maximum_offset_curvature
           for p,l,r in zip(states,left,right)):
        raise GeometryError('Variable normal offset exceeds its curvature/singularity bound')
    return [[Point2D(float(round(p.x-math.sin(p.heading)*l,6)),float(round(p.y+math.cos(p.heading)*l,6))) for p,l in zip(states,left)],
            [Point2D(float(round(p.x+math.sin(p.heading)*r,6)),float(round(p.y-math.cos(p.heading)*r,6))) for p,r in zip(states,right)]]


def validate_corridor(sampled,walls,widths,vehicle,limits):
    if self_intersects(sampled.points,closed=True):raise GeometryError('Exported centerline self-intersects')
    if any(self_intersects(w,closed=True) for w in walls):raise GeometryError('Variable boundary self-intersects')
    # At these waypoint spacings the existing indexed scalar narrow phase is
    # faster than allocating NumPy batches. Keep the all-edge exact metric.
    gap=minimum_boundary_separation(*walls,closed=True)
    usable=gap-2*limits.footprint_margin_m
    if usable<limits.minimum_usable_width_m:raise GeometryError(f'Global opposing-wall usable width {usable:.6f} below limit')
    nonlocal_gap=_nonlocal_gap_certificate(sampled,walls,float(max(widths)),limits.minimum_nonlocal_boundary_gap_m)
    index=WallIndex(walls,max(vehicle.length_m,vehicle.width_m,float(max(widths))))
    count=0
    for state in sampled.states[:-1]:
        corners=footprint_corners(state,vehicle,limits.footprint_margin_m)
        bounds=(min(p.x for p in corners),min(p.y for p in corners),max(p.x for p in corners),max(p.y for p in corners))
        candidates=set(j for cell in _cells(bounds,index.size) for j in index.grid.get(cell,()))
        co,si=math.cos(state.heading),math.sin(state.heading)
        for j in candidates:
            a,b=index.segments[j]
            if max(a.x,b.x)<bounds[0] or min(a.x,b.x)>bounds[2] or max(a.y,b.y)<bounds[1] or min(a.y,b.y)>bounds[3]:continue
            x=(a.x-state.x)*co+(a.y-state.y)*si;y=-(a.x-state.x)*si+(a.y-state.y)*co
            contained=abs(x)<=vehicle.length_m/2+limits.footprint_margin_m and abs(y)<=vehicle.width_m/2+limits.footprint_margin_m
            if contained or any(_segments_intersect(c,d,a,b) for c,d in edges(corners,True)):
                raise GeometryError('Full sampled vehicle footprint intersects variable boundary')
        count+=1
    return dict(exported_global_boundary_separation_m=gap,minimum_usable_corridor_width_m=usable,
        nonlocal_boundary_gap=nonlocal_gap,footprint='passed_at_sampled_poses',footprint_poses_checked=count,
        limits=asdict(limits),vehicle=asdict(vehicle)),index


def raster_ray_distance(state,direction,raster):
    pixels,width,height,ox,oy,resolution=raster
    x,y=state.x,state.y;dx,dy=direction
    col,row=math.floor((x-ox)/resolution),math.floor((y-oy)/resolution)
    def occupied(c,r):return not (0<=c<width and 0<=r<height) or pixels[(height-1-r)*width+c]==0
    if occupied(col,row):raise GeometryError('Centerline lies outside free raster corridor')
    sx=1 if dx>0 else -1;sy=1 if dy>0 else -1
    tx=(ox+(col+(1 if dx>0 else 0))*resolution-x)/dx if abs(dx)>1e-14 else math.inf
    ty=(oy+(row+(1 if dy>0 else 0))*resolution-y)/dy if abs(dy)>1e-14 else math.inf
    dtx=resolution/abs(dx) if abs(dx)>1e-14 else math.inf
    dty=resolution/abs(dy) if abs(dy)>1e-14 else math.inf
    for _ in range(width+height+2):
        if abs(tx-ty)<1e-12:
            distance=tx
            if occupied(col+sx,row) or occupied(col,row+sy):return max(0.,distance)
            col+=sx;row+=sy;tx+=dtx;ty+=dty
        elif tx<ty:distance=tx;col+=sx;tx+=dtx
        else:distance=ty;row+=sy;ty+=dty
        if occupied(col,row):return max(0.,distance)
    raise GeometryError('Raster normal ray traversal exhausted map dimensions')


def validate_raster_corridor(sampled,raster,vehicle,limits):
    footprint=validate_raster_footprint(sampled,raster,vehicle,limits.footprint_margin_m)
    widths=[];sides=[]
    for p in sampled.states[:-1]:
        n=(-math.sin(p.heading),math.cos(p.heading))
        left=raster_ray_distance(p,n,raster);right=raster_ray_distance(p,(-n[0],-n[1]),raster)
        widths.append(left+right);sides.append(min(left,right))
    minimum=min(widths)
    if minimum-2*limits.footprint_margin_m<limits.minimum_usable_width_m:
        raise GeometryError('Measured raster normal width below usable-width requirement')
    return dict(raster_footprint=footprint,minimum_raster_width_m=minimum,
        minimum_raster_side_clearance_m=min(sides),raster_width_poses_checked=len(widths),
        raster_width_measurement='exact normal ray traversal of occupied cell rectangles at every retained pose')
