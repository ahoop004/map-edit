"""Offline nonlinear closure, long circuits, variable widths and exact replay."""
from copy import deepcopy
from dataclasses import replace
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import numpy as np
import pytest
from map_editor.geometry import GeometryError,GeometrySequence,hairpin,straight
from map_editor.geometry.validation import GeometryLimits,validate_raster_footprint
from map_editor.geometry.width_profile import WidthProfile
from map_editor.geometry.corridor import (vectorized_boundary_separation,_segment_distances,variable_boundaries,
    validate_corridor,raster_ray_distance,validate_raster_corridor)
from map_editor.geometry.spatial import segment_distance,minimum_boundary_separation,self_intersects
from map_editor.models.annotations import Point2D
from map_editor.services.extended_spec import (ExtendedSpec,SupportingTurn,LayoutTopology,load_vehicle_snapshot,
    load_extended_spec,spec_from_recipe,LENGTH_PRESETS)
from map_editor.services.extended_layout import extended_candidates,MotionModel,optimize_motion
from map_editor.services.extended_pilot import default_extended_specs,load_extended_pilot,generate_extended_pilot
from map_editor.services.extended_tracks import (prepare_extended,publish_extended,ExtendedGenerationError,
    validate_extended_metadata,evaluate_objectives)
from map_editor.services import extended_tracks
from map_editor.services.offline_export import rasterize_corridor
from map_editor.services.procedural_track import _rasterize_walls
from map_editor.services.geometry_metadata import validate_geometry_metadata
from map_editor.services.composite_statistics import contains
from map_editor.services.yaml_serializer import load_map_yaml

ROOT=Path(__file__).resolve().parents[1]
PILOT=ROOT/'examples/phase4b_pilot'

@pytest.fixture(scope='module')
def vehicle():return load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json')

@pytest.fixture(scope='module')
def specs(vehicle):return default_extended_specs(vehicle)

@pytest.fixture(scope='module')
def long_track(specs):return prepare_extended(specs[0])

@pytest.fixture(scope='module')
def width_pair(specs):return prepare_extended(specs[8]),prepare_extended(specs[9])


def test_offline_snapshot_and_length_design_ranges(vehicle):
    assert vehicle.length_m==.5 and vehicle.width_m==.27
    assert len(vehicle.source_sha256)==64
    assert LENGTH_PRESETS==dict(short=(70.,140.),medium=(140.,260.),long=(260.,450.))

@pytest.mark.parametrize('side', ['left','right'])
def test_periodic_width_smoothstep_and_gradient(side):
    knots=((0.,.6),(.25,1.),(.6,.8),(1.,.6))
    profile=WidthProfile(**{side:knots})
    a,b=profile.evaluate([0.,25.,60.,100.,125.],100.)
    values=a if side=='left' else b
    assert values==pytest.approx([.6,1.,.8,.6,1.])
    epsilon=.0001
    before=profile.evaluate([25.-epsilon],100.)[0 if side=='left' else 1][0]
    after=profile.evaluate([25.+epsilon],100.)[0 if side=='left' else 1][0]
    assert abs((after-before)/(2*epsilon))<1e-6
    with pytest.raises(GeometryError,match='gradient'):profile.evaluate([0.],1.)

@pytest.mark.parametrize('kwargs',[
    dict(left=((0.,.7),(1.,.8))),dict(left=((.1,.7),(1.,.7))),
    dict(right=((0.,.7),(.5,0),(1.,.7))),dict(left=((0.,.7),(.5,.8),(.4,.9),(1.,.7))),
    dict(left=((0.,.7),(.3,float('nan')),(1.,.7))),dict(maximum_gradient=0)])
def test_invalid_width_profiles(kwargs):
    with pytest.raises(GeometryError):WidthProfile(**kwargs)


def test_asymmetric_constant_offsets():
    profile=WidthProfile.constant(2.,.35)
    a,b=profile.evaluate([0,10,20],30.)
    assert a==pytest.approx([.7]*3) and b==pytest.approx([1.3]*3)
    with pytest.raises(GeometryError):WidthProfile.constant(1.5,1.)


