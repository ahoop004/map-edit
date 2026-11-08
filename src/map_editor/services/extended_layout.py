"""Deterministic bounded nonlinear closure of designated supporting motion only."""
from dataclasses import dataclass
import math
import random
import numpy as np
from map_editor.geometry import Frame,GeometryError,straight,sweeper
from map_editor.services.composite_assembly import AssemblyItem,connector


@dataclass(frozen=True)
class ExtendedCandidate:
    items: tuple
    frame: Frame
    solution: dict


def _heading_projection(desired,lower,upper,total):
    if total<sum(lower)-1e-10 or total>sum(upper)+1e-10:
        raise GeometryError('Primary heading deficit cannot be met by the designated supporting angle bounds')
    lo=float(np.min(lower-desired))-1.;hi=float(np.max(upper-desired))+1.
    for _ in range(80):
        mid=(lo+hi)/2
        if np.clip(desired+mid,lower,upper).sum()<total:lo=mid
        else:hi=mid
    return np.clip(desired+(lo+hi)/2,lower,upper)


def supporting_curve(slot,angle):
    return sweeper(slot.radius_m,abs(float(angle)),'left' if angle>0 else 'right',slot.transition_m,slot.transition_m)


class MotionModel:
    """Cache fixed local SE(2) motions; only supporting turns need quadrature."""
    def __init__(self,spec,topology):
        self.spec=spec;self.topology=topology
        self.slots={s.after_index:(j,s) for j,s in enumerate(topology.turns)}
        self.primary={}
        for i in topology.order:
            request=spec.inventory[i];m=request.build()
            if abs(m.segments[0].k_start)>1e-10 or abs(m.segments[-1].k_end)>1e-10:
                raise GeometryError('Extended primary endpoints must have zero curvature; fixed ramps belong in the request')
            end=m.at(m.length_m)
            self.primary[i]=(m,end.x,end.y,end.heading)
        self.fixed_length=sum(self.primary[i][0].length_m+spec.inventory[i].straight_after_m for i in topology.order)
        self.fixed_heading=sum(self.primary[i][3] for i in topology.order)
        self.turn_cache={}

    def turn_motion(self,k,slot,angle):
        key=(k,float(angle))
        if key not in self.turn_cache:
            curve=supporting_curve(slot,angle)
            self.turn_cache[key]=(curve,curve.at(curve.length_m))
        return self.turn_cache[key]

    def evaluate(self,variables):
        n=len(self.topology.order);lengths=variables[:n];angles=variables[n:]
        x=y=heading=0.;length=self.fixed_length
        for j,i in enumerate(self.topology.order):
            m,dx,dy,turn=self.primary[i]
            c,s=math.cos(heading),math.sin(heading)
            x+=c*dx-s*dy;y+=s*dx+c*dy;heading+=turn
            fixed=self.spec.inventory[i].straight_after_m
            x+=fixed*math.cos(heading);y+=fixed*math.sin(heading)
            if i in self.slots:
                k,slot=self.slots[i];curve,end=self.turn_motion(k,slot,angles[k])
                c,s=math.cos(heading),math.sin(heading)
                x+=c*end.x-s*end.y;y+=s*end.x+c*end.y;heading+=end.heading;length+=curve.length_m
            x+=lengths[j]*math.cos(heading);y+=lengths[j]*math.sin(heading);length+=lengths[j]
        return np.array([x,y,10*(heading-math.tau),length-self.spec.target_lap_length_m])

    def assemble(self,variables):
        n=len(self.topology.order);items=[]
        for j,i in enumerate(self.topology.order):
            request=self.spec.inventory[i]
            items.append(AssemblyItem(self.primary[i][0],'primary',request.name,i))
            if request.straight_after_m:
                items.append(AssemblyItem(straight(request.straight_after_m),'primary',request.name+'_straight',i))
            if i in self.slots:
                k,slot=self.slots[i]
                items.append(connector(supporting_curve(slot,variables[n+k]),'supporting_turn',adjustable=True))
            items.append(connector(straight(float(variables[j])),'distributed_gap',adjustable=True))
        return tuple(items)


