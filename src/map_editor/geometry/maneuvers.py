"""Requested maneuver labels are explicit; measurement must confirm them."""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
import random
from .curves import CurvatureSegment, Frame, GeometryError, finite


@dataclass(frozen=True)
class Maneuver:
    type: str
    direction: str
    segments: tuple[CurvatureSegment, ...]
    requested: dict

    def __post_init__(self):
        allowed = {"straight": {"none"}, "hairpin": {"left", "right"},
                   "sweeper": {"left", "right"}, "chicane": {"left_right", "right_left"},
                   "s_curve": {"left_right", "right_left"},
                   "transition": {"none", "left", "right", "left_right", "right_left"}}
        if self.type not in allowed or self.direction not in allowed[self.type]:
            raise GeometryError("Unknown maneuver type or incompatible direction")
        if not self.segments:
            raise GeometryError("Maneuver needs at least one nonzero segment")
        for a, b in zip(self.segments, self.segments[1:]):
            if abs(a.k_end-b.k_start) > 1e-10:
                raise GeometryError("Maneuver has an internal curvature discontinuity")

    @property
    def length_m(self):
        return sum(s.length_m for s in self.segments)

    def at(self, s: float, frame=Frame()):
        finite(s)
        if not 0 <= s <= self.length_m + 1e-10:
            raise GeometryError("Arc position lies outside the maneuver")
        distance = 0.
        for segment in self.segments:
            if s <= distance + segment.length_m + 1e-12:
                value = segment.at(min(segment.length_m, max(0., s-distance)), frame)
                return replace(value, s=s)
            frame = segment.at(segment.length_m, frame).frame
            distance += segment.length_m
        raise GeometryError("Cannot evaluate maneuver")

    def sample(self, spacing, frame=Frame()):
        states, distance = [], 0.
        for segment in self.segments:
            sampled = segment.sample(spacing, frame)
            states.extend(replace(p, s=p.s+distance) for p in (sampled if not states else sampled[1:]))
            frame = sampled[-1].frame
            distance += segment.length_m
        return tuple(states)

    def mirrored(self):
        directions = {"left": "right", "right": "left", "none": "none",
                      "left_right": "right_left", "right_left": "left_right"}
        requested = dict(self.requested)
        if "direction" in requested:
            requested["direction"] = directions[self.direction]
        for key in ("k_start_inv_m", "k_end_inv_m"):
            if key in requested:
                requested[key] = -requested[key]
        return Maneuver(self.type, directions[self.direction],
            tuple(replace(s, k_start=-s.k_start, k_end=-s.k_end) for s in self.segments), requested)


def _sign(direction):
    if direction not in {"left", "right"}:
        raise GeometryError("Turn direction must be left or right")
    return 1 if direction == "left" else -1


def straight(length_m):
    return Maneuver("straight", "none", (CurvatureSegment(length_m),), {"length_m": length_m})


def transition(length_m, k_start_inv_m, k_end_inv_m, ramp="smoothstep"):
    signs = ["left" if k > 0 else "right" for k in (k_start_inv_m, k_end_inv_m) if abs(k) > 1e-12]
    direction = "none" if not signs else signs[0] if len(set(signs)) == 1 else "_".join(signs)
    return Maneuver("transition", direction, (CurvatureSegment(length_m, k_start_inv_m, k_end_inv_m, ramp),),
                    dict(length_m=length_m, k_start_inv_m=k_start_inv_m, k_end_inv_m=k_end_inv_m, ramp=ramp))


def _bend(radius_m, turn_angle_rad, direction, entry_transition_m, exit_transition_m, end_radius_m=None):
    values = [radius_m, turn_angle_rad, entry_transition_m, exit_transition_m]
    if end_radius_m is not None:
        values.append(end_radius_m)
    finite(*values)
    if radius_m <= 0 or (end_radius_m is not None and end_radius_m <= 0) or turn_angle_rad <= 0:
        raise GeometryError("Radius and turn angle must be positive")
    if min(entry_transition_m, exit_transition_m) < 0:
        raise GeometryError("Transition lengths must be nonnegative")
    sign = _sign(direction)
    k0, k1 = sign/radius_m, sign/(end_radius_m or radius_m)
    budget = turn_angle_rad - (abs(k0)*entry_transition_m + abs(k1)*exit_transition_m)/2
    if budget <= 1e-8:
        raise GeometryError("Turn angle is too small for requested radii and transitions")
    segments = []
    if entry_transition_m:
        segments.append(CurvatureSegment(entry_transition_m, 0, k0))
    segments.append(CurvatureSegment(2*budget/(abs(k0)+abs(k1)), k0, k1))
    if exit_transition_m:
        segments.append(CurvatureSegment(exit_transition_m, k1, 0))
    return tuple(segments)


