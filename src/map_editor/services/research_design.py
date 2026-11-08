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
    if dataset.design_version=='research_design.v2':
        from .research_reliable_design import reliable_spec,irregular_composite_spec,IRREGULAR_VARIANTS
        profiles=IRREGULAR_VARIANTS.get((slot.scale,slot.complexity)) if slot.generation_mode=='composite' else None
        if profiles:
            variant=profiles[(slot.design_seed+attempt-1)%len(profiles)]
            spec=irregular_composite_spec(slot.scale,slot.complexity,variant,candidate_seed(dataset,slot,attempt),vehicle,attempt)
        else:
            variant=(slot.design_seed+attempt-1)%(3 if slot.family=='hairpin' else 4)
            spec=reliable_spec(slot.family or 'composite',slot.scale,variant,
                candidate_seed(dataset,slot,attempt),vehicle,complexity=slot.complexity)
        spec=replace(spec,seed=candidate_seed(dataset,slot,attempt),attempt=attempt,
            split=slot.split,slot_id=slot.slot_id,parent_lineage=slot.parent_lineage,
            dataset_id=dataset.dataset_id)
        # One validated proposal per candidate seed. Repeating the same fixed
        # heading solve with three initializations rarely changes its failure.
        spec=replace(spec,candidate_budget=1)
    else:spec=_candidate_spec(dataset,slot,attempt,vehicle)
    policy=dataset.objective_ranges
    minimum=dataset.specialist_exposure[slot.family] if slot.family else spec.minimum_target_exposure
    # V2 retains Phase 5.1 specialist dominance independently of the stricter
    # composite coverage contract. V1's original global policy is unchanged.
    specialist_v2=dataset.design_version=='research_design.v2' and slot.family is not None
    return replace(spec,minimum_target_exposure=minimum,
        minimum_primary_coverage=minimum if specialist_v2 else max(policy['minimum_primary_coverage'],minimum if slot.family else 0.,.6 if dataset.design_version=='research_design.v2' else 0.),
        maximum_supporting_fraction=1-minimum if specialist_v2 else min(policy['maximum_supporting_fraction'],1-minimum if slot.family else 1.,.4 if dataset.design_version=='research_design.v2' else 1.),
        minimum_family_exposure=policy['minimum_composite_family_exposure'],maximum_family_exposure=policy['maximum_composite_family_exposure'],
        minimum_target_active_fraction=policy['minimum_target_active_fraction'],
        limits=GeometryLimits(minimum_usable_width_m=policy['minimum_usable_width_m'],maximum_curvature_rate_inv_m2=policy['maximum_curvature_rate_inv_m2']))


