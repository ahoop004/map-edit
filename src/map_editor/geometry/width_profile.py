"""Periodic, independently controlled C1 left/right normal offsets."""
from dataclasses import dataclass
import math
import numpy as np
from .curves import GeometryError


@dataclass(frozen=True)
class WidthProfile:
    left: tuple[tuple[float,float],...] = ((0.,.75),(1.,.75))
    right: tuple[tuple[float,float],...] = ((0.,.75),(1.,.75))
    maximum_gradient: float = .12

    def __post_init__(self):
        if isinstance(self.maximum_gradient,bool) or not math.isfinite(self.maximum_gradient) or self.maximum_gradient<=0:
            raise GeometryError('Width gradient limit must be finite and positive')
        for side in ('left','right'):
            knots=tuple(tuple(k) for k in getattr(self,side))
            if len(knots)<2 or any(len(k)!=2 or not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in k) for k in knots):
                raise GeometryError('Width knots require finite fraction/offset pairs')
            if knots[0][0]!=0 or knots[-1][0]!=1 or knots[0][1]!=knots[-1][1]:
                raise GeometryError('Periodic widths need equal offsets at fractions zero and one')
            if any(b[0]<=a[0] for a,b in zip(knots,knots[1:])) or any(k[1]<=0 for k in knots):
                raise GeometryError('Width fractions must increase and offsets must be positive')
            object.__setattr__(self,side,knots)

    @classmethod
    def constant(cls,width_m,left_fraction=.5):
        if not 0<left_fraction<1:
            raise GeometryError('Constant width left fraction must lie in (0,1)')
        return cls(((0.,width_m*left_fraction),(1.,width_m*left_fraction)),
                   ((0.,width_m*(1-left_fraction)),(1.,width_m*(1-left_fraction))))

    def evaluate(self,positions,lap_m):
        if not math.isfinite(lap_m) or lap_m<=0:
            raise GeometryError('Width evaluation needs positive lap length')
        result=[]
        u=np.asarray(positions,dtype=float)%lap_m/lap_m
        if not np.isfinite(u).all():raise GeometryError('Nonfinite width positions')
        for side in (self.left,self.right):
            fraction=np.array([p[0] for p in side]);offset=np.array([p[1] for p in side])
            gradient=1.5*abs(np.diff(offset))/(np.diff(fraction)*lap_m)
            if max(gradient)>self.maximum_gradient+1e-12:
                raise GeometryError('Requested width transition exceeds the designated gradient bound')
            index=np.clip(np.searchsorted(fraction,u,side='right')-1,0,len(side)-2)
            t=(u-fraction[index])/(fraction[index+1]-fraction[index])
            result.append(offset[index]+(offset[index+1]-offset[index])*(3*t*t-2*t*t*t))
        return tuple(result)
