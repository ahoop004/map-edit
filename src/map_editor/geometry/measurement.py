"""Measurements and acceptance tests of the final sampled differential geometry."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
import numpy as np
from .curves import GeometryError, finite


@dataclass(frozen=True)
class MeasurementTolerances:
    length_abs_m: float = 1e-4
    length_relative: float = .002
    angle_rad: float = .005
    curvature_inv_m: float = .002
    straightness_m: float = .001
    sign_epsilon_inv_m: float = 1e-5
    hairpin_min_angle_rad: float = math.radians(150)
    hairpin_max_angle_rad: float = math.radians(210)
    minimum_lobe_angle_rad: float = .05
    displacement_m: float = .002

    def __post_init__(self):
        finite(*asdict(self).values())
        if min(asdict(self).values()) < 0 or self.hairpin_min_angle_rad >= self.hairpin_max_angle_rad:
            raise GeometryError("Invalid measurement tolerances")


def position_curvatures(states):
    points=np.array([(p.x,p.y) for p in states])
    if len(points)<3:
        return np.zeros(len(points))
    a,b=np.diff(points,axis=0)[:-1],np.diff(points,axis=0)[1:]
    denominator=np.linalg.norm(a,axis=1)*np.linalg.norm(b,axis=1)*np.linalg.norm(a+b,axis=1)
    if np.any(denominator<=1e-15):
        raise GeometryError("Degenerate samples cannot be measured")
    middle=2*(a[:,0]*b[:,1]-a[:,1]*b[:,0])/denominator
    return np.r_[middle[0],middle,middle[-1]]


def measure(states,*,width_m=None,tolerances=MeasurementTolerances()):
    if len(states)<3:
        raise GeometryError("At least three samples are required for measurement")
    if not all(math.isfinite(value) for p in states
               for value in (p.s,p.x,p.y,p.heading,p.curvature,p.curvature_rate)):
        raise GeometryError("Sampled geometry must contain finite values")
    xy=np.array([(p.x,p.y) for p in states])
    ds=np.diff([p.s for p in states])
    chords=np.linalg.norm(np.diff(xy,axis=0),axis=1)
    if np.any(ds<=0) or np.any(chords<=1e-10):
        raise GeometryError("Degenerate or unordered samples")
    heading=np.array([p.heading for p in states])  # unwrapped by construction
    chord_angles=np.arctan2(np.diff(xy[:,1]),np.diff(xy[:,0]))
    angle_error=chord_angles-(heading[:-1]+heading[1:])/2
    tangent_error=float(max(abs(np.arctan2(np.sin(angle_error),np.cos(angle_error)))))
    k=np.array([p.curvature for p in states])
    k_geom=position_curvatures(states)
    curvature_error=float(np.max(abs(k_geom[1:-1]-k[1:-1])))
    direction_signs=[]
    lobe_changes=[]
    for i in range(len(ds)):
        angle=heading[i+1]-heading[i]
        average=(k[i]+k[i+1])/2
        sign=1 if average>tolerances.sign_epsilon_inv_m else -1 if average < -tolerances.sign_epsilon_inv_m else 0
        if sign:
            if not direction_signs or sign!=direction_signs[-1]:
                direction_signs.append(sign)
                lobe_changes.append(0.)
            lobe_changes[-1]+=abs(float(angle))
    axis=xy[-1]-xy[0]
    axis_length=np.linalg.norm(axis)
    if axis_length<1e-9:
        deviation=float(np.max(np.linalg.norm(xy-xy[0],axis=1)))
    else:
        deviation=float(np.max(abs((xy[:,0]-xy[0,0])*axis[1]-(xy[:,1]-xy[0,1])*axis[0]))/axis_length)
    max_k=float(max(abs(k)))
    result=dict(length_m=float(sum(chords)),curve_arc_length_m=float(sum(ds)),
        signed_heading_change_rad=float(heading[-1]-heading[0]),
        absolute_heading_change_rad=float(sum(abs(np.diff(heading)))),
        minimum_curvature_inv_m=float(min(k)),maximum_curvature_inv_m=float(max(k)),
        minimum_radius_m=1/max_k if max_k>1e-12 else None,
        maximum_curvature_rate_inv_m2=float(max(abs(np.diff(k)/ds))),
        maximum_sampled_curvature_rate_inv_m2=max(abs(p.curvature_rate) for p in states),
        start_heading_rad=float(heading[0]),end_heading_rad=float(heading[-1]),
        start_curvature_inv_m=float(k[0]),end_curvature_inv_m=float(k[-1]),
        straightness_deviation_m=deviation,direction_reversals=max(0,len(direction_signs)-1),
        turn_signs=direction_signs,lobe_heading_changes_rad=lobe_changes,
        geometric_curvature_error_inv_m=curvature_error,
        maximum_tangent_error_rad=tangent_error,
        geometric_minimum_radius_m=float(1/max(abs(k_geom))) if max(abs(k_geom))>1e-10 else None,
        lateral_displacement_m=float(-(xy[-1,0]-xy[0,0])*math.sin(heading[0])+(xy[-1,1]-xy[0,1])*math.cos(heading[0])),
        corridor_width_m=width_m)
    return result


def validate_maneuver(maneuver,states,*,width_m=None,tolerances=MeasurementTolerances()):
    m=measure(states,width_m=width_m,tolerances=tolerances)
    p=maneuver.requested
    errors=[]
    length_tolerance=max(tolerances.length_abs_m,tolerances.length_relative*maneuver.length_m)
    if abs(m["length_m"]-maneuver.length_m)>length_tolerance:
        errors.append("measured arc length")
    if "length_m" in p and abs(m["length_m"]-p["length_m"])>length_tolerance:
        errors.append("requested length")
    # Differential fields must agree with independently reconstructed curvature.
    # dk/ds times the spacing bounds finite-difference error at short transitions.
    spacing=max(b.s-a.s for a,b in zip(states,states[1:]))
    curvature_tolerance=tolerances.curvature_inv_m+spacing*m["maximum_sampled_curvature_rate_inv_m2"]
    if m["maximum_tangent_error_rad"]>tolerances.angle_rad+spacing**2*m["maximum_sampled_curvature_rate_inv_m2"]:
        errors.append("position/tangent consistency")
    if m["geometric_curvature_error_inv_m"]>curvature_tolerance:
        errors.append("position/curvature consistency")
    expected={"left":[1],"right":[-1],"left_right":[1,-1],"right_left":[-1,1],"none":[]}[maneuver.direction]
    if m["turn_signs"]!=expected:
        errors.append("turn direction sequence")
    if maneuver.type=="straight":
        if m["straightness_deviation_m"]>tolerances.straightness_m or m["absolute_heading_change_rad"]>tolerances.angle_rad:
            errors.append("straightness")
    if maneuver.type in {"hairpin","sweeper"}:
        turn=abs(m["signed_heading_change_rad"])
        if "turn_angle_rad" in p and abs(turn-p["turn_angle_rad"])>tolerances.angle_rad:
            errors.append("requested turn angle")
        if maneuver.type=="hairpin" and not tolerances.hairpin_min_angle_rad-tolerances.angle_rad<=turn<=tolerances.hairpin_max_angle_rad+tolerances.angle_rad:
            errors.append("hairpin heading-reversal range")
        expected_k=max(1/p["radius_m"],1/(p.get("end_radius_m") or p["radius_m"]))
        if abs(max(abs(m["minimum_curvature_inv_m"]),abs(m["maximum_curvature_inv_m"]))-expected_k)>tolerances.curvature_inv_m:
            errors.append("requested radius")
    if maneuver.type in {"chicane","s_curve"}:
        if m["direction_reversals"]!=1 or min(m["lobe_heading_changes_rad"],default=0)<tolerances.minimum_lobe_angle_rad:
            errors.append("opposing turn lobes")
        if abs(m["signed_heading_change_rad"])>tolerances.angle_rad:
            errors.append("exit heading")
        radii = p.get("radii_m", [p.get("radius_m"), p.get("radius_m")])
        peaks = [m["maximum_curvature_inv_m"], -m["minimum_curvature_inv_m"]]
        if maneuver.direction == "right_left":
            peaks.reverse()
        if any(r is None or abs(k-1/r)>tolerances.curvature_inv_m for k,r in zip(peaks,radii)):
            errors.append("requested opposing radii")
        if maneuver.type=="s_curve" and any(abs(angle-p["turn_angle_rad"])>tolerances.angle_rad for angle in m["lobe_heading_changes_rad"]):
            errors.append("requested lobe angles")
        if maneuver.type=="chicane" and abs(abs(m["lateral_displacement_m"])-p["lateral_displacement_m"])>tolerances.displacement_m:
            errors.append("requested lateral displacement")
    if maneuver.type=="transition":
        if abs(m["start_curvature_inv_m"]-p["k_start_inv_m"])>tolerances.curvature_inv_m or abs(m["end_curvature_inv_m"]-p["k_end_inv_m"])>tolerances.curvature_inv_m:
            errors.append("transition endpoint curvature")
    if errors:
        raise GeometryError(f"Invalid {maneuver.type}: {', '.join(errors)}")
    return m
