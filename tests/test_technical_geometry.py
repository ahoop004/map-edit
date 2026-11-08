"""Technical classification, distributed closure, measured objectives and replay."""
from copy import deepcopy
from dataclasses import replace
import csv
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from map_editor.geometry import GeometryError, hairpin, s_curve
from map_editor.geometry.curves import CurvatureSegment
from map_editor.geometry.measurement import validate_maneuver
from map_editor.geometry.technical import technical_corner,validate_technical,TechnicalManeuver
from map_editor.geometry.validation import VehicleProfile,GeometryLimits
from map_editor.services.geometry_metadata import validate_geometry_metadata
from map_editor.services.technical_analysis import analyze_geometry,periodic_runs,resample,read_centerline
from map_editor.services.technical_spec import TechnicalSpec,TechnicalRequest,spec_from_recipe,load_technical_spec
from map_editor.services.technical_layout import bounded_projection,layout_candidates
from map_editor.services.technical_tracks import (prepare_technical,publish_technical,TechnicalGenerationError,
    validate_technical_metadata,check_objectives)
from map_editor.services.technical_pilot import default_technical_specs,generate_technical_pilot,load_technical_pilot
from map_editor.services.composite_statistics import contains,coordinate_fingerprint,curvature_profile_fingerprint
from map_editor.services import technical_pilot

ROOT=Path(__file__).resolve().parents[1]
PILOT=ROOT/'examples/phase3b_pilot'

@pytest.fixture(scope='module')
def vehicle():
    return VehicleProfile(.5,.27,.15875,.17145,-.523599,.523599,-3.2,3.2,'combined_slip.yaml',
        'fb8bab7a7c49cb913c6adafbec84d4560e02d927087ff61956be0145f6288016','uncalibrated')

@pytest.fixture(scope='module')
def specs(vehicle):return default_technical_specs(vehicle)

@pytest.fixture(scope='module')
def prepared(specs):return prepare_technical(specs[0])

@pytest.mark.parametrize('angle,radius,end,direction,kind',[
    (30,1.4,None,'left','corner'),(90,1.5,None,'right','corner'),(150,2,None,'left','corner'),
    (75,1.4,3,'left','corner'),(110,3,1.4,'right','corner'),(12,3,None,'right','kink'),
    (35,2,None,'left','kink')])
def test_technical_requested_measured_classification(angle,radius,end,direction,kind):
    m=technical_corner(radius,angle,direction,.3,end,kind=kind)
    result=validate_technical(m,m.sample(.04))
    assert abs(math.degrees(result['signed_heading_change_rad']))==pytest.approx(angle)
    assert result['minimum_radius_m']==pytest.approx(min(radius,end or radius))
    assert m.segments[0].k_start==m.segments[-1].k_end==0
    assert all(a.k_end==b.k_start for a,b in zip(m.segments,m.segments[1:]))
    mirrored=m.mirrored();assert mirrored.type==kind
    assert mirrored.at(mirrored.length_m).y==pytest.approx(-m.at(m.length_m).y)
    validate_technical(mirrored,mirrored.sample(.04))


def test_compound_has_two_measured_apexes():
    m=technical_corner(2,110,apex_radii_m=[3.5,1.5,4,1.8,3.5],kind='compound_corner')
    result=validate_technical(m,m.sample(.04))
    assert result['profile']=='compound'
    assert result['achieved_body_radii_m']==pytest.approx([3.5,1.5,4,1.8,3.5])

@pytest.mark.parametrize('kwargs',[
    dict(turn_angle_deg=25),dict(turn_angle_deg=151),dict(radius_m=0),dict(transition_m=0),
    dict(kind='kink',turn_angle_deg=60),dict(direction='none'),dict(radius_m=float('nan')),
    dict(apex_radii_m=[2,1,2,2,3],kind='compound_corner'),dict(apex_radii_m=[2,1,3]),
    dict(turn_angle_deg=30,radius_m=1,transition_m=3)])
def test_technical_invalid_requests(kwargs):
    with pytest.raises(GeometryError):technical_corner(**kwargs)


def test_wrong_hairpin_and_corner_labels_fail():
    corner=technical_corner(1.5,90)
    wrong=hairpin(1.5,turn_angle_rad=math.pi/2)
    with pytest.raises(GeometryError,match='hairpin'):validate_maneuver(wrong,wrong.sample(.05))
    changed=replace(corner,requested=dict(corner.requested,turn_angle_deg=120))
    with pytest.raises(GeometryError,match='angle'):validate_technical(changed,changed.sample(.05))
    invalid=replace(corner,requested=dict(corner.requested,turn_angle_deg=200))
    with pytest.raises(GeometryError,match='classification'):validate_technical(invalid,invalid.sample(.05))


