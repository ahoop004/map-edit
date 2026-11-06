"""Hard geometric checks and explicitly separate kinematic/dynamic advisories."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import numpy as np
import yaml
from map_editor.models.annotations import Point2D
from .curves import GeometryError, finite
from .spatial import edges, self_intersects, minimum_boundary_separation, _index, _cells


@dataclass(frozen=True)
class VehicleProfile:
    length_m: float
    width_m: float
    lf_m: float
    lr_m: float
    steering_min_rad: float
    steering_max_rad: float
    steering_rate_min_rad_s: float
    steering_rate_max_rad_s: float
    source: str
    source_sha256: str
    calibration_status: str = "unknown"

    def __post_init__(self):
        finite(self.length_m,self.width_m,self.lf_m,self.lr_m,self.steering_min_rad,
               self.steering_max_rad,self.steering_rate_min_rad_s,self.steering_rate_max_rad_s)
        if min(self.length_m,self.width_m,self.lf_m,self.lr_m)<=0:
            raise GeometryError("Vehicle dimensions must be positive")
        if not -math.pi/2<self.steering_min_rad<0<self.steering_max_rad<math.pi/2:
            raise GeometryError("Invalid steering angle bounds")
        if not self.steering_rate_min_rad_s<0<self.steering_rate_max_rad_s:
            raise GeometryError("Invalid steering rate bounds")

    @classmethod
    def from_yaml(cls,path: Path):
        raw=path.read_bytes()
        data=yaml.safe_load(raw)
        if not isinstance(data,dict) or not isinstance(data.get("calibration",{}),dict):
            raise GeometryError("Use a resolved vehicle configuration mapping")
        try:
            actuators=data.get("wheel_actuators")
            bounds=([actuators[k] for k in ("steering_min","steering_max","steering_rate_min","steering_rate_max")]
                    if actuators else [data[k] for k in ("s_min","s_max","sv_min","sv_max")])
            return cls(float(data["length"]),float(data["width"]),float(data["lf"]),float(data["lr"]),
                       *map(float,bounds),path.name,hashlib.sha256(raw).hexdigest(),
                       data.get("calibration",{}).get("status","unknown"))
        except (KeyError,TypeError,ValueError) as exc:
            raise GeometryError("Use a resolved vehicle configuration containing dimensions, axles and steering bounds") from exc


@dataclass(frozen=True)
class GeometryLimits:
    minimum_radius_m: float = .5
    minimum_usable_width_m: float = .7
    maximum_curvature_rate_inv_m2: float = 2.
    footprint_margin_m: float = .02
    minimum_nonlocal_boundary_gap_m: float = .1

    def __post_init__(self):
        finite(*asdict(self).values())
        if min(self.minimum_radius_m,self.minimum_usable_width_m,self.maximum_curvature_rate_inv_m2)<=0 or min(self.footprint_margin_m,self.minimum_nonlocal_boundary_gap_m)<0:
            raise GeometryError("Invalid geometry limits")


def offset_boundaries(sampled,width_m):
    finite(width_m)
    if width_m<=0:
        raise GeometryError("Corridor width must be positive")
    states=sampled.states[:-1] if sampled.closed else sampled.states
    if any(abs(p.curvature)*width_m/2>=1 for p in states):
        raise GeometryError("Offset boundary has a curvature singularity")
    return [[Point2D(p.x-sign*width_m/2*math.sin(p.heading),p.y+sign*width_m/2*math.cos(p.heading))
             for p in states] for sign in (1,-1)]


def footprint_corners(state,vehicle,margin=0.):
    co,si=math.cos(state.heading),math.sin(state.heading)
    a,b=vehicle.length_m/2+margin,vehicle.width_m/2+margin
    return [Point2D(state.x+co*x-si*y,state.y+si*x+co*y) for x,y in [(a,b),(a,-b),(-a,-b),(-a,b)]]


def validate_geometry(sampled,width_m,*,limits=GeometryLimits(),vehicle=None):
    if any(joint["curvature_inv_m"]>1e-7 for joint in sampled.joints):
        raise GeometryError("Curvature jumps have unbounded curvature-change rate")
    walls=offset_boundaries(sampled,width_m)
    if self_intersects(sampled.points,closed=sampled.closed):
        raise GeometryError("Centerline self-intersects")
    if any(self_intersects(wall,closed=sampled.closed) for wall in walls):
        raise GeometryError("Boundary self-intersects")
    gap=minimum_boundary_separation(*walls,closed=sampled.closed)
    usable=gap-2*limits.footprint_margin_m
    if usable < limits.minimum_usable_width_m:
        raise GeometryError(f"Global boundary separation {gap:.6f} m below usable width limit")
    nonlocal_gap=_nonlocal_gap_certificate(sampled,walls,width_m,limits.minimum_nonlocal_boundary_gap_m)
    k=max(abs(p.curvature) for p in sampled.states)
    rate=max(abs(p.curvature_rate) for p in sampled.states)
    if k and 1/k < limits.minimum_radius_m-1e-9:
        raise GeometryError("Minimum radius constraint violated")
    # Adjacent samples also catch G1 joins allowed explicitly by a caller.
    rate=max(rate,max(abs(b.curvature-a.curvature)/(b.s-a.s) for a,b in zip(sampled.states,sampled.states[1:])))
    if rate > limits.maximum_curvature_rate_inv_m2:
        raise GeometryError("Curvature-change rate exceeds geometry limit")
    report=dict(global_boundary_separation_m=gap,minimum_usable_corridor_width_m=usable,
                maximum_curvature_rate_inv_m2=rate,footprint="not_assessed",limits=asdict(limits))
    report["nonlocal_boundary_gap"]=nonlocal_gap
    if vehicle:
        segments=[edge for wall in walls for edge in edges(wall,sampled.closed)]
        size=max(vehicle.length_m,vehicle.width_m,width_m)
        grid=_index(segments,size)
        count,unassessed=0,0
        for state in sampled.states[:-1] if sampled.closed else sampled.states:
            if not sampled.closed and min(state.s,sampled.length_m-state.s)<vehicle.length_m/2+limits.footprint_margin_m:
                unassessed+=1
                continue
            corners=footprint_corners(state,vehicle,limits.footprint_margin_m)
            bounds=(min(p.x for p in corners),min(p.y for p in corners),max(p.x for p in corners),max(p.y for p in corners))
            candidates=set(j for cell in _cells(bounds,size) for j in grid.get(cell,()))
            from .spatial import _segments_intersect
            for j in candidates:
                a,b=segments[j]
                if (max(a.x,b.x)<bounds[0] or min(a.x,b.x)>bounds[2]
                        or max(a.y,b.y)<bounds[1] or min(a.y,b.y)>bounds[3]):
                    continue
                co,si=math.cos(state.heading),math.sin(state.heading)
                local_x=(a.x-state.x)*co+(a.y-state.y)*si
                local_y=-(a.x-state.x)*si+(a.y-state.y)*co
                contained=abs(local_x)<=vehicle.length_m/2+limits.footprint_margin_m and abs(local_y)<=vehicle.width_m/2+limits.footprint_margin_m
                if contained or any(_segments_intersect(c,d,a,b) for c,d in edges(corners,True)):
                    raise GeometryError("Sampled full-vehicle footprint intersects a boundary")
            count+=1
        report.update(footprint="passed_at_sampled_poses",footprint_poses_checked=count,
                      open_endpoint_poses_unassessed=unassessed,vehicle=asdict(vehicle))
    return walls,report


def _nonlocal_gap_certificate(sampled,walls,width_m,threshold):
    """Certify a lower bound for all boundary pairs beyond a local arc window.

    Same-wall neighboring edges have arbitrarily small distances by construction.
    Exclude centerline arc neighborhoods of 3*width, using periodic distance on
    closed paths. This is explicitly distinct from opposing-wall corridor width.
    """
    from .spatial import segment_distance
    segments=[edge for wall in walls for edge in edges(wall,sampled.closed)]
    count=len(edges(walls[0],sampled.closed))
    middle=[(a.s+b.s)/2 for a,b in zip(sampled.states,sampled.states[1:])]
    if not sampled.closed:
        middle=middle[:count]
    exclusion=3*width_m
    grid=_index(segments,max(width_m,threshold,1e-6))
    for i,(a,b) in enumerate(segments):
        bounds=(min(a.x,b.x)-threshold,min(a.y,b.y)-threshold,
                max(a.x,b.x)+threshold,max(a.y,b.y)+threshold)
        candidates=set(j for cell in _cells(bounds,max(width_m,threshold,1e-6)) for j in grid.get(cell,()))
        for j in candidates:
            if j<=i:
                continue
            distance=abs(middle[i%count]-middle[j%count])
            if sampled.closed:
                distance=min(distance,sampled.length_m-distance)
            if distance<=exclusion:
                continue
            if segment_distance(a,b,*segments[j])<threshold:
                raise GeometryError("Nonlocal boundary gap below configured minimum")
    return dict(lower_bound_m=threshold,local_arc_exclusion_m=exclusion,status="passed")


def validate_raster_footprint(sampled,raster,vehicle,margin_m=0.):
    """SAT intersection of every occupied cell with each sampled rectangle.

    This checks the FULL area, not only corners. It is not a continuous sweep.
    """
    pixels,width,height,ox,oy,resolution=raster
    mask=np.frombuffer(pixels,dtype=np.uint8).reshape(height,width)
    a,b=vehicle.length_m/2+margin_m,vehicle.width_m/2+margin_m
    checked=0
    for state in sampled.states[:-1] if sampled.closed else sampled.states:
        if not sampled.closed and min(state.s,sampled.length_m-state.s)<a:
            continue
        co,si=math.cos(state.heading),math.sin(state.heading)
        ex,ey=abs(co)*a+abs(si)*b,abs(si)*a+abs(co)*b
        c0,c1=math.floor((state.x-ex-ox)/resolution),math.floor((state.x+ex-ox)/resolution)
        r0,r1=math.floor((state.y-ey-oy)/resolution),math.floor((state.y+ey-oy)/resolution)
        if c0<0 or r0<0 or c1>=width or r1>=height:
            raise GeometryError("Footprint extends outside raster")
        cols,rows=np.meshgrid(np.arange(c0,c1+1),np.arange(r0,r1+1))
        dx=ox+(cols+.5)*resolution-state.x
        dy=oy+(rows+.5)*resolution-state.y
        half=resolution/2
        overlap=(abs(dx)<=ex+half)&(abs(dy)<=ey+half)
        overlap&=(abs(co*dx+si*dy)<=a+half*(abs(co)+abs(si)))
        overlap&=(abs(-si*dx+co*dy)<=b+half*(abs(co)+abs(si)))
        if np.any(overlap&(mask[height-1-rows,cols]==0)):
            raise GeometryError("Raster occupied cell overlaps sampled vehicle footprint")
        checked+=1
    return dict(status="passed_at_sampled_poses",poses_checked=checked,margin_m=margin_m)


def feasibility_advisory(sampled,vehicle,*,speed_m_s=2.,lateral_acceleration_limit_m_s2=None):
    finite(speed_m_s)
    if speed_m_s<0:
        raise GeometryError("Advisory speed must be nonnegative")
    k=np.array([p.curvature for p in sampled.states])
    rate=np.array([p.curvature_rate for p in sampled.states])
    wheelbase=vehicle.lf_m+vehicle.lr_m
    if np.any(abs(vehicle.lr_m*k)>=1):
        return {"status":"outside_kinematic_domain","physical_drivability":"unassessed"}
    root=np.sqrt(1-(vehicle.lr_m*k)**2)
    steering=np.arctan(wheelbase*k/root)
    derivative=wheelbase/(root**3*(1+(wheelbase*k/root)**2))
    steering_rate=derivative*rate*speed_m_s
    max_k=float(max(abs(k)))
    result=dict(status="advisory_only",physical_drivability="unassessed",speed_m_s=speed_m_s,
        maximum_abs_steering_rad=float(max(abs(steering))),
        steering_angle_within_bounds=bool(np.all((steering>=vehicle.steering_min_rad)&(steering<=vehicle.steering_max_rad))),
        maximum_abs_steering_rate_rad_s=float(max(abs(steering_rate))),
        steering_rate_within_bounds=bool(np.all((steering_rate>=vehicle.steering_rate_min_rad_s)&(steering_rate<=vehicle.steering_rate_max_rad_s))),
        required_lateral_acceleration_m_s2=speed_m_s**2*max_k,
        lateral_acceleration_limit_m_s2=lateral_acceleration_limit_m_s2,
        calibration_status=vehicle.calibration_status)
    if lateral_acceleration_limit_m_s2 is not None:
        finite(lateral_acceleration_limit_m_s2)
        if lateral_acceleration_limit_m_s2<=0:
            raise GeometryError("Lateral acceleration assumption must be positive")
        result["curvature_speed_limit_m_s"]=math.sqrt(lateral_acceleration_limit_m_s2/max_k) if max_k else None
    return result
