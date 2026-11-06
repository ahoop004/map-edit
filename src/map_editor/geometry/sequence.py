"""Rigid placement and checked connections; no closure fitting or rescaling."""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
from .curves import Frame, GeometryError, State, finite
from .maneuvers import Maneuver


def heading_difference(a,b):
    return math.atan2(math.sin(a-b),math.cos(a-b))


@dataclass(frozen=True)
class ContinuityTolerances:
    position_m: float = 1e-7
    heading_rad: float = 1e-7
    curvature_inv_m: float = 1e-7

    def __post_init__(self):
        finite(self.position_m,self.heading_rad,self.curvature_inv_m)
        if min(self.position_m,self.heading_rad,self.curvature_inv_m) < 0:
            raise GeometryError("Continuity tolerances must be nonnegative")


@dataclass(frozen=True)
class PlacedManeuver:
    maneuver: Maneuver
    frame: Frame

    @property
    def end(self):
        return self.maneuver.at(self.maneuver.length_m,self.frame)


@dataclass(frozen=True)
class SampledSequence:
    states: tuple[State,...]  # includes terminal vertex even for closed geometry
    spans: tuple[tuple[int,int],...]
    maneuvers: tuple[Maneuver,...]
    closed: bool
    joints: tuple[dict,...]

    @property
    def length_m(self):
        return self.states[-1].s

    @property
    def points(self):
        from map_editor.models.annotations import Point2D
        return [Point2D(p.x,p.y) for p in (self.states[:-1] if self.closed else self.states)]


class GeometrySequence:
    def __init__(self, maneuvers=(), *, frame=Frame(), require_g2=True, tolerances=ContinuityTolerances()):
        self.start=frame
        self.require_g2=require_g2
        self.tolerances=tolerances
        self.placements=[]
        self.joints=[]
        for maneuver in maneuvers:
            self.append(maneuver)

    def _check(self,end,start):
        residual=dict(position_m=math.hypot(end.x-start.x,end.y-start.y),
                      heading_rad=abs(heading_difference(end.heading,start.heading)),
                      curvature_inv_m=abs(end.curvature-start.curvature))
        tol=self.tolerances
        if residual["position_m"] > tol.position_m or residual["heading_rad"] > tol.heading_rad:
            raise GeometryError(f"Position/tangent discontinuity: {residual}")
        if self.require_g2 and residual["curvature_inv_m"] > tol.curvature_inv_m:
            raise GeometryError(f"Curvature discontinuity: {residual}")
        return residual

    def append(self,maneuver,*,frame=None):
        previous=self.placements[-1].end if self.placements else None
        frame=frame or (previous.frame if previous else self.start)
        if previous:
            self.joints.append(self._check(previous,maneuver.at(0,frame)))
            # Equivalent headings differing by 2*pi must not create an artificial
            # revolution in the sampled, unwrapped heading signal.
            frame=Frame(frame.x,frame.y,previous.heading+heading_difference(frame.heading,previous.heading))
        self.placements.append(PlacedManeuver(maneuver,frame))
        return self

    def sample(self,spacing,*,closed=False,check_intersections=True):
        if not self.placements:
            raise GeometryError("Cannot sample an empty sequence")
        joints=list(self.joints)
        if closed:
            joints.append(self._check(self.placements[-1].end,
                          self.placements[0].maneuver.at(0,self.placements[0].frame)))
        states,spans,distance=[],[],0.
        for placed in self.placements:
            sampled=placed.maneuver.sample(spacing,placed.frame)
            start=max(0,len(states)-1)
            states.extend(replace(p,s=p.s+distance) for p in (sampled if not states else sampled[1:]))
            spans.append((start,len(states)-1))
            distance+=placed.maneuver.length_m
        result=SampledSequence(tuple(states),tuple(spans),tuple(p.maneuver for p in self.placements),closed,tuple(joints))
        for a,b in zip(states,states[1:]):
            ds=b.s-a.s
            chord=math.hypot(b.x-a.x,b.y-a.y)
            if ds <= 0 or chord <= 1e-10 or chord > ds+1e-7 or chord < .99*ds:
                raise GeometryError("Arc-length inconsistency or insufficient sampling resolution")
            if abs(b.heading-a.heading) > .2:
                raise GeometryError("Heading changes exceed 0.2 rad per sample; use finer spacing")
        if check_intersections:
            from .spatial import self_intersects
            if self_intersects(result.points,closed=closed):
                raise GeometryError("Centerline self-intersects")
        return result
