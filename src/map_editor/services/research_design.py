"""Deterministic candidate parameters from preassigned scaffold/split/scale slots."""
from dataclasses import replace
import math
import random
from map_editor.geometry import Maneuver
from map_editor.geometry.maneuvers import _opposing
from map_editor.geometry.width_profile import WidthProfile
from .extended_spec import LayoutTopology,SupportingTurn
from .research_spec import ResearchSpec,ResearchFeature
from .dataset_spec import SCALES,candidate_seed


def _opposing_feature(name,family,radius,angle,ramp,direction,separation=0.,ratio=1.15):
    if family=='s_curve':p=dict(radii_m=[radius,radius*ratio],turn_angle_rad=angle,transition_length_m=ramp,direction=direction)
    else:
        curve=Maneuver('chicane','left_right',_opposing(radius,radius,angle,ramp,separation),{})
        p=dict(radius_m=radius,lateral_displacement_m=curve.at(curve.length_m).y,separation_m=separation,transition_length_m=ramp,direction=direction)
    return ResearchFeature(name,family,p)


def _width(rng):
    base=rng.uniform(1.45,1.85)
    if rng.random()<.45:return WidthProfile.constant(base,rng.uniform(.46,.54))
    a,b=rng.uniform(.9,1.1),rng.uniform(.88,1.1)
    return WidthProfile(((0.,base*.5),(.3,base*.5*a),(.65,base*.5*b),(1.,base*.5)),
        ((0.,base*.5),(.25,base*.5*b),(.7,base*.5*a),(1.,base*.5)))


def _five_family(dataset,slot,attempt,vehicle,target,width,seed,rng,design):
    gap=rng.uniform(.3,.65);ramp=.5
    angle=design.uniform(.75,.95)
    h=max(2.,target*design.uniform(.11,.16)/math.tau)
    sw=max(5.5,target*design.uniform(.10,.16)/(4*angle))
    cr=max(1.8,target*design.uniform(.09,.13)/(4*.8))
    sr=max(1.8,target*design.uniform(.10,.15)/(4*.9))
    ch=_opposing_feature('chicane','chicane',cr,.8,ramp,'left_right',.4)
    sc=_opposing_feature('s_curve','s_curve',sr,.9,ramp,'left_right',ratio=design.uniform(1.,1.2))
    others=[ch,sc,ResearchFeature('sweeper_left','sweeper',dict(radius_m=sw,turn_angle_rad=angle,entry_transition_m=ramp,exit_transition_m=ramp)),
        ResearchFeature('sweeper_right','sweeper',dict(radius_m=sw*design.uniform(.9,1.1),turn_angle_rad=angle,direction='right',entry_transition_m=ramp,exit_transition_m=ramp)),
        ResearchFeature('hairpin','hairpin',dict(radius_m=h,turn_angle_rad=math.pi,entry_transition_m=ramp,exit_transition_m=ramp))]
    fixed=sum(r.build().length_m for r in others)+6*gap
    length=target/2-fixed
    if length<target*.025:raise ValueError('Five-family source budget leaves insufficient requested straight length')
    inventory=(ResearchFeature('straight','straight',dict(length_m=length)),*others)
    return ResearchSpec(inventory,vehicle,(LayoutTopology('controlled_five_family_motif',tuple(range(6)),()),),
        target,SCALES[slot.scale],slot.split,slot.slot_id,slot.parent_lineage,'controlled_halfturn_five',
        expected_primary_families=5,width=width,seed=seed,attempt=attempt,dataset_id=dataset.dataset_id,
        assembly_method='controlled_halfturn.v1',support_gap_m=gap,candidate_budget=1)