def test_tight_opposing_turns_keep_explicit_existing_family():
    m=s_curve((1.4,1.7),.7,.6)
    result=validate_maneuver(m,m.sample(.04))
    assert result['direction_reversals']==1
    assert result['minimum_radius_m']==pytest.approx(1.4)


def test_bounded_projection_exact_closure_and_optimum():
    a=np.array([[1,0,-1,0],[0,1,0,-1],[1,1,1,1.]])
    target=np.array([1.,7.,2.,3.]);rhs=np.array([0.,0.,16.])
    x,info=bounded_projection(a,rhs,target,.5,8.)
    assert a@x==pytest.approx(rhs,abs=1e-9)
    assert min(x)>=.5 and max(x)<=8
    for t in np.linspace(-2,2,21):
        other=x+t*np.array([1.,-1,1,-1])
        if min(other)>=.5 and max(other)<=8:
            assert np.sum((x-target)**2)<=np.sum((other-target)**2)+1e-7
    assert info['residual']<1e-9


def test_projection_bounds_exhaustion_and_rank():
    with pytest.raises(GeometryError,match='exhausted'):
        bounded_projection(np.eye(3),np.ones(3)*10,np.ones(3),0,1,iterations=3)
    with pytest.raises(GeometryError,match='rank'):
        bounded_projection(np.zeros((3,4)),np.ones(3),np.ones(4),0,1)


def test_generalized_layout_preserves_all_primary_geometry(specs,prepared):
    for item in prepared.items:
        if item.role=='primary' and item.maneuver.type!='straight':
            original=specs[0].inventory[item.inventory_index].build()
            assert item.maneuver==original
        elif item.role!='primary':
            assert item.adjustable and item.maneuver.type=='transition'
            assert item.maneuver.requested['source_type']=='straight'
    assert max(j['position_m'] for j in prepared.sampled.joints)<1e-7
    assert max(j['curvature_inv_m'] for j in prepared.sampled.joints)<1e-10
    assert prepared.statistics['primary_coverage']+prepared.statistics['supporting_fraction']==pytest.approx(1.)
    assert abs(prepared.statistics['raw_lap_length_m']-specs[0].target_lap_length_m)<.01


def test_multi_topology_search_scores_all_valid_candidates(prepared):
    provenance=prepared.metadata['provenance'];attempts=provenance['layout_attempts']
    assert len(attempts)==6
    valid=[a for a in attempts if a['status'] in ('selected','valid_not_selected')]
    assert len(valid)>1 and len({a['topology_index'] for a in valid})>1
    selected=next(a for a in valid if a['status']=='selected')
    assert selected['geometric_selection_score']==min(a['geometric_selection_score'] for a in valid)
    assert selected['candidate']!=1
    for a in attempts:
        assert a['adjustable_geometry']=='distributed_straight_lengths'
        assert a['status'] in {'selected','valid_not_selected','rejected'}


def test_cyclic_and_rigid_geometry_fingerprints(prepared):
    xy=prepared.sampled.points;n=len(xy)
    assert coordinate_fingerprint(xy,1.5)==coordinate_fingerprint(xy[27:]+xy[:27],1.5)
    assert coordinate_fingerprint(xy,1.5)==coordinate_fingerprint(xy[::-1],1.5)
    items=list(prepared.items)
    assert curvature_profile_fingerprint(items,1.5)==curvature_profile_fingerprint(items[3:]+items[:3],1.5)


def test_duplicate_winner_cannot_change_native_recipe(specs,prepared):
    with pytest.raises(TechnicalGenerationError,match='Duplicate'):
        prepare_technical(specs[0],{prepared.metadata['provenance']['identity']['geometry_fingerprint']})


def test_impossible_heading_and_length_are_bounded(specs):
    request=specs[0].inventory[0]
    bad=replace(request,parameters=dict(request.parameters,turn_angle_deg=80))
    spec=replace(specs[0],inventory=(bad,*specs[0].inventory[1:]),candidate_budget=2)
    with pytest.raises(TechnicalGenerationError) as caught:prepare_technical(spec)
    assert len(caught.value.attempts)==2
    assert all('360' in r['reason'] for r in caught.value.attempts)
    with pytest.raises(TechnicalGenerationError) as caught:
        prepare_technical(replace(specs[0],connector_bounds_m=(.4,.5),candidate_budget=1))
    assert 'bounds' in caught.value.attempts[0]['reason']