def experimental_spec(family,scale,variant,seed,vehicle,attempt=1):
    """Opt-in Phase 5.1 tuning; fully resolved native recipes keep v1 replay.

    Radii never depend on target lap length. Counts and supporting gaps provide
    scale; the frozen formal dataset design above deliberately stays unchanged.
    """
    rng=random.Random(seed+1009*(attempt-1));ramp=.65
    inventory=[];turns=[]
    def bend(kind,angle,radius):
        inventory.append(ResearchFeature(f'{kind}_{len(inventory)+1}',kind,
            dict(radius_m=radius,turn_angle_rad=math.radians(abs(angle)),
                 direction='left' if angle>0 else 'right',
                 entry_transition_m=ramp,exit_transition_m=ramp)))
    def opposing(kind):
        radius=rng.uniform(2.8,4.) if kind=='chicane' else rng.uniform(4.5,6.5)
        angle=rng.uniform(.8,1.05) if kind=='chicane' else rng.uniform(.95,1.35)
        inventory.append(_opposing_feature(f'{kind}_{len(inventory)+1}',kind,radius,angle,ramp,
            rng.choice(('left_right','right_left')),.25 if kind=='chicane' else 0.,rng.uniform(1.02,1.18)))
    if family=='hairpin':
        n={'short':5,'medium':9,'long':15}[scale]
        target={'short':138.,'medium':210.,'long':340.}[scale]
        # A folded lane sequence, with two outer supporting bends. Alternating
        # signs create real U-turn practice instead of two enlarged oval ends.
        angle=180.
        for i in range(n):bend('hairpin',angle if i%2==0 else -angle,
            rng.uniform(5.8,6.) if i in (0,n-1) else rng.uniform(5.3,5.6) if i==2 else rng.uniform(3.,3.7))
        turns=[SupportingTurn(1,(90.,90.),2.3,ramp),SupportingTurn(n-1,(90.,90.),8.,ramp)]
        minimum=.50
    elif family=='sweeper':
        angles=[110,-60,100,85,85]
        target=170. if scale=='medium' else 265.
        for angle in angles:bend('sweeper',angle,rng.uniform(10.,14.5))
        if scale=='long':
            for _ in range(2):
                # Opposing sustained bends add practice without adding a net
                # revolution or enlarging the original bend radii.
                bend('sweeper',-55,rng.uniform(10.,14.5));bend('sweeper',55,rng.uniform(10.,14.5))
        deficit=360-sum(angles)
        turns=[SupportingTurn(i,(deficit/2-6,deficit/2+6),3.2,ramp) for i in (0,len(inventory)-1)]
        minimum=.50
    elif family in ('chicane','s_curve'):
        n=8;target=110. if family=='chicane' else 165.
        for _ in range(n):opposing(family)
        turns=[SupportingTurn(i,(28.,65.),rng.uniform(2.4,3.2),ramp) for i in range(n)]
        minimum=.50
    elif family=='composite':
        target=(145.,245.,270.)[variant]
        # Unequal headings, concave corners and mixed ordering, without rotated
        # blocks. Each tuple is an independently requested primary maneuver.
        cores=[ [('corner',85),('sweeper',105),('corner',-70),('corner',115),('corner',125)],
                [('corner',85),('hairpin',170),('corner',-65),('corner',95),('corner',75)],
                [('hairpin',170),('sweeper',100),('sweeper',90),('sweeper',80),('sweeper',-80)] ][variant]
        for i,(kind,angle) in enumerate(cores):
            if kind=='corner':
                inventory.append(ResearchFeature(f'corner_{i}','corner',dict(radius_m=rng.uniform(2.3,3.8),
                    turn_angle_deg=abs(angle),direction='left' if angle>0 else 'right',transition_m=ramp)))
            else:bend(kind,angle,rng.uniform(3.,5.) if kind=='hairpin' else rng.uniform(7.,12.))
            if (i+variant)%2==0:opposing('s_curve' if variant==1 or i%2 else 'chicane')
            if i in (1,4):
                inventory.append(ResearchFeature(f'straight_{i}','straight',
                    dict(length_m=rng.uniform(*( (8.,18.) if variant==0 else (14.,28.) )))))
        if variant==2:opposing('s_curve')
        minimum=.40
    else:raise ValueError('Unsupported experimental pilot family')
    count=len(inventory);order=tuple(range(count))
    # The folded switchback ordering is intentional; random reorderings destroy
    # its lane progression. The mixed inventories already vary ordering.
    topologies=(LayoutTopology('phase5_1_'+family,order,tuple(turns)),)
    return ResearchSpec(tuple(inventory),vehicle,topologies,target,SCALES[scale],
        'train',f'phase5_1_{family}_{variant+1:02d}',f'phase5_1_{family}_{variant}_{seed}',
        'experimental_'+family,generation_mode='composite' if family=='composite' else 'specialist',
        target_family=None if family=='composite' else family,minimum_target_exposure=minimum,
        expected_primary_families=len({r.family for r in inventory}),minimum_primary_coverage=minimum,
        maximum_supporting_fraction=1-minimum,maximum_family_exposure=.85,
        connector_length_bounds_m=(1.2,target*.45),candidate_budget=3,
        width=WidthProfile.constant(1.5),seed=seed+1009*(attempt-1),attempt=attempt,dataset_id='phase5_1_pilot')


