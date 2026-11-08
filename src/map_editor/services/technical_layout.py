"""Bounded convex closure with distributed adjustable straight connectors.

For fixed primary curves, final displacement is d + A*l. Curves are rigid;
only explicitly designated lengths l change. A third equality fixes lap length.
Dykstra projection minimizes ||l-target||^2 over affine closure and a box.
"""
from dataclasses import dataclass
import math
import random
import numpy as np
from map_editor.geometry import Frame, GeometryError, straight
from map_editor.services.composite_assembly import AssemblyItem, end_state, connector


@dataclass(frozen=True)
class LayoutCandidate:
    items: tuple
    frame: Frame
    solution: dict


def bounded_projection(matrix,rhs,target,lower,upper,iterations=2000):
    matrix=np.asarray(matrix,dtype=float);rhs=np.asarray(rhs,dtype=float)
    x=np.asarray(target,dtype=float).copy()
    if np.linalg.matrix_rank(matrix)<len(rhs):
        raise GeometryError('Distributed connector closure equality matrix is rank deficient')
    projection=matrix.T@np.linalg.inv(matrix@matrix.T)
    p=np.zeros_like(x);q=np.zeros_like(x)
    history=[]
    for count in range(1,iterations+1):
        previous=x.copy()
        z=x+p;y=z+projection@(rhs-matrix@z);p=z-y
        z=y+q;x=np.clip(z,lower,upper);q=z-x
        residual=float(np.max(abs(matrix@x-rhs)))
        if count==1 or count%100==0:
            history.append(dict(iteration=count,equality_residual=residual))
        if residual<1e-9 and (count==1 or np.max(abs(x-previous))<1e-9):
            # Final affine correction is roundoff sized; bounds are rechecked.
            x=x+projection@(rhs-matrix@x)
            if np.min(x)>=lower-1e-8 and np.max(x)<=upper+1e-8:
                return x,dict(iterations=count,residual=float(np.max(abs(matrix@x-rhs))),
                    objective_squared_distance=float(np.sum((x-target)**2)),history=history)
    error=GeometryError(f'Connector optimization exhausted {iterations} iterations; equality residual {residual:.6g}')
    error.optimization=dict(iterations=count,residual=residual,history=history)
    raise error


def layout_candidates(spec,journal):
    rng=random.Random(spec.seed)
    lo,hi=spec.connector_bounds_m
    for index in range(spec.candidate_budget):
        order=spec.topology_orders[index%len(spec.topology_orders)]
        record=dict(candidate=index+1,topology_index=index%len(spec.topology_orders),order=list(order),
                    method=spec.layout_version,adjustable_geometry='distributed_straight_lengths')
        journal.append(record)
        try:
            core=[];directions=[];fixed_length=0.
            for i in order:
                request=spec.inventory[i];maneuver=request.build()
                if abs(maneuver.segments[0].k_start)>1e-10 or abs(maneuver.segments[-1].k_end)>1e-10:
                    raise GeometryError('Distributed straight layout requires zero-curvature primary endpoints')
                core.append(AssemblyItem(maneuver,'primary',request.name,i))
                if request.straight_after_m:
                    core.append(AssemblyItem(straight(request.straight_after_m),'primary',request.name+'_straight',i))
                end=end_state(core)
                directions.append((math.cos(end.heading),math.sin(end.heading)))
            end=end_state(core)
            if abs(end.heading-math.tau)>1e-8:
                raise GeometryError('Fixed primary turns must sum to +360 degrees; no heading correction is allowed')
            fixed_length=sum(i.maneuver.length_m for i in core)
            remaining=spec.target_lap_length_m-fixed_length
            n=len(order)
            if not n*lo<=remaining<=n*hi:
                raise GeometryError('Target lap length outside the total designated connector length bounds')
            matrix=np.vstack([np.array(directions).T,np.ones(n)])
            rhs=np.array([-end.x,-end.y,remaining])
            target=np.array([remaining/n*rng.uniform(.35,1.65) for _ in order])
            record['target_connector_lengths_m']=target.tolist()
            lengths,optimization=bounded_projection(matrix,rhs,target,lo,hi,spec.optimization_iterations)
            items=[]
            for i,length in zip(order,lengths):
                request=spec.inventory[i]
                items.append(AssemblyItem(request.build(),'primary',request.name,i))
                if request.straight_after_m:
                    items.append(AssemblyItem(straight(request.straight_after_m),'primary',request.name+'_straight',i))
                items.append(connector(straight(float(length)),'distributed_gap',adjustable=True))
            final=end_state(items)
            record.update(status='candidate',optimization=optimization,connector_lengths_m=lengths.tolist(),
                          position_residual_m=math.hypot(final.x,final.y),heading_residual_rad=abs(final.heading-math.tau))
            yield LayoutCandidate(tuple(items),Frame(),dict(record))
        except (GeometryError,np.linalg.LinAlgError) as exc:
            record.update(status='rejected',reason=str(exc))
            if hasattr(exc,'optimization'):
                record['optimization']=exc.optimization