@pytest.mark.parametrize('key,bounds',[
    ('corner_density_per_100m',(100,200)),('p95_curvature_inv_m',(10,11)),
    ('curvature_reversals',(100,200)),('longest_straight_m',(1000,2000)),
    ('minimum_corner_angle_deg',(170,180)),('supporting_fraction',(0,.01)),
    ('symmetry_error_m',(0,1e-9)),('repetition_fraction',(1,1))])
def test_complexity_targets_are_hard_constraints(key,bounds,specs,prepared):
    with pytest.raises(GeometryError,match=key):check_objectives(replace(specs[0],objectives={key:bounds}),prepared.statistics)


def test_periodic_windows_and_metadata_schema(prepared):
    m=prepared.metadata;validate_technical_metadata(m)
    assert m['schema_version']=='2.0.0'
    assert any(a['wraps_seam'] and a['s_end_m']>0 for a in m['maneuvers'])
    lap=m['measured']['length_m']
    for s in np.linspace(0,lap,1001,endpoint=False):assert sum(contains(a,s) for a in m['maneuvers'])==1
    old=deepcopy(m);old['schema_version']='1.0.0'
    with pytest.raises(ValueError):validate_geometry_metadata(old)
    tamper=deepcopy(m);tamper['provenance']['technical_statistics']['primary_coverage']=.1
    with pytest.raises(GeometryError,match='exposure'):validate_technical_metadata(tamper)
    assert m['provenance']['policy_observations_changed'] is False
    assert m['provenance']['validation']['geometric_steering_within_vehicle_bounds']


def test_scale_analysis_reduces_sampling_noise_and_is_periodic():
    t=np.arange(1200)*math.tau/1200
    radius=5+.002*np.sin(91*t)
    xy=np.column_stack([radius*np.cos(t),radius*np.sin(t)])
    raw=analyze_geometry(xy,sigma_m=0);smooth=analyze_geometry(xy,sigma_m=.4)
    assert smooth['p95_curvature_inv_m']<raw['p95_curvature_inv_m']*.6
    assert smooth['minimum_sustained_radius_m']==pytest.approx(5,rel=.03)
    assert smooth['corner_count']==1 and smooth['curvature_reversals']==0
    shifted=analyze_geometry(np.roll(xy,100,axis=0),sigma_m=.4)
    assert shifted['p95_curvature_inv_m']==pytest.approx(smooth['p95_curvature_inv_m'],rel=.01)
    runs=periodic_runs([1,1,0,-1,-1,1])
    assert sorted(len(r) for r in runs)==[1,2,3]
    with pytest.raises(ValueError):resample([[0,0],[1,0],[2,0]])


def test_native_recipe_roundtrip_and_old_default_not_serialized(specs):
    spec=spec_from_recipe(json.loads(json.dumps(specs[0].recipe())))
    assert spec.configuration_id==specs[0].configuration_id
    assert spec.inventory[0].build()==specs[0].inventory[0].build()
    from map_editor.services.parametric_track import ParametricTrackSpec
    assert 'metadata_schema_version' not in ParametricTrackSpec('legacy',()).recipe()

@pytest.mark.parametrize('kwargs',[
    dict(candidate_budget=0),dict(optimization_iterations=0),dict(objectives={'unknown':(0,1)}),
    dict(connector_bounds_m=(0,1)),dict(lap_length_range_m=(1,2)),dict(seed=-1),
    dict(maximum_supporting_fraction=1.1),dict(topology_orders=((0,1),)),dict(variant='../bad')])
def test_spec_contract_invalid(kwargs,specs):
    with pytest.raises(GeometryError):replace(specs[0],**kwargs)


def test_partial_manifest_and_overwrite_are_auditable(tmp_path,specs,monkeypatch):
    def fail(spec):raise TechnicalGenerationError('forced exhaustion',[dict(candidate=1,status='rejected',reason='infeasible test')])
    monkeypatch.setattr(technical_pilot,'prepare_technical',fail)
    reference=tmp_path/'reference';(reference/'src/utils').mkdir(parents=True)
    (reference/'src/utils/map_loader.py').touch()
    out=tmp_path/'pilot'
    result=generate_technical_pilot(specs[:1],out,reference=reference)
    assert result['complete'] is False and result['incomplete_requests']==[specs[0].variant]
    assert result['rejected'][0]['reason']=='infeasible test'
    assert json.loads((out/'manifest.json').read_text())==result
    assert load_technical_pilot(out/'pilot_recipe.json')[0].configuration_id==specs[0].configuration_id
    with pytest.raises(FileExistsError):generate_technical_pilot(specs[:1],out,reference=reference)