def refined_spec(family,scale,variant,seed,vehicle,attempt=1,*,complexity=None):
    """Explicit V2 physical-scale designs; bounded closure and V1 replay unchanged.

    Counts, fixed useful features and solver gaps supply lap length. Full resolved
    parameters, topology and design version are included in native recipe identity.
    """
    rng=random.Random(seed+1009*(attempt-1));ramp=.65
    inventory=[];turns=[]
    target={'short':132.,'medium':210.,'long':330.}[scale]
    def bend(kind,angle,radius,end_radius=None):
        p=dict(radius_m=radius,turn_angle_rad=math.radians(abs(angle)),
            direction='left' if angle>0 else 'right',entry_transition_m=ramp,exit_transition_m=ramp)
        if end_radius is not None:p['end_radius_m']=end_radius
        inventory.append(ResearchFeature(f'{kind}_{len(inventory)+1}',kind,p))
    def opposing(kind):
        radius=rng.uniform(2.8,3.7) if kind=='chicane' else rng.uniform(4.,6.2)
        angle=rng.uniform(.78,.92) if kind=='chicane' else rng.uniform(.85,1.35)
        inventory.append(_opposing_feature(f'{kind}_{len(inventory)+1}',kind,radius,angle,ramp,
            rng.choice(('left_right','right_left')),.25 if kind=='chicane' else 0.,rng.uniform(1.02,1.15)))
    def primary_straight(length):
        inventory.append(ResearchFeature(f'straight_{len(inventory)+1}','straight',dict(length_m=length)))
    if family=='hairpin':
        if variant==0:
            n={'short':5,'medium':9,'long':15}[scale]
            if scale=='short':target=138.
            for i in range(n):
                radius=rng.uniform(5.8,6.) if i in (0,n-1) else rng.uniform(5.3,5.6) if i==2 else rng.uniform(3.,3.7)
                bend('hairpin',180 if i%2==0 else -180,radius)
            turns=[SupportingTurn(1,(90.,90.),2.3,ramp),SupportingTurn(n-1,(90.,90.),8.,ramp)]
            topology='unequal_folded_lanes'
        else:
            # Outward-facing pairs are grouped around three or four existing
            # supporting bends. These replace the self-crossing two-bank and
            # inward orthogonal-cluster proposals retained in pilot evidence.
            clusters=4 if variant==1 else 3
            per_cluster=2 if scale!='long' else 4
            radius_range=(3.9,4.8) if scale!='long' else (4.3,5.4)
            for cluster in range(clusters):
                for i in range(per_cluster):
                    bend('hairpin',-180 if i%2==0 else 180,rng.uniform(*radius_range))
                turns.append(SupportingTurn(len(inventory)-1,(360/clusters,360/clusters),3.2,ramp))
            topology='four_outward_switchback_clusters' if variant==1 else 'three_outward_switchback_clusters'
    elif family=='sweeper':
        # Signed orders are intentionally concave, never a regular positive ring.
        angles=([110,-60,100,85,85] if variant%2==0 else [80,115,-70,120,115])
        if scale=='short':angles=[95,-45,110,100,100]
        if scale=='long':angles=angles+([-65,65] if variant%2==0 else [-50,75,-70,45])
        for i,angle in enumerate(angles):
            radius=rng.uniform(8.,14.5) if i%3 else rng.uniform(6.5,9.)
            bend('sweeper',angle,radius,rng.uniform(7.,14.5) if i%2 else None)
        target={'short':138.,'medium':170.,'long':285.}[scale]
        # Add unequal opposing sustained bends until useful content covers scale.
        while sum(r.build().length_m for r in inventory)<target*.57:
            angle=rng.uniform(48.,72.)
            bend('sweeper',-angle,rng.uniform(9.,14.5),rng.uniform(7.,13.))
            bend('sweeper',angle,rng.uniform(8.,13.),rng.uniform(7.,14.5))
        deficit=360-sum(angles)
        if deficit:
            turns=[SupportingTurn(i,(deficit/2-5,deficit/2+5),3.2,ramp) for i in (0,len(inventory)-1)]
        topology='concave_sustained_sweepers' if variant%2==0 else 'variable_radius_sweeper_chain'
    elif family in ('chicane','s_curve'):
        n={'short':8,'medium':10,'long':18}[scale]
        if family=='chicane' and scale=='short':target=110.
        if family=='s_curve' and scale=='medium':target=165.
        for _ in range(n):opposing(family)
        turns=[SupportingTurn(i,(max(16.,360/n*.65),360/n*1.4),rng.uniform(2.4,3.2),ramp) for i in range(n)]
        topology='unequal_opposing_maneuver_ring'
    elif family=='straight':
        n={'short':4,'medium':5,'long':6}[scale]
        lengths=[rng.uniform(.8,1.2) for _ in range(n)]
        for length in lengths:primary_straight(target*.74*length/sum(lengths))
        turns=[SupportingTurn(i,(360/n*.75,360/n*1.25),2.4,ramp) for i in range(n)]
        topology='long_runs_compact_connectors'
    elif family=='composite':
        complexity=complexity or (5,4,5)[variant]
        target=({'short':138.,'medium':(170.,210.,245.)[variant],'long':330.})[scale]
        cores=([('corner',85),('sweeper',105),('corner',-70),('corner',115),('corner',125)] if variant==0 else
               [('corner',85),('hairpin',170),('corner',-65),('corner',95),('corner',75)] if variant==1 else
               [('hairpin',170),('sweeper',100),('sweeper',90),('sweeper',80),('sweeper',-80)])
        # Lower-complexity slots retain genuinely different primary families.
        if complexity in (2,3):
            cores=[('sweeper' if complexity==3 and i==1 else 'corner',a)
                for i,a in enumerate((85,105,-70,115,125))]
        for i,(kind,angle) in enumerate(cores):
            if kind=='corner':
                inventory.append(ResearchFeature(f'corner_{len(inventory)+1}','corner',dict(radius_m=rng.uniform(2.5,3.8),
                    turn_angle_deg=abs(angle),direction='left' if angle>0 else 'right',transition_m=ramp)))
            else:bend(kind,angle,rng.uniform(3.5,5.) if kind=='hairpin' else rng.uniform(7.,12.))
            if complexity>=4 and i in (0,2,4):opposing('s_curve' if variant==1 else 'chicane')
            if complexity==5 and i in (1,3):opposing('s_curve' if variant!=1 else 'chicane')
            if variant==1 and complexity>=4 and i in (0,3):opposing('s_curve')
            if variant==2 and complexity==5 and i in (0,2):opposing('s_curve')
            if i in (1,4):primary_straight(rng.uniform(8.,16.) if scale=='short' else rng.uniform(14.,25.))
        # Scale with additional useful zero-net-heading maneuvers, never radii.
        if scale=='long':
            for kind in (('s_curve','chicane') if complexity==5 else ('s_curve',) if variant==1 and complexity>=4 else ('chicane',) if complexity>=4 else ()):
                opposing(kind)
        if complexity in (2,3):
            # Same physical corner vocabulary at every scale; repetitions add
            # content to longer slots without turning technical corners into ovals.
            while sum(r.build().length_m for r in inventory)<target*.64:
                angle=rng.uniform(55.,100.);radius=rng.uniform(2.8,3.8)
                for direction in ('left','right'):
                    inventory.append(ResearchFeature(f'corner_{len(inventory)+1}','corner',
                        dict(radius_m=radius,turn_angle_deg=angle,direction=direction,transition_m=ramp)))
        topology=('technical_flow_mix','hairpin_opposing_mix','five_family_irregular_chain')[variant] if complexity>=4 else 'technical_flow_mix'
    else:raise ValueError('Unsupported V2 family')
    minimum=.6 if family=='composite' else .5
    return ResearchSpec(tuple(inventory),vehicle,(LayoutTopology(topology,tuple(range(len(inventory))),tuple(turns)),),
        target,SCALES[scale],'train',f'phase5_2_{family}_{variant+1:02d}',f'research_design.v2:{family}:{scale}:{variant}:{seed}',
        topology,generation_mode='composite' if family=='composite' else 'specialist',
        target_family=None if family=='composite' else family,minimum_target_exposure=minimum,
        expected_primary_families=len({r.family for r in inventory}),minimum_primary_coverage=minimum,
        maximum_supporting_fraction=1-minimum,maximum_family_exposure=.78,
        connector_length_bounds_m=(1.2,target*.4),candidate_budget=3,
        width=WidthProfile.constant(1.5),seed=seed+1009*(attempt-1),attempt=attempt,
        dataset_id='phase5_2_pilot',design_version='research_design.v2')