def _candidate_spec(dataset,slot,attempt,vehicle):
    design=random.Random(slot.design_seed);seed=candidate_seed(dataset,slot,attempt);rng=random.Random(seed)
    low,high=SCALES[slot.scale]
    target=rng.uniform(low+7,high-7)
    # Physical targets span each design range; no source scale/radius fitting
    # occurs after these exact primary parameters have been requested.
    width=_width(rng);ramp=rng.uniform(.65,.95)
    if slot.generation_mode=='specialist':
        family=slot.family
        if family=='hairpin':n=2
        else:n=design.choice((4,5,6))
        ratio=[design.uniform(.8,1.2) for _ in range(n)]
        inventory=[]
        if family=='straight':
            coverage=rng.uniform(.72,.81)
            lengths=[coverage*target*x/sum(ratio) for x in ratio]
            inventory=[ResearchFeature(f'straight_{i+1}','straight',dict(length_m=x)) for i,x in enumerate(lengths)]
            support_radius=rng.uniform(1.8,2.8) if slot.scale=='short' else rng.uniform(3.,6.)
            turns=tuple(SupportingTurn(i,(math.degrees(math.tau/n)*.65,math.degrees(math.tau/n)*1.35),support_radius,.65) for i in range(n))
            minimum=.70
        elif family=='hairpin':
            angles=[math.radians(design.uniform(151,166)),math.radians(design.uniform(151,166))]
            coverage=rng.uniform(.74,.83)
            ratios=[1.,design.uniform(.94,1.06)]
            base=(coverage*target-n*ramp)/sum(a*r for a,r in zip(angles,ratios))
            inventory=[ResearchFeature(f'hairpin_{i+1}','hairpin',dict(radius_m=base*ratios[i],turn_angle_rad=a,
                entry_transition_m=ramp,exit_transition_m=ramp)) for i,a in enumerate(angles)]
            deficit=360-sum(math.degrees(a) for a in angles)
            turns=tuple(SupportingTurn(i,(12.,deficit-12.),rng.uniform(3.2,4.),.55) for i in range(n))
            minimum=.70
        elif family=='sweeper':
            raw=[design.uniform(.75,1.25) for _ in range(n)];total=math.radians(300.)
            angles=[total*a/sum(raw) for a in raw];coverage=rng.uniform(.82,.90)
            base=(coverage*target-n*ramp)/sum(a*r for a,r in zip(angles,ratio))
            inventory=[ResearchFeature(f'sweeper_{i+1}','sweeper',dict(radius_m=base*ratio[i],turn_angle_rad=a,
                entry_transition_m=ramp,exit_transition_m=ramp)) for i,a in enumerate(angles)]
            turns=(SupportingTurn(0,(15.,45.),rng.uniform(2.5,4.),.65),SupportingTurn(n//2,(15.,45.),rng.uniform(2.5,4.),.65))
            minimum=.80
        else:
            angles=[design.uniform(.65,1.1) for _ in range(n)];coverage=rng.uniform(.70,.82)
            ratios=ratio
            separation=target/n*rng.uniform(.015,.06) if family=='chicane' else 0.
            factor=2. if family=='chicane' else 2.15
            base=(coverage*target-n*(2*ramp+separation))/sum(factor*a*r for a,r in zip(angles,ratios))
            for i,angle in enumerate(angles):
                inventory.append(_opposing_feature(f'{family}_{i+1}',family,base*ratios[i],angle,ramp,
                    'left_right' if design.random()<.5 else 'right_left',separation))
            sr=rng.uniform(1.9,2.7) if slot.scale=='short' else rng.uniform(3.,5.)
            turns=tuple(SupportingTurn(i,(math.degrees(math.tau/n)*.7,math.degrees(math.tau/n)*1.3),sr,.65) for i in range(n))
            minimum=.60 if family=='chicane' else .65
        order=tuple(range(n));reverse=(0,*reversed(range(1,n)))
        topologies=(LayoutTopology('unequal_maneuver_ring',order,turns),LayoutTopology('reordered_maneuver_ring',reverse,turns))
        return ResearchSpec(tuple(inventory),vehicle,topologies,target,(low,high),slot.split,slot.slot_id,slot.parent_lineage,
            f'{family}_{n}_unequal_ring',generation_mode='specialist',target_family=family,minimum_target_exposure=minimum,
            expected_primary_families=1,candidate_budget=3,maximum_supporting_fraction=1-minimum,minimum_primary_coverage=minimum,
            connector_length_bounds_m=(.3,target*.35),width=width,seed=seed,attempt=attempt,dataset_id=dataset.dataset_id)
    # Composite families are literal independently validated primary annotation
    # types, including the new honest corner vocabulary. Supporting types do not
    # inflate the count.
    complexity=slot.complexity
    if complexity==5:return _five_family(dataset,slot,attempt,vehicle,target,width,seed,rng,design)
    choices={2:[('straight','corner'),('straight','hairpin'),('corner','s_curve')],
        3:[('straight','corner','s_curve'),('straight','corner','sweeper'),('corner','chicane','s_curve')],
        4:[('straight','corner','chicane','s_curve')],
        5:[('straight','hairpin','sweeper','chicane','s_curve')]}
    families=design.choice(choices[complexity]);has_hairpin='hairpin' in families
    if has_hairpin:
        angles=[math.radians(155.),math.radians(55.),math.radians(60.)]
        core_types=['hairpin','sweeper' if 'sweeper' in families else 'hairpin','sweeper' if 'sweeper' in families else 'hairpin']
        if 'sweeper' not in families:
            angles=[math.radians(design.uniform(151,163)),math.radians(design.uniform(151,163))];core_types=['hairpin']*2
    else:
        n=design.choice((4,5,6));weights=[design.uniform(.85,1.2) for _ in range(n)]
        angles=[math.radians(280.)*w/sum(weights) for w in weights];core_types=['sweeper' if 'sweeper' in families and i%2 else 'corner' for i in range(n)]
    n=len(angles);inventory=[];support_slots=[]
    opposing=[f for f in families if f in ('chicane','s_curve')]
    fixed_fraction=.32 if 'straight' in families else 0.
    feature_budget=.70-fixed_fraction
    # A dominant straight quota is never manufactured by embedding long internal
    # straights in opposing maneuvers. Their exact zero-curvature separation is bounded.
    core_fraction=feature_budget-(.10*len(opposing))
    core_ratios=[design.uniform(.96,1.04) if has_hairpin else design.uniform(.8,1.2) for _ in angles]
    core_base=(target*core_fraction-n*ramp)/sum(a*r for a,r in zip(angles,core_ratios))
    for i,(angle,kind) in enumerate(zip(angles,core_types)):
        radius=max(1.6,core_base*core_ratios[i])
        if kind=='hairpin':params=dict(radius_m=radius,turn_angle_rad=angle,entry_transition_m=ramp,exit_transition_m=ramp)
        elif kind=='sweeper':params=dict(radius_m=max(5.,radius),turn_angle_rad=angle,entry_transition_m=ramp,exit_transition_m=ramp)
        else:params=dict(radius_m=radius,turn_angle_deg=math.degrees(angle),transition_m=ramp)
        fixed=target*fixed_fraction/n*design.uniform(.8,1.2) if 'straight' in families else 0.
        inventory.append(ResearchFeature(f'core_{i+1}',kind,params))
        support_slots.append(len(inventory)-1)
        for f in opposing:
            if i%2==0:
                count=(n+1)//2;length=target*.1/count;theta=design.uniform(.65,1.)
                sep=length*.03 if f=='chicane' else 0.
                factor=2 if f=='chicane' else 2.15
                rad=max(1.6,(length-2*ramp-sep)/(factor*theta))
                inventory.append(_opposing_feature(f'{f}_{i+1}',f,rad,theta,ramp,
                    'left_right' if design.random()<.5 else 'right_left',sep))
        if fixed:
            inventory.append(ResearchFeature(f'primary_straight_{i+1}','straight',dict(length_m=fixed)))
    deficit=360-sum(math.degrees(a) for a in angles)
    lo=max(12.,deficit/n*.55);hi=deficit-(n-1)*lo
    # A fixed positive radius and zero-curvature ramps bound every connector.
    sr=3.2 if slot.scale=='short' else rng.uniform(3.2,5.)
    turn_slots=tuple(SupportingTurn(i,(lo,hi),sr,.5) for i in support_slots)
    order=tuple(range(len(inventory)));alt=(0,*reversed(range(1,len(inventory))))
    topologies=(LayoutTopology('mixed_feature_ring',order,turn_slots),LayoutTopology('reordered_feature_ring',alt,turn_slots))
    return ResearchSpec(tuple(inventory),vehicle,topologies,target,(low,high),slot.split,slot.slot_id,slot.parent_lineage,
        f'mixed_{complexity}_{len(inventory)}_ring',expected_primary_families=complexity,
        width=width,candidate_budget=3,connector_length_bounds_m=(.3,target*.3),seed=seed,attempt=attempt,dataset_id=dataset.dataset_id)


def candidate_spec(dataset,slot,attempt,vehicle):
    from map_editor.geometry.validation import GeometryLimits
    spec=_candidate_spec(dataset,slot,attempt,vehicle)
    policy=dataset.objective_ranges
    minimum=dataset.specialist_exposure[slot.family] if slot.family else spec.minimum_target_exposure
    return replace(spec,minimum_target_exposure=minimum,
        minimum_primary_coverage=max(policy['minimum_primary_coverage'],minimum if slot.family else 0.),
        maximum_supporting_fraction=min(policy['maximum_supporting_fraction'],1-minimum if slot.family else 1.),
        minimum_family_exposure=policy['minimum_composite_family_exposure'],maximum_family_exposure=policy['maximum_composite_family_exposure'],
        minimum_target_active_fraction=policy['minimum_target_active_fraction'],
        limits=GeometryLimits(minimum_usable_width_m=policy['minimum_usable_width_m'],maximum_curvature_rate_inv_m2=policy['maximum_curvature_rate_inv_m2']))
