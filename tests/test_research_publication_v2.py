"""Frozen V2 release contract and fail-closed publication integration."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from map_editor.geometry import GeometryError
from map_editor.services import research_dataset
from map_editor.services.research_selection_plan import verify_plan,plan_identity
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.specialist_templates import canonical_hash

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'datasets/phase5_v2'


@pytest.fixture(scope='module')
def release():
    if not (DATA/'selection_plan.json').is_file():pytest.skip('Frozen V2 publication is not installed')
    return (json.loads((DATA/'selection_plan.json').read_text()),
        json.loads((DATA/'development/preflight_pool.json').read_text()),
        load_vehicle_snapshot(DATA/'development/vehicle_snapshot.json'))


def test_v2_release_matches_frozen_plan_and_all_pairwise_constraints(release):
    plan,pool,vehicle=release
    result=verify_plan(plan,pool,vehicle)
    assert result['selected']==60 and result['pairs']==1770
    assert result['low_repetition_composites']==28
    audit=research_dataset.audit_dataset(DATA,require_complete=True)
    assert len(audit['pairwise_comparisons'])==1770
    assert not audit['near_duplicate_pairs'] and not audit['cross_split_lineage_leaks']
    assert audit['selection_plan_verification']['preflight_differences']==[]
    assert audit['selection_plan_verification']['candidate_evidence_counts']==dict(geometry_rejected=17,valid_unselected=74)


def test_v2_tampered_selected_recipe_cannot_be_substituted(release):
    plan,pool,vehicle=release
    changed=deepcopy(plan);changed['selected'][0]['native_recipe']['seed']+=1
    changed['selected_candidates_sha256']=canonical_hash(changed['selected']);changed['plan_id']=plan_identity(changed)
    with pytest.raises(GeometryError,match='native recipe'):verify_plan(changed,pool,vehicle)


def test_completed_v2_resume_is_read_only_and_uses_archived_inputs(release,monkeypatch):
    before={str(p.relative_to(DATA)):hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.rglob('*') if p.is_file()}
    def forbidden(*args,**kwargs):raise AssertionError('Completed selected publication must not regenerate or publish')
    monkeypatch.setattr(research_dataset,'prepare_research',forbidden)
    monkeypatch.setattr(research_dataset,'publish_research',forbidden)
    result=research_dataset.publish_selected_dataset(DATA/'selection_plan.json',None,DATA,
        snapshot=DATA/'development/vehicle_snapshot.json',calibration=DATA/'development/calibration.json',resume=True)
    assert result['complete']
    assert before=={str(p.relative_to(DATA)):hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.rglob('*') if p.is_file()}