def corrected_spec(family,scale,variant,seed,vehicle,attempt=1,*,complexity=None):
    """Phase 5.2B corrections; saved V2 recipes and the tuning factory stay intact.

    The two rejected hairpin cluster strategies are never selected here. Counts,
    connector budgets and supporting radii vary within the proven folded lanes.
    """
    if family=='hairpin' and variant in (1,2):
        base=experimental_spec(family,scale,variant,seed,vehicle,attempt)
        rng=random.Random(base.seed)
        count=({'short':5,'medium':7,'long':13} if variant==1 else
               {'short':5,'medium':11,'long':17})[scale]
        target=({'short':138.,'medium':180.,'long':300.} if variant==1 else
                {'short':138.,'medium':250.,'long':390.})[scale]
        inventory=[]
        for i in range(count):
            radius=rng.uniform(5.8,6.) if i in (0,count-1) else rng.uniform(5.3,5.6) if i==2 else rng.uniform(3.,3.7)
            inventory.append(ResearchFeature(f'hairpin_{i+1}','hairpin',dict(radius_m=radius,
                turn_angle_rad=math.pi,direction='left' if i%2==0 else 'right',
                entry_transition_m=.65,exit_transition_m=.65)))
        turns=(SupportingTurn(1,(90.,90.),2.3 if variant==1 else 2.7,.65),
               SupportingTurn(count-1,(90.,90.),8. if variant==1 else 8.8,.65))
        return replace(base,inventory=tuple(inventory),target_lap_length_m=target,
            topologies=(LayoutTopology('unequal_folded_lanes',tuple(range(count)),turns),),
            topology_family='unequal_folded_lanes',connector_length_bounds_m=(1.2,target*.45),
            dataset_id='phase5_2b_pilot',design_version='research_design.v2')
    if family=='composite' and variant==0 and complexity in (None,4):
        base=experimental_spec(family,'medium',0,seed,vehicle,attempt)
        rng=random.Random(base.seed+77)
        inventory=[]
        for feature in base.inventory:
            inventory.append(feature)
            # The proven 115-degree corner has a long following gap. Insert a
            # genuine opposing bend there instead of expanding straight labels.
            if feature.name=='corner_3':
                inventory.append(_opposing_feature('extra_chicane','chicane',rng.uniform(3.,3.5),
                    .85,.65,rng.choice(('left_right','right_left')),.25))
        target={'short':138.,'medium':145.,'long':300.}[scale]
        return replace(base,inventory=tuple(inventory),target_lap_length_m=target,lap_length_range_m=SCALES[scale],
            topologies=(LayoutTopology('compact_technical_flow_mix',tuple(range(len(inventory))),()),),
            topology_family='compact_technical_flow_mix',minimum_primary_coverage=.6,
            maximum_supporting_fraction=.4,maximum_family_exposure=.78,
            dataset_id='phase5_2b_pilot',design_version='research_design.v2')
    return refined_spec(family,scale,variant,seed,vehicle,attempt,complexity=complexity)