def hairpin(radius_m, turn_angle_rad=math.pi, direction="left", entry_transition_m=1., exit_transition_m=1.):
    params = dict(radius_m=radius_m, turn_angle_rad=turn_angle_rad, direction=direction,
                  entry_transition_m=entry_transition_m, exit_transition_m=exit_transition_m)
    return Maneuver("hairpin", direction, _bend(**params), params)


def sweeper(radius_m, turn_angle_rad, direction="left", entry_transition_m=0., exit_transition_m=0., end_radius_m=None):
    params = dict(radius_m=radius_m, turn_angle_rad=turn_angle_rad, direction=direction,
                  entry_transition_m=entry_transition_m, exit_transition_m=exit_transition_m, end_radius_m=end_radius_m)
    return Maneuver("sweeper", direction, _bend(**params), params)


def _opposing(radius1, radius2, angle, ramp_length, separation):
    first = _bend(radius1, angle, "left", ramp_length, ramp_length)
    second = _bend(radius2, angle, "right", ramp_length, ramp_length)
    middle = (CurvatureSegment(separation),) if separation > 0 else ()
    return first + middle + second


def chicane(radius_m, lateral_displacement_m, separation_m=0., transition_length_m=1., direction="left_right"):
    finite(radius_m, lateral_displacement_m, separation_m, transition_length_m)
    if min(radius_m, lateral_displacement_m) <= 0 or min(separation_m, transition_length_m) < 0:
        raise GeometryError("Invalid chicane dimensions")
    if direction not in {"left_right", "right_left"}:
        raise GeometryError("Chicane requires opposing turn directions")
    lo, hi = transition_length_m/radius_m + 1e-7, math.pi/2
    if lo >= hi:
        raise GeometryError("Chicane transitions exceed the available turn budget")
    def make(angle):
        return Maneuver("chicane", "left_right", _opposing(radius_m, radius_m, angle, transition_length_m, separation_m), {})
    if not make(lo).at(make(lo).length_m).y <= lateral_displacement_m <= make(hi).at(make(hi).length_m).y:
        raise GeometryError("Lateral displacement cannot be met with these radius/separation/transition constraints")
    for _ in range(60):
        mid = (lo+hi)/2
        curve = make(mid)
        if curve.at(curve.length_m).y < lateral_displacement_m:
            lo = mid
        else:
            hi = mid
    curve = make((lo+hi)/2)
    if direction == "right_left":
        curve = curve.mirrored()
    return replace(curve, requested=dict(radius_m=radius_m, lateral_displacement_m=lateral_displacement_m,
        separation_m=separation_m, transition_length_m=transition_length_m, direction=direction))


def s_curve(radii_m=(5., 7.), turn_angle_rad=math.pi/3, transition_length_m=1., direction="left_right"):
    if len(radii_m) != 2 or direction not in {"left_right", "right_left"}:
        raise GeometryError("S-curve needs two radii and opposing turn directions")
    curve = Maneuver("s_curve", "left_right", _opposing(*radii_m, turn_angle_rad, transition_length_m, 0.),
        dict(radii_m=list(radii_m), turn_angle_rad=turn_angle_rad,
             transition_length_m=transition_length_m, direction="left_right"))
    return curve if direction == "left_right" else curve.mirrored()


def sample_parameters(ranges: dict[str, tuple[float, float]], seed: int):
    if type(seed) is not int or seed < 0:
        raise GeometryError("Seed must be a nonnegative integer")
    rng, result = random.Random(seed), {}
    for name, bounds in sorted(ranges.items()):
        if len(bounds) != 2:
            raise GeometryError("Parameter ranges must contain two bounds")
        lo, hi = bounds
        finite(lo, hi)
        if lo > hi:
            raise GeometryError("Parameter range bounds are reversed")
        result[name] = rng.uniform(lo, hi)
    return result