def test_joint_supporting_headings_and_lengths_close_without_primary_full_turn(specs,long_track):
    solution=long_track.metadata['provenance']['layout_solution']
    assert abs(solution['fixed_primary_heading_rad']-math.tau)>.5
    assert sum(solution['supporting_angles_deg'])==pytest.approx(360-math.degrees(solution['fixed_primary_heading_rad']),abs=1e-7)
    assert np.max(abs(np.array(solution['supporting_angles_deg'])-solution['initial_supporting_angles_deg']))>.001
    assert max(abs(x) for x in solution['closure_residual_scaled'])<2e-9
    assert long_track.metadata['provenance']['validation']['polygon_winding_rad']==pytest.approx(math.tau)
    assert all(specs[0].connector_length_bounds_m[0]-1e-9<=x<=specs[0].connector_length_bounds_m[1]+1e-9 for x in solution['connector_lengths_m'])
    assert all(lo-1e-7<=x<=hi+1e-7 for x,(lo,hi) in zip(solution['supporting_angles_deg'],solution['supporting_angle_bounds_deg']))


def test_preserved_primary_geometry_and_supporting_classification(specs,long_track):
    for item in long_track.items:
        if item.role=='primary' and item.maneuver.type!='straight':
            assert item.maneuver==specs[0].inventory[item.inventory_index].build()
        if item.role!='primary':
            assert item.adjustable and item.maneuver.type=='transition'
            assert item.maneuver.requested['source_type'] in {'straight','sweeper'}
    assert max(j['position_m'] for j in long_track.sampled.joints)<1e-7
    assert max(j['curvature_inv_m'] for j in long_track.sampled.joints)<1e-7
    assert 300<long_track.statistics['raw_lap_length_m']<450
    assert 12<=long_track.statistics['corner_count']<=20
    assert len(long_track.geometry.samples)>3500


def test_deterministic_all_candidate_search_and_ranking(specs,long_track):
    journal=[];first=list(extended_candidates(specs[0],journal))
    journal2=[];second=list(extended_candidates(specs[0],journal2))
    assert journal==journal2
    assert first[0].items==second[0].items
    actual=long_track.metadata['provenance']['layout_attempts']
    valid=[a for a in actual if a['status'] in ('selected','valid_not_selected')]
    chosen=next(a for a in valid if a['status']=='selected')
    assert chosen['geometric_selection_score']==min(a['geometric_selection_score'] for a in valid)
    assert len({a['topology'] for a in actual})==3
    assert chosen['candidate']!=1


def test_bounded_heading_and_optimizer_failures(specs):
    spec=specs[0]
    topology=replace(spec.topologies[0],turns=tuple(replace(t,angle_bounds_deg=(12.,13.)) for t in spec.topologies[0].turns))
    with pytest.raises(ExtendedGenerationError) as caught:
        prepare_extended(replace(spec,topologies=(topology,),candidate_budget=2))
    assert len(caught.value.attempts)==2
    assert all('heading deficit' in a['reason'] for a in caught.value.attempts)
    with pytest.raises(ExtendedGenerationError) as caught:
        prepare_extended(replace(spec,optimization_iterations=1,candidate_budget=1))
    attempt=caught.value.attempts[0]
    assert attempt['failure_stage']=='closure'
    assert attempt['optimization']['converged'] is False
    assert attempt['optimization']['evaluations']>0
    assert 'within 1 iterations' in attempt['reason']


def test_opposing_supporting_turn_bounds_and_g2(vehicle):
    from map_editor.services.technical_spec import TechnicalRequest
    inventory=tuple(TechnicalRequest(str(i),'corner',dict(radius_m=3.,turn_angle_deg=90.),10.) for i in range(4))
    topology=LayoutTopology('opposing',tuple(range(4)),
        (SupportingTurn(0,(-35.,-12.),5.,.7),SupportingTurn(2,(12.,35.),5.,.7)))
    spec=ExtendedSpec(inventory,vehicle,(topology,),target_lap_length_m=150.,lap_length_range_m=(100.,200.),
        candidate_budget=1,maximum_supporting_fraction=.6,minimum_primary_coverage=.4,connector_length_bounds_m=(.4,60.))
    journal=[];candidates=list(extended_candidates(spec,journal))
    assert len(candidates)==1
    sampled=GeometrySequence([i.maneuver for i in candidates[0].items]).sample(.1,closed=True)
    assert max(j['curvature_inv_m'] for j in sampled.joints)<1e-10
    angles=candidates[0].solution['supporting_angles_deg']
    assert angles==pytest.approx([-12.,12.],abs=1e-7)
    assert candidates[0].solution['optimization']['iterations']<10