def test_published_pilot_evidence():
    manifest=json.loads((PILOT/'manifest.json').read_text())
    assert manifest['complete'] and len(manifest['accepted'])==12
    assert len({e['identity']['geometry_fingerprint'] for e in manifest['accepted']})==12
    from collections import Counter
    assert set(Counter(e['category'] for e in manifest['accepted']).values())=={3}
    assert len({tuple(e['identity']['topology_order']) for e in manifest['accepted']})>=3
    for entry in manifest['accepted']:
        metadata=json.loads((PILOT/entry['metadata']).read_text());validate_technical_metadata(metadata)
        report=json.loads((PILOT/entry['validation']).read_text())
        assert report['integration']['status']=='passed'
        assert report['recipe_replay']==dict(status='passed',byte_identical=True,artifacts_compared=10)
        assert report['validation']['exported_raster_footprint']['status']=='passed_at_sampled_poses'
        assert entry['statistics']['symmetry_error_m']>.1
        assert entry['statistics']['supporting_fraction']<=.45

@pytest.mark.parametrize('index',[0,10])
def test_golden_native_replay_in_fresh_process(index,tmp_path):
    entry=json.loads((PILOT/'manifest.json').read_text())['accepted'][index]
    metadata=json.loads((PILOT/entry['metadata']).read_text())
    folder=(PILOT/entry['map']).parent;recipe=folder/metadata['artifacts']['recipe']
    out=tmp_path/'replay'
    code='from map_editor.services.technical_tracks import publish_technical; from map_editor.services.technical_spec import load_technical_spec; import sys; publish_technical(load_technical_spec(sys.argv[1]),sys.argv[2])'
    import os
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
    subprocess.run([sys.executable,'-c',code,str(recipe),str(out)],env=env,check=True,capture_output=True)
    for name in [*metadata['artifacts'].values(),entry['track_id']+'_evaluation.csv']:
        assert (folder/name).read_bytes()==(out/name).read_bytes(),name
    with pytest.raises(FileExistsError):publish_technical(load_technical_spec(recipe),out)

@pytest.mark.parametrize('key',['median_corner_angle_deg','p90_corner_angle_deg','corner_angle_std_deg'])
def test_turn_angle_distribution_objectives(key,specs,prepared):
    assert math.isfinite(prepared.statistics[key])
    with pytest.raises(GeometryError,match=key):
        check_objectives(replace(specs[0],objectives={key:(1000,2000)}),prepared.statistics)

@pytest.mark.parametrize('change,reason',[
    (dict(limits=GeometryLimits(maximum_curvature_rate_inv_m2=.1)),'Curvature-change'),
    (dict(track_width_m=4.),'singularity')])
def test_extreme_geometry_is_rejected_by_shared_validation(change,reason,specs):
    with pytest.raises(TechnicalGenerationError) as caught:
        prepare_technical(replace(specs[0],candidate_budget=1,**change))
    assert reason in caught.value.attempts[0]['reason']


def test_schema2_parametric_opt_in_roundtrip(tmp_path):
    from map_editor.services.parametric_track import ParametricTrackSpec,load_parametric_spec
    import yaml
    spec=ParametricTrackSpec('technical_opt_in',(technical_corner(),),metadata_schema_version='2.0.0')
    path=tmp_path/'recipe.yaml';path.write_text(yaml.safe_dump(spec.recipe()))
    loaded=load_parametric_spec(path)
    assert loaded.maneuvers==spec.maneuvers and loaded.recipe()==spec.recipe()


def test_stated_limits_intersect_user_targets(specs,prepared,tmp_path):
    for key,bounds in [('primary_coverage',(.99,1)),('raw_lap_length_m',(1,2))]:
        with pytest.raises(GeometryError,match=key):
            check_objectives(replace(specs[0],objectives={key:bounds}),prepared.statistics)
    with pytest.raises(GeometryError,match='publication recipe'):
        publish_technical(replace(specs[0],variant='other'),tmp_path/'mismatch',prepared=prepared)
