"""Explicit schema-2 technical corners using the physical-curvature backend."""
from dataclasses import asdict, dataclass
import math
from .curves import CurvatureSegment, GeometryError, finite
from .maneuvers import Maneuver
from .measurement import validate_maneuver

PRIMITIVE_VERSION='technical_corners.v1'


@dataclass(frozen=True)
class CornerTolerances:
    angle_rad: float = .005
    curvature_inv_m: float = .002
    radius_relative: float = .01
    minimum_apex_contrast_inv_m: float = .03


@dataclass(frozen=True)
class TechnicalManeuver(Maneuver):
    def __post_init__(self):
        if self.type not in {'corner','kink','compound_corner'} or self.direction not in {'left','right'}:
            raise GeometryError('Invalid technical maneuver vocabulary/direction')
        if not self.segments or any(abs(a.k_end-b.k_start)>1e-10 for a,b in zip(self.segments,self.segments[1:])):
            raise GeometryError('Technical corners require continuous curvature')

    def mirrored(self):
        from dataclasses import replace
        return replace(self,direction='right' if self.direction=='left' else 'left',
            segments=tuple(replace(s,k_start=-s.k_start,k_end=-s.k_end) for s in self.segments),
            requested=dict(self.requested,direction='right' if self.direction=='left' else 'left'))


def technical_corner(radius_m=2., turn_angle_deg=90., direction='left', transition_m=.65,
                     end_radius_m=None, apex_radii_m=None, kind='corner'):
    """Body knots are interpolated with smoothstep; their equal-length cells
    integrate exactly to the requested angle. End ramps are part of the request.
    Compound knots include two distinct maxima separated by lower curvature.
    """
    end_radius_m=radius_m if end_radius_m is None else end_radius_m
    radii=list(apex_radii_m) if apex_radii_m is not None else [radius_m,end_radius_m]
    finite(radius_m,end_radius_m,turn_angle_deg,transition_m,*radii)
    if direction not in {'left','right'} or kind not in {'corner','kink','compound_corner'}:
        raise GeometryError('Invalid technical corner kind/direction')
    lo,hi=(5,35) if kind=='kink' else (30,150) if kind=='corner' else (30,210)
    if not lo<=turn_angle_deg<=hi or min(radii)<=0 or transition_m<=0:
        raise GeometryError('Technical angle/radius/transition outside its classification contract')
    if len(radii)<2 or (kind!='compound_corner' and apex_radii_m is not None):
        raise GeometryError('Only compound corners accept explicit body apex knots')
    if kind=='compound_corner':
        if len(radii)<5:
            raise GeometryError('Compound corner needs at least five body radius knots')
        k=[1/r for r in radii]
        peaks=[i for i in range(1,len(k)-1) if k[i]>k[i-1]+.03 and k[i]>k[i+1]+.03]
        if len(peaks)<2:
            raise GeometryError('Compound corner needs two measured separated curvature maxima')
    sign=1 if direction=='left' else -1
    knots=[sign/r for r in radii]
    remainder=math.radians(turn_angle_deg)-transition_m*(abs(knots[0])+abs(knots[-1]))/2
    mean_integral=sum((abs(a)+abs(b))/2 for a,b in zip(knots,knots[1:]))
    if remainder<=.03:
        raise GeometryError('Requested angle too small for the fixed end transitions')
    cell_length=remainder/mean_integral
    segments=(CurvatureSegment(transition_m,0,knots[0]),
        *(CurvatureSegment(cell_length,a,b) for a,b in zip(knots,knots[1:])),
        CurvatureSegment(transition_m,knots[-1],0))
    profile='compound' if kind=='compound_corner' else 'constant' if radius_m==end_radius_m else 'increasing_radius' if end_radius_m>radius_m else 'decreasing_radius'
    request=dict(primitive_version=PRIMITIVE_VERSION,radius_m=radius_m,end_radius_m=end_radius_m,
        turn_angle_deg=turn_angle_deg,direction=direction,transition_m=transition_m,
        apex_radii_m=list(apex_radii_m) if apex_radii_m is not None else None,kind=kind,profile=profile,
        body_radius_knots_m=radii,body_cell_length_m=cell_length)
    return TechnicalManeuver(kind,direction,tuple(segments),request)


def validate_technical(maneuver,states,width_m=None,tolerances=CornerTolerances()):
    m=validate_maneuver(maneuver,states,width_m=width_m)
    p=maneuver.requested
    expected=technical_corner(**{k:p[k] for k in ('radius_m','turn_angle_deg','direction','transition_m',
        'end_radius_m','apex_radii_m','kind')})
    if expected.type!=maneuver.type or expected.requested['profile']!=p['profile']:
        raise GeometryError('Technical classification does not match the requested geometry')
    if abs(abs(m['signed_heading_change_rad'])-math.radians(p['turn_angle_deg']))>tolerances.angle_rad:
        raise GeometryError('Achieved technical corner angle differs from request')
    # Evaluate requested knot locations from measured samples, not constructor labels.
    sign=1 if maneuver.direction=='left' else -1
    locations=[p['transition_m']+i*p['body_cell_length_m'] for i in range(len(p['body_radius_knots_m']))]
    import numpy as np
    origin=states[0].s
    measured_k=np.interp(locations,[s.s-origin for s in states],[sign*s.curvature for s in states])
    requested_k=np.array([1/r for r in p['body_radius_knots_m']])
    if max(abs(measured_k-requested_k))>tolerances.curvature_inv_m:
        raise GeometryError('Achieved technical radius knots differ from request')
    if any(abs(1/k-r)/r>tolerances.radius_relative for k,r in zip(measured_k,p['body_radius_knots_m'])):
        raise GeometryError('Achieved technical radii exceed relative tolerance')
    if maneuver.type=='compound_corner':
        peaks=[i for i in range(1,len(measured_k)-1)
               if measured_k[i]>measured_k[i-1]+tolerances.minimum_apex_contrast_inv_m
               and measured_k[i]>measured_k[i+1]+tolerances.minimum_apex_contrast_inv_m]
        if len(peaks)<2:
            raise GeometryError('Compound classification lacks two achieved curvature maxima')
    m.update(classification_version=PRIMITIVE_VERSION,profile=p['profile'],
        achieved_body_radii_m=(1/measured_k).tolist(),requested_geometry=p,
        classification_tolerances=asdict(tolerances))
    return m
