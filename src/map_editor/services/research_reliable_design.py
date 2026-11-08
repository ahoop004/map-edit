"""Phase 5.2C templates using existing exact half-turn and bounded-ring assembly.

No native recipe interpretation changes. Counts, severity, order and requested
straights vary; radii remain in physical maneuver ranges at every lap scale.
"""
from dataclasses import replace
import math
import random
from map_editor.geometry import GeometryError
from map_editor.geometry.width_profile import WidthProfile
from .dataset_spec import SCALES
from .extended_spec import LayoutTopology,SupportingTurn
from .research_spec import ResearchFeature,ResearchSpec
from .research_design import _opposing_feature,corrected_spec

TARGETS={'short':(90.,105.,120.,136.),'medium':(155.,185.,220.,252.),'long':(275.,320.,370.,425.)}


def reliable_spec(family,scale,variant,seed,vehicle,attempt=1,*,complexity=None):
    if family=='hairpin' or (family=='sweeper' and scale!='short'):
        return corrected_spec(family,scale,variant%3,seed,vehicle,attempt,complexity=complexity)
    variant%=4;rng=random.Random(seed+1009*(attempt-1));ramp=.65
    target=TARGETS[scale][variant];inventory=[];turns=[];gap=.45+.12*variant
    method='bounded_supporting_turns.v1';topology='severity_varied_'+family
    def feature(kind,parameters):
        inventory.append(ResearchFeature(f'{kind}_{len(inventory)+1}',kind,parameters))
    def bend(kind,angle,radius):
        feature(kind,dict(radius_m=radius,turn_angle_rad=math.radians(abs(angle)),direction='left' if angle>0 else 'right',
            entry_transition_m=ramp,exit_transition_m=ramp))
    def opposing(kind,direction='left_right',specialist=False):
        if kind=='chicane':
            radius=(2.5,3.,3.5,4.)[variant]*rng.uniform(.97,1.03)
            # Displacement stays within 1.5-4 m even at the largest radius.
            angle=(.88,.86,.82,.78)[variant]*rng.uniform(.97,1.03);separation=.25
        else:
            radius=(3.4,4.,4.8,5.8)[variant]*rng.uniform(.97,1.03)
            angle=(.82,.95,1.08,1.2)[variant]*rng.uniform(.97,1.03);separation=0.
        r=_opposing_feature(f'{kind}_{len(inventory)+1}',kind,radius,angle,ramp,direction,separation,1.08)
        inventory.append(r)
    if family=='composite':
        complexity=complexity or (2+variant)
        if complexity not in (2,3,4,5):raise GeometryError('Composite complexity must be 2..5')
        # Phase 5's controlled half-turn construction supplies exact closure.
        # Phase 5.1/5.2B folded lanes supply the alternating tight U-turn word.
        if scale=='short':target=(118.,124.,130.,138.)[variant] if complexity>=4 else target
        count=1 if scale=='short' else (3 if complexity<=3 else 1) if scale=='medium' else (5 if complexity<=3 else 3)
        # Fixed physical radii; longer laps use more turns, never enlarged ends.
        hairpin_radius=(4.7,5.,5.4,5.7)[variant] if scale=='short' else (3.4,3.8,4.2,4.6)[variant]
        opposing_kinds=[] if complexity==2 else [('chicane' if variant%2==0 else 's_curve')] if complexity==3 else ['chicane','s_curve']
        repeats={'short':1,'medium':1 if complexity==5 else 2,'long':2}[scale]
        # Place useful monotone opposing turns before the straight and folds.
        # Positive lateral shifts keep the two half-lap banks separated.
        words=[opposing_kinds,opposing_kinds[::-1],opposing_kinds[::-1],opposing_kinds]
        for repeat in range(repeats):
            for kind in words[variant]:opposing(kind)
        if complexity==5:
            angle=(45.,49.,53.,57.)[variant]
            bend('sweeper',angle,6.2+.35*variant)
            bend('sweeper',-angle,6.2+.35*variant)
        # A real requested straight, resolved before assembly. Gaps remain support.
        straight_index=len(inventory)
        feature('straight',dict(length_m=1.))
        for i in range(count):bend('hairpin',180 if i%2==0 else -180,hairpin_radius*rng.uniform(.98,1.02))
        fixed=sum(r.build().length_m for i,r in enumerate(inventory) if i!=straight_index)
        length=target/2-fixed-len(inventory)*gap
        if length<max(2.,target*.025/2):raise GeometryError('Half-turn inventory leaves insufficient meaningful requested straight')
        inventory[straight_index]=ResearchFeature(inventory[straight_index].name,'straight',dict(length_m=length))
        exposures={kind:2*sum(r.build().length_m for r in inventory if r.family==kind)/target for kind in {r.family for r in inventory}}
        if any(not .025<=v<=.78 for v in exposures.values()):raise GeometryError('Half-turn inventory violates meaningful family coverage budget')
        topology=f'controlled_halfturn_folded_{complexity}'
        method='controlled_halfturn.v1'
    elif family in ('chicane','s_curve'):
        # Start from the proven Phase 5.1 opposing ring, but fit count to actual
        # physical window length and reserve the full supporting-turn budget.
        opposing(family);length=inventory[0].build().length_m
        count=max(5,round(target*.60/length))
        if count>40:raise GeometryError('Physical opposing-ring count exceeds native bound')
        for i in range(1,count):
            direction='right_left' if (i+variant)%(2+variant%2)==0 else 'left_right'
            opposing(family,direction)
        # Shorter supporting ramps allow many small heading corrections while
        # preserving the unchanged source curvature-rate limit.
        turns=[SupportingTurn(i,(360/count,360/count),2.8+.2*variant,.4) for i in range(count)]
        minimum_support=sum(t.radius_m*math.radians(t.angle_bounds_deg[0])+t.transition_m for t in turns)+count*.3
        primary=sum(r.build().length_m for r in inventory)
        if primary/target<.5 or primary+minimum_support>target:
            raise GeometryError('Opposing ring fails fixed primary/support length budget')
        topology='count_budgeted_opposing_ring'
    elif family=='straight':
        count=4+variant
        weights=[rng.uniform(.65,1.35) for _ in range(count)]
        for w in weights:feature('straight',dict(length_m=.74*target*w/sum(weights)))
        turns=[SupportingTurn(i,(max(16.,360/count*.6),360/count*1.4),2.2+.15*variant,ramp) for i in range(count)]
        topology='unequal_straights_varied_corner_count'
    elif family=='sweeper':
        target=(118.,125.,132.,138.)[variant]
        words=([95,-45,110,100,100],[80,115,-70,120,115],[110,-60,100,85,85],[75,120,-45,100,110])
        angles=words[variant]
        for i,angle in enumerate(angles):bend('sweeper',angle,(7.5,8.2,8.9,9.6)[variant]*rng.uniform(.96,1.04))
        deficit=360-sum(angles)
        if deficit:turns=[SupportingTurn(i,(deficit/2,deficit/2),3.2,ramp) for i in (0,len(inventory)-1)]
        topology='short_sweepers_varied_signed_order'
    else:raise GeometryError('Unsupported reliability family')
    composite=family=='composite';minimum=.6 if composite else .5
    return ResearchSpec(tuple(inventory),vehicle,(LayoutTopology(topology,tuple(range(len(inventory))),tuple(turns)),),target,SCALES[scale],
        'train',f'phase5_2c_{family}_{scale}_{variant}',f'phase5_2c:{family}:{scale}:{variant}:{seed}',topology,
        generation_mode='composite' if composite else 'specialist',target_family=None if composite else family,
        minimum_target_exposure=minimum,expected_primary_families=len({r.family for r in inventory}),
        minimum_primary_coverage=minimum,maximum_supporting_fraction=1-minimum,
        connector_length_bounds_m=(.3,target*.4),candidate_budget=1,width=WidthProfile.constant(1.5),
        seed=seed+1009*(attempt-1),attempt=attempt,dataset_id='phase5_2c_readiness',design_version='research_design.v2',
        assembly_method=method,support_gap_m=gap)