def test_width_pairs_do_not_change_centerline_or_primary_radii(specs,width_pair):
    a,b=width_pair
    assert specs[8].centerline_configuration_id==specs[9].centerline_configuration_id
    assert specs[8].configuration_id!=specs[9].configuration_id
    assert a.geometry.samples==b.geometry.samples
    assert a.items==b.items
    assert a.metadata['provenance']['layout_attempts']==b.metadata['provenance']['layout_attempts']
    assert a.geometry.walls!=b.geometry.walls
    assert b.statistics['minimum_width_m']==pytest.approx(1.2,abs=3e-6)
    assert b.statistics['maximum_width_m']>2.1
    assert b.statistics['width_std_m']>.2
    assert a.statistics['width_std_m']<1e-5
    assert b.statistics['minimum_raster_width_m']>1.
    assert b.metadata['provenance']['validation']['footprint']=='passed_at_sampled_poses'


def test_width_failure_rejects_fixed_winner_without_fallback(specs,width_pair):
    spec=replace(specs[8],width=WidthProfile.constant(.5))
    with pytest.raises(ExtendedGenerationError) as caught:prepare_extended(spec)
    selected=width_pair[0].metadata['provenance']['layout_selection']['selected_candidate']
    rejected=[a for a in caught.value.attempts if a.get('failure_stage')=='corridor']
    assert len(rejected)==1 and rejected[0]['candidate']==selected
    assert 'usable width' in rejected[0]['reason']


def test_requested_and_measured_objective_failures_remain_separate(specs,long_track):
    spec=replace(specs[0],objectives={'corner_count':(100,200),'maximum_width_m':(1.,1.2)})
    center=evaluate_objectives(spec,long_track.statistics)
    assert center['failures'][0]['metric']=='corner_count'
    assert 'maximum_width_m' not in center['requested_targets']
    widths=evaluate_objectives(spec,long_track.statistics,width=True)
    assert widths['failures'][0]['metric']=='maximum_width_m'
    with pytest.raises(ExtendedGenerationError) as caught:
        prepare_extended(replace(spec,candidate_budget=1))
    assert caught.value.attempts[0]['objective_evaluation']['failures']
    assert caught.value.attempts[0]['failure_stage']=='centerline'


def test_width_objectives_intersect_geometry_selection(specs,width_pair):
    original=width_pair[0]
    with pytest.raises(ExtendedGenerationError) as caught:
        prepare_extended(replace(specs[8],objectives={**specs[8].objectives,'minimum_width_m':(2,3)}))
    reject=next(a for a in caught.value.attempts if a.get('failure_stage')=='corridor')
    assert reject['candidate']==original.metadata['provenance']['layout_selection']['selected_candidate']
    assert reject['objective_evaluation']['requested_targets']=={'minimum_width_m':[2,3]}


def test_vector_distance_matches_scalar_for_adversarial_and_random_segments():
    rng=np.random.default_rng(42)
    tuples=rng.normal(size=(150,4,2))
    tuples[:4]=np.array([[[0,0],[2,2],[0,2],[2,0]],[[0,0],[2,0],[1,0],[3,0]],
        [[0,0],[0,1],[1,0],[1,1]],[[0,0],[1,0],[1,0],[2,0]]])
    for values in tuples:
        points=[Point2D(float(x),float(y)) for x,y in values]
        expected=segment_distance(*points)
        actual=_segment_distances(values[0],values[1],values[2:3],values[3:4])[0]
        assert actual==pytest.approx(expected,abs=1e-10)


def test_global_opposing_distance_matches_legacy(width_pair):
    for prepared in width_pair:
        assert vectorized_boundary_separation(*prepared.geometry.walls)==pytest.approx(
            minimum_boundary_separation(*prepared.geometry.walls,closed=True),abs=1e-10)

@pytest.mark.parametrize('resolution',[.05,.13,.37])
def test_active_edge_raster_identical_to_legacy(resolution):
    rng=random.Random(42)
    for n in (4,9,17):
        angles=np.arange(n)*math.tau/n
        outer=[Point2D(float(8*math.cos(a)),float(7*math.sin(a))) for a in angles]
        inner=[Point2D(float((5+rng.random()*.2)*math.cos(a)),float((4+rng.random()*.2)*math.sin(a))) for a in angles]
        actual=rasterize_corridor([outer,inner],resolution=resolution,padding=1.)
        expected=_rasterize_walls([outer,inner],resolution=resolution,padding=1.,thickness_px=1,occupancy_mode='corridor')
        assert actual==expected


