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
