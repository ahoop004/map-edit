"""Formal quota, native replay, independence, lineage and restart regressions."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import pytest
from map_editor.geometry import GeometryError
from map_editor.services.dataset_spec import (default_dataset_spec,verify_allocation,candidate_seed,load_dataset_spec,SCALES,SPLIT_SCALES)
from map_editor.services.dataset_diversity import normalized_shape,shape_distance,pair_metrics,classify_pair
from map_editor.services.research_spec import load_research_spec,spec_from_recipe
from map_editor.services.research_tracks import prepare_research,publish_research,validate_research_metadata,ResearchGenerationError
from map_editor.services.research_design import candidate_spec
from map_editor.services.research_dataset import (generate_dataset,audit_dataset,verify_entry,quota_report,scale_of,safe_path,_save_manifests)
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.extended_analysis import shape_distance as slow_shape_distance
from map_editor.services.technical_analysis import read_centerline
from map_editor.services import research_dataset
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'datasets/phase5_v1'
EVIDENCE=dict(snapshot=ROOT/'profiles/f110_resolved_phase3b.json',calibration=ROOT/'docs/phase5_calibration.json',readiness=ROOT/'docs/phase5_readiness.json')

@pytest.fixture(scope='module')
def spec():return default_dataset_spec()

@pytest.fixture(scope='module')
def vehicle():return load_vehicle_snapshot(EVIDENCE['snapshot'])

@pytest.fixture(scope='module')
def master():return json.loads((DATA/'manifest.json').read_text())


def test_exact_joint_allocation_before_generation(spec):
    from collections import Counter
    assert len(spec.slots)==60
    verify_allocation(spec.slots)
    assert Counter(s.scale for s in spec.slots)==dict(short=18,medium=22,long=20)
    assert Counter(s.split for s in spec.slots)==dict(train=40,validation=8,test=12)
    for split in SPLIT_SCALES:assert Counter(s.scale for s in spec.slots if s.split==split)==SPLIT_SCALES[split]
    train=[s for s in spec.slots if s.split=='train' and s.generation_mode=='composite']
    assert Counter(2 if s.complexity==2 else 3 if s.complexity==3 else 4 for s in train)=={2:6,3:8,4:6}
    assert len({s.parent_lineage for s in spec.slots})==60
    # Complexity is not assigned as a synonym for scale.
    for k in (2,3,4):assert len({s.scale for s in train if (2 if s.complexity==2 else 3 if s.complexity==3 else 4)==k})>=2

@pytest.mark.parametrize('change',['missing','duplicate','scale','family','lineage'])
def test_invalid_allocation_rejected(change,spec):
    slots=list(spec.slots)
    if change=='missing':slots.pop()
    elif change=='duplicate':slots[-1]=slots[0]
    elif change=='scale':slots[0]=replace(slots[0],scale='long')
    elif change=='family':slots[0]=replace(slots[0],family='hairpin')
    else:slots[1]=replace(slots[1],parent_lineage=slots[0].parent_lineage)
    with pytest.raises(GeometryError):replace(spec,slots=tuple(slots))


@pytest.mark.parametrize('change',['missing','nan','zero','inverted'])
def test_invalid_dataset_objectives_rejected(change,spec):
    objectives=dict(spec.objective_ranges)
    if change=='missing':objectives.pop('minimum_target_active_fraction')
    elif change=='nan':objectives['maximum_curvature_rate_inv_m2']=float('nan')
    elif change=='zero':objectives['minimum_usable_width_m']=0
    else:objectives['minimum_composite_family_exposure']=.9
    with pytest.raises(GeometryError):replace(spec,objective_ranges=objectives)


@pytest.mark.parametrize('fraction',[0.,1.1,float('nan')])
def test_invalid_native_active_exposure_rejected(fraction,master):
    native=load_research_spec(DATA/master['accepted'][0]['recipe'])
    with pytest.raises(GeometryError):replace(native,minimum_target_active_fraction=fraction)


def test_seeds_are_independent_and_restart_stable(spec):
    seeds=[candidate_seed(spec,s,a) for s in spec.slots for a in range(1,4)]
    assert len(seeds)==len(set(seeds))
    assert seeds[:3]==[candidate_seed(spec,spec.slots[0],a) for a in range(1,4)]
    assert seeds[0]!=candidate_seed(replace(spec,root_seed=99),spec.slots[0],1)

@pytest.mark.parametrize('length,scale',[(70,'short'),(139.999,'short'),(140,'medium'),(259.999,'medium'),(260,'long'),(450,'long')])
def test_half_open_scale_quotas(length,scale):assert scale_of(length)==scale

@pytest.mark.parametrize('length',[69.99,450.01,float('nan')])
def test_out_of_scale_lengths_rejected(length):
    with pytest.raises(GeometryError):scale_of(length)


def test_development_readiness_every_family_and_scale():
    r=json.loads(EVIDENCE['readiness'].read_text())
    assert r['complete'] and len(r['cases'])==15 and r['formal_dataset'] is False
    for c in r['cases']:
        assert c['status']=='passed' and c['measured']['target_exposure_fraction']>=c['recipe']['minimum_target_exposure']
        assert c['footprint']['status']=='passed_at_sampled_poses'
    calibration=json.loads(EVIDENCE['calibration'].read_text())
    assert calibration['frozen_before_formal_generation']
    assert 'no held-out' in calibration['calibration_sources']
    assert all(not c['accepted_as_independent'] for c in calibration['forbidden_transform_checks'])


def test_fast_shape_distance_matches_existing_metric():
    t=np.arange(500)*math.tau/500
    a=np.c_[9*np.cos(t)+.4*np.sin(3*t),5*np.sin(t)]
    b=np.c_[8*np.cos(t)+np.sin(4*t),4.7*np.sin(t)]
    assert shape_distance(normalized_shape(a),normalized_shape(b))==pytest.approx(slow_shape_distance(a,b),abs=1e-8)
    for changed in (a[::-1],a*[-1,1],a+[20,50],np.roll(a,100,axis=0)):
        assert shape_distance(normalized_shape(a),normalized_shape(changed))<.01


def test_frozen_near_duplicate_and_ambiguous_policy(spec):
    metrics=dict(normalized_shape_distance=.02,relative_length=.05,relative_sustained_radius=.05,relative_p95_curvature=.05,family_exposure_l1=.03,corner_count_difference=0)
    assert classify_pair(metrics,spec.policy)=='near_duplicate'
    assert classify_pair(dict(metrics,normalized_shape_distance=.07),spec.policy)=='ambiguous'
    assert classify_pair(dict(metrics,relative_length=.3),spec.policy)=='independent_under_policy'
    assert classify_pair(dict(metrics,normalized_shape_distance=.2),spec.policy)=='independent_under_policy'


def test_formal_sixty_independent_layouts(master):
    assert master['complete'] and len(master['accepted'])==60
    assert len({e['identity']['centerline_fingerprint'] for e in master['accepted']})==60
    assert len({e['identity']['coordinate_fingerprint'] for e in master['accepted']})==60
    audit=audit_dataset(DATA,require_complete=True)
    assert audit['complete'] and len(audit['pairwise_comparisons'])==1770
    assert not audit['near_duplicate_pairs'] and not audit['cross_split_lineage_leaks'] and not audit['cross_split_near_group_leaks']
    assert audit['quotas']['scale_counts']==dict(short=18,medium=22,long=20)
    assert len(audit['candidate_evidence_sha256'])==88
    assert len(audit['bundle_file_checks'])==60
    assert all(c['png_pgm_agreement']=='byte_identical_pixels' and
        c['named_spawn']=='passed_geometrically' for c in audit['bundle_file_checks'].values())

@pytest.mark.parametrize('split,expected',[('train',40),('validation',8),('test',12)])
def test_split_manifests_paths_and_no_leakage(split,expected,master):
    manifest=json.loads((DATA/(split+'_manifest.json')).read_text())
    assert manifest['complete'] and len(manifest['accepted'])==expected
    assert manifest['accepted']==[e for e in master['accepted'] if e['split']==split]
    paths=(DATA/(split+'_maps.txt')).read_text().splitlines()
    assert paths==[e['map'] for e in manifest['accepted']]
    for path in paths:assert safe_path(DATA,path).is_file()
    parents=[set(e['parent_lineage'] for e in master['accepted'] if e['split']==s) for s in SPLIT_SCALES]
    assert all(not (a&b) for i,a in enumerate(parents) for b in parents[i+1:])

@pytest.mark.parametrize('family',['straight','hairpin','sweeper','chicane','s_curve'])
def test_measured_specialist_not_composite_relabel(family,master):
    selected=[e for e in master['accepted'] if e['target_family']==family]
    assert len(selected)==6
    assert {e['scale'] for e in selected}==set(SCALES)
    assert sum(e['split']=='train' for e in selected)==4
    for e in selected:
        m=json.loads((DATA/e['metadata']).read_text());validate_research_metadata(m)
        native=load_research_spec(DATA/e['recipe']);s=e['statistics']
        assert m['generation_mode']=='specialist' and s['measured_primary_families']==[family]
        assert s['target_exposure_fraction']>=native.minimum_target_exposure
        primary=[a for a in m['maneuvers'] if a['requested']['composition_role']=='primary']
        assert all(a['type']==family for a in primary)
        assert len(primary)>=2
        if family=='hairpin':assert all(150-.3<=abs(math.degrees(a['measured']['signed_heading_change_rad']))<=210+.3 for a in primary)
        if family=='sweeper':assert all(a['measured']['minimum_radius_m']>=5 for a in primary)


def test_measured_training_composite_complexity(master):
    from collections import Counter
    entries=[e for e in master['accepted'] if e['split']=='train' and e['generation_mode']=='composite']
    assert len(entries)==20
    assert Counter(2 if e['complexity']==2 else 3 if e['complexity']==3 else 4 for e in entries)=={2:6,3:8,4:6}
    for e in entries:
        assert e['statistics']['primary_family_count']==e['complexity']
        assert min(e['statistics']['primary_family_exposure_fractions'].values())>=.025


def test_all_artifact_hashes_and_native_reports(master):
    for e in master['accepted']:
        verify_entry(DATA,e)
        assert len(e['artifact_sha256'])==11
        report=json.loads((DATA/e['validation']).read_text())
        assert report['recipe_replay']==dict(status='passed',byte_identical=True,artifacts_compared=10)
        assert report['integration']['status']=='not_run' and report['physical_drivability']=='unassessed' and report['driving_difficulty']=='unrated'
        assert report['validation']['raster_footprint']['status']=='passed_at_sampled_poses'
    assert len({e['identity']['width_sha256'] for e in master['accepted']})>20

@pytest.mark.parametrize('path',['../escape','/absolute','tracks/../../bad','a\\b'])
def test_unsafe_dataset_paths_rejected(path):
    with pytest.raises(GeometryError):safe_path(DATA,path)


def test_manifest_tampering_rejected(master):
    entry=deepcopy(master['accepted'][0]);entry['statistics']['raw_lap_length_m']+=1
    with pytest.raises(GeometryError,match='statistics'):verify_entry(DATA,entry)
    entry=deepcopy(master['accepted'][0]);entry['artifact_sha256'].pop(next(iter(entry['artifact_sha256'])))
    with pytest.raises(GeometryError,match='coverage'):verify_entry(DATA,entry)
    for field,value in [('parent_lineage','other_parent'),('generation_mode','composite'),('seed',0),('attempt',24)]:
        entry=deepcopy(master['accepted'][0]);entry[field]=value
        with pytest.raises(GeometryError,match='identity differs'):verify_entry(DATA,entry)


def test_partial_generation_recovery_and_accepted_immutability(tmp_path,spec):
    root=tmp_path/'partial'
    first=generate_dataset(spec,root,**EVIDENCE,max_requests=1)
    assert first['complete'] is False and len(first['accepted'])==1
    accepted=deepcopy(first['accepted'][0]);before={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in accepted['artifact_sha256']}
    second=generate_dataset(spec,root,**EVIDENCE,resume=True,max_requests=1)
    assert second['complete'] is False and len(second['accepted'])==2
    assert second['accepted'][0]==accepted
    assert before=={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in before}
    with pytest.raises(FileExistsError):generate_dataset(spec,root,**EVIDENCE,max_requests=1)
    with pytest.raises(GeometryError,match='recipe'):generate_dataset(replace(spec,root_seed=43),root,**EVIDENCE,resume=True)
    with pytest.raises(GeometryError,match='partial'):audit_dataset(root,require_complete=True)


def test_orphan_bundle_adoption_after_interrupted_checkpoint(tmp_path,spec):
    root=tmp_path/'orphan';manifest=generate_dataset(spec,root,**EVIDENCE,max_requests=1)
    entry=deepcopy(manifest['accepted'][0]);manifest['accepted']=[];manifest['incomplete_requests']=[s.slot_id for s in spec.slots];_save_manifests(root,manifest)
    recovered=generate_dataset(spec,root,**EVIDENCE,resume=True,max_requests=1)
    assert len(recovered['accepted'])==1 and recovered['accepted'][0]['artifact_sha256']==entry['artifact_sha256']


def test_partial_failed_candidate_evidence_is_preserved(tmp_path,spec,monkeypatch):
    def fail(*a,**k):raise ResearchGenerationError('bounded test failure',[dict(status='rejected',failure_stage='closure',reason='test infeasible')])
    monkeypatch.setattr(research_dataset,'prepare_research',fail)
    bounded=replace(spec,max_attempts=2)
    root=tmp_path/'failures';r=generate_dataset(bounded,root,**EVIDENCE,max_requests=1)
    assert not r['complete'] and len(r['rejected'])==2
    evidence=list((root/'evidence').rglob('*.json'));hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}
    assert len(evidence)==2
    again=generate_dataset(bounded,root,**EVIDENCE,resume=True,max_requests=1)
    assert len(again['rejected'])==2 and hashes=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}
    record=json.loads(evidence[0].read_text());record['reason']='tampered rejection'
    evidence[0].write_text(json.dumps(record))
    with pytest.raises(GeometryError,match='evidence checksum'):generate_dataset(bounded,root,**EVIDENCE,resume=True)


def test_completed_resume_does_not_rewrite_publication(master):
    before=(DATA/'manifest.json').read_bytes()
    spec=load_dataset_spec(DATA/'dataset_recipe.json')
    resumed=generate_dataset(spec,DATA,**EVIDENCE,resume=True)
    assert resumed==master and (DATA/'manifest.json').read_bytes()==before

@pytest.mark.parametrize('mode',['specialist','composite'])
def test_fresh_process_native_byte_replay_forbids_external_runtime(mode,tmp_path,master):
    entry=next(e for e in master['accepted'] if e['generation_mode']==mode)
    out=tmp_path/'native'
    code="""
