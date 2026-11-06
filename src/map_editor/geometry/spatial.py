"""Conservative grid broad phase, with exact segment narrow-phase predicates."""
from __future__ import annotations
from collections import defaultdict
import math
from statistics import median
from map_editor.services.procedural_track import _segments_intersect
from .curves import GeometryError


def edges(points, closed=False):
    return list(zip(points, [*points[1:], points[0]] if closed else points[1:]))


def _bounds(edge):
    a, b = edge
    return min(a.x,b.x), min(a.y,b.y), max(a.x,b.x), max(a.y,b.y)


def _cells(bounds, size):
    x0,y0,x1,y1 = (math.floor(v/size) for v in bounds)
    if (x1-x0+1)*(y1-y0+1) > 1000000:
        raise GeometryError("Spatial grid cell budget exceeded; use finer sampling")
    for x in range(x0,x1+1):
        for y in range(y0,y1+1):
            yield x,y


def _index(segments, size):
    grid = defaultdict(list)
    for i, edge in enumerate(segments):
        for cell in _cells(_bounds(edge), size):
            grid[cell].append(i)
    return grid


def self_intersects(points, *, closed=False, use_grid=True):
    segments = edges(points, closed)
    if not segments:
        return False
    lengths = [math.hypot(b.x-a.x,b.y-a.y) for a,b in segments]
    if min(lengths) <= 1e-10:
        raise GeometryError("Zero-length centerline or boundary edge")
    # Adjacent overlaps are not safe merely because they share a vertex.
    for i in range(len(segments) if closed else len(segments)-1):
        a,b = segments[i]
        _,c = segments[(i+1)%len(segments)]
        u,v = (b.x-a.x,b.y-a.y),(c.x-b.x,c.y-b.y)
        if abs(u[0]*v[1]-u[1]*v[0]) < 1e-12 and u[0]*v[0]+u[1]*v[1] < 0:
            return True
    size = max(median(lengths)*8, 1e-6)
    grid = _index(segments,size) if use_grid else None
    for i, edge in enumerate(segments):
        candidates = set(j for cell in _cells(_bounds(edge),size) for j in grid.get(cell,())) if grid is not None else range(i+1,len(segments))
        for j in sorted(candidates):
            if j <= i+1 or (closed and i == 0 and j == len(segments)-1):
                continue
            if _segments_intersect(*edge,*segments[j]):
                return True
    return False


def point_segment_distance(p,a,b):
    dx,dy=b.x-a.x,b.y-a.y
    norm=dx*dx+dy*dy
    t=max(0.,min(1.,((p.x-a.x)*dx+(p.y-a.y)*dy)/norm)) if norm else 0.
    return math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)


def segment_distance(a,b,c,d):
    if _segments_intersect(a,b,c,d):
        return 0.
    return min(point_segment_distance(a,c,d),point_segment_distance(b,c,d),
               point_segment_distance(c,a,b),point_segment_distance(d,a,b))


def minimum_boundary_separation(first,second,*,closed=False,use_grid=True):
    """Global distance between ALL opposing wall segments, not paired vertices."""
    left,right=edges(first,closed),edges(second,closed)
    if not left or not right:
        raise GeometryError("Need two boundaries with at least two vertices")
    best=segment_distance(*left[0],*right[0])
    if best == 0:
        return 0.
    size=max(best,1e-6)
    grid=_index(right,size) if use_grid else None
    for a,b in left:
        x0,y0,x1,y1=_bounds((a,b))
        candidates=set(j for cell in _cells((x0-best,y0-best,x1+best,y1+best),size)
                       for j in grid.get(cell,())) if grid is not None else range(len(right))
        for j in sorted(candidates):
            c,d=right[j]
            rx0,ry0,rx1,ry1=_bounds((c,d))
            if math.hypot(max(rx0-x1,x0-rx1,0),max(ry0-y1,y0-ry1,0)) > best:
                continue
            best=min(best,segment_distance(a,b,c,d))
            if best == 0:
                return 0.
    return best