def test_crossing_and_overlapping_sections_rejected(vehicle):
    sampled=GeometrySequence([straight(10),hairpin(3),straight(10),hairpin(3)]).sample(.1,closed=True)
    left,right=np.full(len(sampled.states)-1,.75),np.full(len(sampled.states)-1,.75)
    walls=variable_boundaries(sampled,left,right)
    cross=[Point2D(0.,0.),Point2D(5.,5.),Point2D(0.,5.),Point2D(5.,0.)]
    assert self_intersects(cross,closed=True)
    with pytest.raises(GeometryError,match='intersects'):
        validate_corridor(sampled,[cross,walls[1]],left+right,vehicle,GeometryLimits())
    with pytest.raises(GeometryError,match='usable width'):
        validate_corridor(sampled,[walls[0],walls[0]],left+right,vehicle,GeometryLimits())
    with pytest.raises(GeometryError,match='singularity'):
        variable_boundaries(sampled,np.full(len(left),3.),right)


def test_sampled_footprint_checks_full_area_and_raster_width(vehicle):
    sampled=GeometrySequence([straight(1)]).sample(.1)
    width,height,res=50,30,.1
    pixels=bytearray([255]*(width*height))
    pixels[(height-1-15)*width+15]=0
    with pytest.raises(GeometryError,match='occupied cell'):
        validate_raster_footprint(sampled,(bytes(pixels),width,height,-1.,-1.5,res),vehicle)
    # Exact grid-ray ownership, including rays along rows and through corners.
    p=sampled.states[0]
    black=bytearray(100)
    for row in range(2,8):
        for col in range(2,8):black[(9-row)*10+col]=255
    state=replace(p,x=.5,y=.5)
    assert raster_ray_distance(state,(1.,0.),(bytes(black),10,10,0.,0.,.1))==pytest.approx(.3)
    assert raster_ray_distance(state,(-1.,0.),(bytes(black),10,10,0.,0.,.1))==pytest.approx(.3)


def test_schema_and_periodic_annotation_integrity(long_track):
    metadata=long_track.metadata;validate_extended_metadata(metadata)
    assert metadata['schema_version']=='2.0.0'
    assert metadata['provenance']['integration']['status']=='not_run'
    assert metadata['provenance']['policy_observations_changed'] is False
    lap=metadata['measured']['length_m']
    for s in np.linspace(0,lap,701,endpoint=False):assert sum(contains(a,float(s)) for a in metadata['maneuvers'])==1
    assert any(a['wraps_seam'] and a['s_end_m']>0 for a in metadata['maneuvers'])
    bad=deepcopy(metadata);bad['provenance']['extended_statistics']['primary_coverage']=.1
    with pytest.raises(GeometryError):validate_extended_metadata(bad)
    old=deepcopy(metadata);old['schema_version']='1.0.0'
    with pytest.raises(ValueError):validate_geometry_metadata(old)

@pytest.mark.parametrize('kwargs',[
    dict(candidate_budget=0),dict(optimization_iterations=0),dict(connector_length_bounds_m=(0,3)),
    dict(target_lap_length_m=1000),dict(maximum_supporting_fraction=1.1),dict(seed=-1),
    dict(objectives={'invented':(0,1)}),dict(variant='../bad'),dict(layout_version='old'),dict(spacing_m=0)])
def test_spec_contract_rejects_invalid_settings(kwargs,specs):
    with pytest.raises(GeometryError):replace(specs[0],**kwargs)

@pytest.mark.parametrize('kwargs',[
    dict(after_index=-1),dict(angle_bounds_deg=(-10,20)),dict(angle_bounds_deg=(.1,1)),
    dict(radius_m=0),dict(transition_m=0),dict(angle_bounds_deg=(12,180))])
def test_supporting_limits_are_explicit(kwargs):
    with pytest.raises(GeometryError):SupportingTurn(**{'after_index':0,**kwargs})


def test_native_spec_roundtrip_and_identity(specs):
    spec=spec_from_recipe(json.loads(json.dumps(specs[0].recipe())))
    assert spec.configuration_id==specs[0].configuration_id
    assert spec.centerline_configuration_id==specs[0].centerline_configuration_id
    assert spec.inventory[0].build()==specs[0].inventory[0].build()


def test_partial_pilot_and_overwrite_protection(tmp_path,specs,monkeypatch):
    def impossible(spec,profile=None):raise ExtendedGenerationError('test exhaustion',[dict(candidate=1,status='rejected',failure_stage='closure',reason='test bounded failure')])
    monkeypatch.setattr(extended_tracks,'prepare_extended',impossible)
    out=tmp_path/'partial'
    report=generate_extended_pilot(specs[:1],out)
    assert report['complete'] is False and report['candidate_accounting']=={'rejected':1}
    assert report['request_failures'][0]['reason']=='test exhaustion'
    assert report['rejected'][0]['reason']=='test bounded failure'
    assert load_extended_pilot(out/'pilot_recipe.json')[0].configuration_id==specs[0].configuration_id
    assert json.loads((out/'manifest.json').read_text())==report
    with pytest.raises(FileExistsError):generate_extended_pilot(specs[:1],out)