import os,sys
sys.path.insert(0,sys.argv[3])
def audit(event,args):
    if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)):
        if 'marl_race' in os.fsdecode(args[0]).split(os.sep):raise AssertionError('Forbidden external checkout access')
    if event=='subprocess.Popen':raise AssertionError('No runtime subprocess allowed')
sys.addaudithook(audit)
from map_editor.services.research_spec import load_research_spec
from map_editor.services.research_tracks import publish_research
publish_research(load_research_spec(sys.argv[1]),sys.argv[2])
"""
    p=subprocess.run([sys.executable,'-c',code,str(DATA/entry['recipe']),str(out),str(ROOT/'src')],text=True,capture_output=True,timeout=90)
    assert p.returncode==0,p.stderr
    metadata=json.loads((DATA/entry['metadata']).read_text())
    for name in [*metadata['artifacts'].values(),entry['track_id']+'_evaluation.csv']:
        assert ((DATA/entry['map']).parent/name).read_bytes()==(out/name).read_bytes(),name


@pytest.mark.parametrize('family,scale,variant',[
    ('hairpin','short',0),('hairpin','medium',1),('hairpin','long',2),
    ('sweeper','medium',0),('sweeper','long',1),('chicane','short',0),
    ('s_curve','medium',0),('composite','medium',0),('composite','medium',1),('composite','long',2)])
def test_experimental_parameters_keep_physical_radii(family,scale,variant):
    from map_editor.services.research_design import experimental_spec
    vehicle=load_vehicle_snapshot(EVIDENCE['snapshot'])
    spec=experimental_spec(family,scale,variant,51000,vehicle)
    assert spec.recipe()==experimental_spec(family,scale,variant,51000,vehicle).recipe()
    assert spec.assembly_method=='bounded_supporting_turns.v1'
    assert spec.limits.minimum_usable_width_m==.7
    assert spec.limits.maximum_curvature_rate_inv_m2==2.
    if family=='hairpin':
        assert len(spec.inventory)==dict(short=5,medium=9,long=15)[scale]
        assert {r.parameters['direction'] for r in spec.inventory}=={'left','right'}
        assert all(3<=r.parameters['radius_m']<=6 for r in spec.inventory)
    elif family=='sweeper':
        assert len(spec.inventory)==(5 if scale=='medium' else 9)
        assert all(6<=r.parameters['radius_m']<=15 for r in spec.inventory)
    if family!='composite':
        assert spec.minimum_target_exposure==.5
        assert {r.family for r in spec.inventory}=={family}


def test_experimental_tuning_preserves_formal_design_native_requests(spec,master):
    vehicle=load_vehicle_snapshot(EVIDENCE['snapshot']);slots={s.slot_id:s for s in spec.slots}
    for entry in master['accepted']:
        requested=candidate_spec(spec,slots[entry['slot_id']],entry['attempt'],vehicle)
        saved=load_research_spec(DATA/entry['recipe'])
        assert requested.configuration_id==saved.configuration_id


def test_v2_opt_in_contract_and_allocation_roundtrip(tmp_path,vehicle):
    v1=default_dataset_spec();v2=default_dataset_spec(design_version='research_design.v2')
    assert v1.design_version=='research_design.v1' and v1.dataset_id=='phase5_research_v1'
    assert v2.dataset_id=='phase5_v2' and v2.identity!=v1.identity
    assert v1.policy==v2.policy and v1.objective_ranges==v2.objective_ranges
    assert [(s.slot_id,s.split,s.scale,s.generation_mode,s.complexity) for s in v1.slots]==[
        (s.slot_id,s.split,s.scale,s.generation_mode,s.complexity) for s in v2.slots]
    assert not set(s.parent_lineage for s in v1.slots)&set(s.parent_lineage for s in v2.slots)
    recipe=tmp_path/'dataset.json';recipe.write_text(json.dumps(v2.recipe()))
    assert load_dataset_spec(recipe).identity==v2.identity
    for slot in v2.slots:
        spec=candidate_spec(v2,slot,1,vehicle)
        assert spec.recipe()==candidate_spec(v2,slot,1,vehicle).recipe()
        assert spec.configuration_id==spec_from_recipe(spec.recipe()).configuration_id
        assert spec.recipe()['design_version']=='research_design.v2'
        assert (spec.split,spec.parent_lineage,spec.slot_id,spec.seed)==(
            slot.split,slot.parent_lineage,slot.slot_id,candidate_seed(v2,slot,1))
        assert spec.expected_primary_families==(slot.complexity or 1)
        if slot.complexity:
            assert spec.minimum_primary_coverage>=.6 and spec.maximum_supporting_fraction<=.4
        else:
            assert spec.minimum_target_exposure==.5 and spec.minimum_primary_coverage==.5
        assert spec.limits.minimum_usable_width_m==.7
        assert spec.limits.maximum_curvature_rate_inv_m2==2.


@pytest.mark.parametrize('family,scale,variant',[
    ('hairpin','short',0),('hairpin','medium',1),('hairpin','long',2),
    ('sweeper','medium',0),('sweeper','long',1),('chicane','short',0),
    ('s_curve','medium',0),('composite','medium',0),('composite','medium',1),('composite','long',2)])
def test_v2_physical_ranges_and_resolved_design(family,scale,variant,vehicle):
    from map_editor.services.research_design import refined_spec
    spec=refined_spec(family,scale,variant,52000,vehicle)
    assert spec.recipe()==refined_spec(family,scale,variant,52000,vehicle).recipe()
    assert spec.assembly_method=='bounded_supporting_turns.v1'
    assert spec_from_recipe(spec.recipe()).configuration_id==spec.configuration_id
    for r in spec.inventory:
        p=r.parameters
        if r.family=='hairpin':
            assert 3<=p['radius_m']<=6 and math.radians(160)<=p['turn_angle_rad']<=math.radians(190)
        elif r.family=='sweeper':
            assert all(6<=v<=15 for v in (p['radius_m'],p.get('end_radius_m') or p['radius_m']))
            assert math.radians(45)<=p['turn_angle_rad']<=math.radians(120)
        elif r.family=='chicane':
            assert 2<=p['radius_m']<=5 and 1.5<=p['lateral_displacement_m']<=4
            assert p['separation_m']<=.5
        elif r.family=='s_curve':
            assert all(3<=v<=8 for v in p['radii_m'])
            assert math.radians(45)<=p['turn_angle_rad']<=math.radians(90)
    if family=='hairpin':assert {r.parameters['direction'] for r in spec.inventory}=={'left','right'}
    if family=='composite':
        assert spec.minimum_primary_coverage==.6 and spec.maximum_supporting_fraction==.4
        assert sum(r.build().length_m for r in spec.inventory)/spec.target_lap_length_m>=.6


def test_v2_rejects_unknown_versions_and_retains_v1_recipe_bytes(vehicle):
    from map_editor.services.research_design import refined_spec
    v2=default_dataset_spec(design_version='research_design.v2')
    with pytest.raises(GeometryError,match='design version'):replace(v2,design_version='research_design.v3')
    native=refined_spec('hairpin','short',0,52000,vehicle)
    with pytest.raises(GeometryError,match='design version'):replace(native,design_version='research_design.v3')
    assert 'design_version' not in replace(native,design_version='research_design.v1').recipe()
    slot=next(s for s in v2.slots if s.family=='hairpin')
    attempts=[candidate_spec(v2,slot,a,vehicle) for a in range(1,4)]
    assert {s.topology_family for s in attempts}=={'unequal_folded_lanes'}
    assert len({len(s.inventory) for s in attempts})==3
    assert all(s.candidate_budget==1 for s in attempts)
    assert len({s.seed for s in attempts})==3


@pytest.mark.parametrize('family,scale,variant,seed,attempt,count,target',[
    ('hairpin','medium',1,53001,2,7,180.),
    ('hairpin','long',2,53002,1,17,390.),
    ('composite','medium',0,53007,6,11,145.)])
def test_v2_corrected_inventory_preserves_physical_coverage(family,scale,variant,seed,attempt,count,target,vehicle):
    from map_editor.services.research_design import corrected_spec
    native=corrected_spec(family,scale,variant,seed,vehicle,attempt)
    assert native.recipe()==corrected_spec(family,scale,variant,seed,vehicle,attempt).recipe()
    assert spec_from_recipe(native.recipe()).configuration_id==native.configuration_id
    assert len(native.inventory)==count and native.target_lap_length_m==target
    assert sum(r.build().length_m for r in native.inventory)/target>=native.minimum_primary_coverage
    if family=='hairpin':
        assert native.topology_family=='unequal_folded_lanes'
        assert all(3<=r.parameters['radius_m']<=6 for r in native.inventory)
        assert all(r.parameters['turn_angle_rad']==math.pi for r in native.inventory)
        assert all(a.parameters['direction']!=b.parameters['direction'] for a,b in zip(native.inventory,native.inventory[1:]))
    else:
        assert native.minimum_primary_coverage==.6 and native.maximum_supporting_fraction==.4
        assert {r.family for r in native.inventory}=={'straight','corner','chicane','sweeper'}
        assert sum(r.name=='extra_chicane' for r in native.inventory)==1


def test_v2_fallback_excludes_rejected_clusters_and_bounds_each_seed(vehicle):
    dataset=default_dataset_spec(design_version='research_design.v2')
    slot=next(s for s in dataset.slots if s.family=='hairpin' and s.scale=='long')
    attempts=[candidate_spec(dataset,slot,a,vehicle) for a in range(1,25)]
    from collections import Counter
    assert Counter(len(s.inventory) for s in attempts)=={13:8,15:8,17:8}
    assert all(s.candidate_budget==1 and len(s.topologies)==1 for s in attempts)
    assert all(s.topology_family=='unequal_folded_lanes' for s in attempts)
    assert len({s.configuration_id for s in attempts})==24
    assert all(s.parent_lineage==slot.parent_lineage for s in attempts)


@pytest.mark.parametrize('complexity',[2,3,4,5])
@pytest.mark.parametrize('scale',['short','medium','long'])
def test_reliability_halfturn_budget_and_native_contract(complexity,scale,vehicle):
    from map_editor.services.research_reliable_design import reliable_spec
    for variant in range(4):
        spec=reliable_spec('composite',scale,variant,73000+variant,vehicle,complexity=complexity)
        curves=[r.build() for r in spec.inventory]
        assert spec.assembly_method=='controlled_halfturn.v1'
        assert abs(sum(c.at(c.length_m).heading for c in curves)-math.pi)<1e-8
        assert abs(2*(sum(c.length_m for c in curves)+len(curves)*spec.support_gap_m)-spec.target_lap_length_m)<1e-8
        assert len({r.family for r in spec.inventory})==complexity
        assert spec.minimum_primary_coverage==.6 and spec.maximum_supporting_fraction==.4
        assert spec.minimum_family_exposure==.025 and spec.maximum_family_exposure==.78
        assert spec_from_recipe(spec.recipe()).configuration_id==spec.configuration_id
        assert all(3<=r.parameters['radius_m']<=6 for r in spec.inventory if r.family=='hairpin')
        assert spec.recipe()==reliable_spec('composite',scale,variant,73000+variant,vehicle,complexity=complexity).recipe()


@pytest.mark.parametrize('family',['chicane','s_curve'])
@pytest.mark.parametrize('scale',['short','medium','long'])
def test_reliability_opposing_physical_ranges_and_support_budget(family,scale,vehicle):
    from map_editor.services.research_reliable_design import reliable_spec
    for variant in range(4):
        spec=reliable_spec(family,scale,variant,74000+variant,vehicle)
        source=sum(r.build().length_m for r in spec.inventory)
        support=sum(t.radius_m*math.radians(t.angle_bounds_deg[0])+t.transition_m for t in spec.topologies[0].turns)
        assert source/spec.target_lap_length_m>=.5
        assert source+support+.3*len(spec.inventory)<spec.target_lap_length_m
        assert abs(sum(t.angle_bounds_deg[0] for t in spec.topologies[0].turns)-360)<1e-7
        for r in spec.inventory:
            p=r.parameters
            if family=='chicane':
                assert 2<=p['radius_m']<=5 and 1.5<=p['lateral_displacement_m']<=4
                assert p['separation_m']==.25
            else:
                assert all(3<=v<=8 for v in p['radii_m'])
                assert math.radians(45)<=p['turn_angle_rad']<=math.radians(90)
        assert spec.limits.maximum_curvature_rate_inv_m2==2.
        assert spec.limits.minimum_usable_width_m==.7


@pytest.mark.parametrize('family,scale',[('straight','short'),('straight','medium'),('straight','long'),('sweeper','short')])
def test_reliability_previously_flagged_specialists_have_independent_extremes(family,scale,vehicle):
    from map_editor.services.research_reliable_design import reliable_spec
    prepared=[prepare_research(reliable_spec(family,scale,v,75000+v,vehicle)) for v in (0,3)]
    shapes=[normalized_shape([(p.x,p.y) for p in q.sampled.states[:-1]]) for q in prepared]
    metrics=pair_metrics(prepared[0].statistics,prepared[1].statistics,*shapes)
    assert classify_pair(metrics,default_dataset_spec().policy)=='independent_under_policy'


@pytest.mark.parametrize('scale,complexity',[('medium',4),('medium',5),('long',5)])
def test_final_v2_promoted_asymmetric_profiles_have_distinct_physical_inventory(scale,complexity,vehicle):
    from map_editor.services.research_reliable_design import irregular_composite_spec,IRREGULAR_VARIANTS
    from map_editor.services.specialist_templates import canonical_hash
    profiles=IRREGULAR_VARIANTS[(scale,complexity)]
    assert len(profiles)==2
    inventory_ids=[]
    for variant in profiles:
        spec=irregular_composite_spec(scale,complexity,variant,85000,vehicle)
        assert spec.recipe()==irregular_composite_spec(scale,complexity,variant,85000,vehicle).recipe()
        assert spec_from_recipe(spec.recipe()).configuration_id==spec.configuration_id
        assert spec.assembly_method=='bounded_supporting_turns.v1' and spec.candidate_budget==1
        assert spec.minimum_primary_coverage==.6 and spec.maximum_supporting_fraction==.4
        assert len({r.family for r in spec.inventory})==spec.expected_primary_families==complexity
        curves=[r.build() for r in spec.inventory]
        assert abs(sum(c.at(c.length_m).heading for c in curves)-math.tau)<1e-8
        assert sum(c.length_m for c in curves)/spec.target_lap_length_m>=.6
        assert sum(r.build().length_m for r in spec.inventory if r.family=='straight')/spec.target_lap_length_m<=.30
        for r in spec.inventory:
            p=r.parameters
            if r.family=='hairpin':
                assert 3<=p['radius_m']<=6 and math.radians(160)<=p['turn_angle_rad']<=math.radians(190)
            elif r.family=='sweeper':
                assert 6<=p['radius_m']<=15 and math.radians(45)<=p['turn_angle_rad']<=math.radians(120)
            elif r.family=='s_curve':assert all(3<=radius<=8 for radius in p['radii_m'])
            elif r.family=='chicane':assert 2<=p['radius_m']<=5 and 1.5<=p['lateral_displacement_m']<=4
        inventory_ids.append(canonical_hash([dict(family=r.family,parameters=r.parameters) for r in spec.inventory]))
    assert len(set(inventory_ids))==2


def test_final_v2_allocation_selects_only_promoted_problem_profiles(vehicle):
    from map_editor.services.research_reliable_design import IRREGULAR_VARIANTS,irregular_composite_spec
    dataset=default_dataset_spec(design_version='research_design.v2')
    seen=set()
    for slot in dataset.slots:
        if slot.generation_mode!='composite' or (slot.scale,slot.complexity) not in IRREGULAR_VARIANTS:continue
        seen.add((slot.scale,slot.complexity));profiles=IRREGULAR_VARIANTS[(slot.scale,slot.complexity)]
        for attempt in (1,2,3):
            native=candidate_spec(dataset,slot,attempt,vehicle)
            profile=profiles[(slot.design_seed+attempt-1)%len(profiles)]
            expected=irregular_composite_spec(slot.scale,slot.complexity,profile,candidate_seed(dataset,slot,attempt),vehicle,attempt)
            assert native.inventory==expected.inventory and native.topology_family==expected.topology_family
            assert native.split==slot.split and native.parent_lineage==slot.parent_lineage
    assert seen==set(IRREGULAR_VARIANTS)


def test_final_v2_unpromoted_five_family_profile_declares_its_actual_complexity(vehicle):
    from map_editor.services.research_reliable_design import irregular_composite_spec,IRREGULAR_VARIANTS
    spec=irregular_composite_spec('medium',5,1,85001,vehicle)
    assert len({r.family for r in spec.inventory})==spec.expected_primary_families==5
    assert 1 not in IRREGULAR_VARIANTS[('medium',5)]