def optimize_motion(model,initial,lower,upper,budget):
    x=np.clip(np.asarray(initial),lower,upper);history=[];evaluations=0;damping=1e-5
    def evaluate(value):
        nonlocal evaluations
        evaluations+=1
        return model.evaluate(value)
    residual=evaluate(x)
    for iteration in range(budget+1):
        peak=float(max(abs(residual)))
        history.append(dict(iteration=iteration,maximum_scaled_residual=peak,
            position_residual_m=float(np.linalg.norm(residual[:2])),heading_residual_rad=float(abs(residual[2])/10),
            length_residual_m=float(abs(residual[3])),damping=damping))
        if peak<2e-9:
            return x,dict(iterations=iteration,evaluations=evaluations,history=history,
                maximum_scaled_residual=peak,converged=True)
        if iteration==budget:break
        jacobian=np.empty((4,len(x)))
        for j in range(len(x)):
            step=1e-5 if j>=len(model.topology.order) else 1e-4
            probe=x.copy();probe[j]+=step
            jacobian[:,j]=(evaluate(probe)-residual)/step
        accepted=False
        for _ in range(8):
            free=np.ones(len(x),dtype=bool)
            # A clamped angle must not keep absorbing the linearized correction
            # while its actual step is discarded. Re-solve on the free columns.
            for _active_pass in range(len(x)+1):
                reduced=jacobian[:,free];delta=np.zeros(len(x))
                delta[free]=-reduced.T@np.linalg.solve(reduced@reduced.T+damping*np.eye(4),residual)
                outward=((x<=lower+1e-10)&(delta<0))|((x>=upper-1e-10)&(delta>0))
                if not np.any(outward&free):break
                free&=~outward
            for scale in (1.,.5,.25,.125):
                candidate=np.clip(x+scale*delta,lower,upper)
                trial=evaluate(candidate)
                if trial@trial<residual@residual*(1-1e-12):
                    x,residual=candidate,trial;accepted=True;break
            if accepted:
                damping=max(1e-12,damping/3);break
            damping*=10
        if not accepted:break
    error=GeometryError(f'Bounded joint closure did not converge within {budget} iterations: position={np.linalg.norm(residual[:2]):.6g} m, heading={abs(residual[2])/10:.6g} rad, length={abs(residual[3]):.6g} m')
    error.optimization=dict(iterations=iteration,evaluations=evaluations,history=history,converged=False)
    raise error


def extended_candidates(spec,journal):
    rng=random.Random(spec.seed)
    for index in range(spec.candidate_budget):
        topology=spec.topologies[index%len(spec.topologies)]
        record=dict(candidate=index+1,topology=topology.name,order=list(topology.order),
            method=spec.layout_version,status='proposal',adjustable_geometry=['supporting_angles','supporting_straight_lengths'])
        journal.append(record)
        try:
            model=MotionModel(spec,topology);n=len(topology.order)
            angle_lower=np.radians([s.angle_bounds_deg[0] for s in topology.turns])
            angle_upper=np.radians([s.angle_bounds_deg[1] for s in topology.turns])
            if not len(angle_lower):
                if abs(model.fixed_heading-math.tau)>1e-9:raise GeometryError('No designated supporting turns can correct the primary heading deficit')
                angles=np.array([])
            else:
                desired=np.array([rng.uniform(lo,hi) for lo,hi in zip(angle_lower,angle_upper)])
                angles=_heading_projection(desired,angle_lower,angle_upper,math.tau-model.fixed_heading)
            supporting_length=sum(supporting_curve(slot,angle).length_m for slot,angle in zip(topology.turns,angles))
            remaining=spec.target_lap_length_m-model.fixed_length-supporting_length
            lo,hi=spec.connector_length_bounds_m
            target=np.array([remaining/n*rng.uniform(.55,1.45) for _ in range(n)])
            lower=np.r_[np.full(n,lo),angle_lower];upper=np.r_[np.full(n,hi),angle_upper]
            initial=np.r_[np.clip(target,lo,hi),angles]
            record.update(fixed_primary_heading_rad=model.fixed_heading,initial_connector_lengths_m=initial[:n].tolist(),
                initial_supporting_angles_deg=np.degrees(angles).tolist(),supporting_angle_bounds_deg=[list(s.angle_bounds_deg) for s in topology.turns])
            solution,optimization=optimize_motion(model,initial,lower,upper,spec.optimization_iterations)
            record.update(status='candidate',optimization=optimization,connector_lengths_m=solution[:n].tolist(),
                supporting_angles_deg=np.degrees(solution[n:]).tolist(),
                closure_residual_scaled=model.evaluate(solution).tolist())
            yield ExtendedCandidate(model.assemble(solution),Frame(),dict(record))
        except (GeometryError,np.linalg.LinAlgError) as exc:
            record.update(status='rejected',failure_stage='closure',reason=str(exc))
            if hasattr(exc,'optimization'):record['optimization']=exc.optimization