def test_duplicate_winner_rejected_outside_matched_pair(tmp_path,specs,long_track,monkeypatch):
    monkeypatch.setattr(extended_tracks,'prepare_extended',lambda *a,**k:long_track)
    monkeypatch.setattr(extended_tracks,'publish_extended',lambda s,o,**k:Path(o)/(s.track_id+'.yaml'))
    report=generate_extended_pilot((specs[0],replace(specs[0],variant='duplicate')),tmp_path/'duplicates')
    assert len(report['accepted'])==1 and report['complete'] is False
    assert 'Duplicate' in report['request_failures'][0]['reason']


def test_published_pilot_geometry_and_matches():
    report=json.loads((PILOT/'manifest.json').read_text())
    assert report['complete'] and len(report['accepted'])==12 and len(report['matched_pairs'])==2
    from collections import Counter
    assert Counter(e['category'] for e in report['accepted'])==dict(long_technical=4,long_irregular_mixed=4,width_comparison=4)
    assert len({e['identity']['centerline_fingerprint'] for e in report['accepted']})==10
    for entry in report['accepted']:
        metadata=json.loads((PILOT/entry['metadata']).read_text());validate_extended_metadata(metadata)
        validation=json.loads((PILOT/entry['validation']).read_text())
        assert validation['integration']==dict(status='not_run',reason='offline_geometry_scope')
        assert validation['recipe_replay']==dict(status='passed',byte_identical=True,artifacts_compared=10)
        assert validation['validation']['raster_footprint']['status']=='passed_at_sampled_poses'
        if entry['category']!='width_comparison':
            assert 300<=entry['statistics']['raw_lap_length_m']<=450
            assert 12<=entry['statistics']['corner_count']<=20
    for pair in report['matched_pairs']:
        hashes=[]
        for track in pair['tracks']:
            hashes.append(hashlib.sha256((PILOT/track/(track+'_centerline.csv')).read_bytes()).hexdigest())
        assert hashes[0]==hashes[1]==pair['centerline_sha256']

@pytest.mark.parametrize('index',[0,9])
def test_fresh_process_replay_with_external_access_forbidden(index,tmp_path):
    report=json.loads((PILOT/'manifest.json').read_text());entry=report['accepted'][index]
    recipe=PILOT/entry['recipe'];output=tmp_path/'replay'
    # This guard is inherited by no external process; this offline command
    # performs both native rebuilds in the guarded interpreter itself.
    code="""
import os,sys
sys.path.insert(0,sys.argv[3])
def audit(event,args):
    if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path=os.fsdecode(args[0])
        if 'marl_race' in path.split(os.sep):raise AssertionError('Forbidden external checkout access: '+path)
    if event=='subprocess.Popen':raise AssertionError('Offline replay started a subprocess')
sys.addaudithook(audit)
from map_editor.services.extended_spec import load_extended_spec
from map_editor.services.extended_tracks import publish_extended
publish_extended(load_extended_spec(sys.argv[1]),sys.argv[2])
"""
    process=subprocess.run([sys.executable,'-c',code,str(recipe),str(output),str(ROOT/'src')],capture_output=True,text=True,timeout=90)
    assert process.returncode==0,process.stderr
    metadata=json.loads((PILOT/entry['metadata']).read_text())
    for name in [*metadata['artifacts'].values(),entry['track_id']+'_evaluation.csv']:
        assert ((PILOT/entry['map']).parent/name).read_bytes()==(output/name).read_bytes(),name
    document=load_map_yaml(output/(entry['track_id']+'.yaml'))
    assert document.annotations.spawn_points[0].name=='grid_1'
    with pytest.raises(FileExistsError):publish_extended(load_extended_spec(recipe),output)


def test_short_configuration_uses_same_standalone_contract(specs):
    base=specs[0]
    short=replace(base,inventory=tuple(replace(r,straight_after_m=r.straight_after_m*.25) for r in base.inventory),
        target_lap_length_m=120.,lap_length_range_m=LENGTH_PRESETS['short'],objectives={'corner_count':(12,20)},candidate_budget=3)
    prepared=prepare_extended(short)
    assert 70<prepared.statistics['raw_lap_length_m']<140
    assert prepared.metadata['provenance']['validation']['raster_footprint']['status']=='passed_at_sampled_poses'
