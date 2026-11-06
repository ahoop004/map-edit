"""Composite closure, composition, periodic evaluation, identity and native replay."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import random
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from map_editor.geometry import GeometryError
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.composite_spec import (
    CompositeSpec,ManeuverRequest,ConnectorConstraints,load_composite_spec,sample_composite_spec,
)
from map_editor.services.composite_assembly import assembly_candidates
from map_editor.services.composite_tracks import (
    CompositeGenerationError,prepare_composite,generate_composite_bundle,validate_composite_metadata,
)
from map_editor.services.composite_statistics import contains,evaluation_rows,interval
from map_editor.services.composite_pilot import (
    CompositePilotRequest,default_composite_requests,generate_composite_pilot,load_composite_pilot,
)
from map_editor.services import composite_tracks, procedural_track

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def vehicle():
    return VehicleProfile(.5,.27,.15875,.17145,-.523599,.523599,-3.2,3.2,"combined_slip.yaml",
                          "fb8bab7a7c49cb913c6adafbec84d4560e02d927087ff61956be0145f6288016","uncalibrated")


@pytest.fixture(scope="module")
def requests(vehicle):
    return default_composite_requests(vehicle)


@pytest.fixture(scope="module")
def prepared(requests):
    return {i:prepare_composite(request.base) for i,request in enumerate(requests)}


@pytest.mark.parametrize("index",range(8))
def test_requested_inventory_and_symmetric_asymmetric_closure(index,requests,prepared):
    spec=requests[index].base
    result=prepared[index]
    assert result.metadata["generation_mode"]=="composite"
    assert result.metadata["schema_version"]=="1.0.0"
    assert result.statistics["primary_distinct_families"]==requests[index].expected_primary_families
    assert set(result.statistics["maneuver_counts"])==set(spec.required_families)
    expected_repeats=spec.symmetry_order if spec.layout=="symmetric" else 1
    for item in result.assembly.items:
        if item.role=="primary":
            original=spec.inventory[item.inventory_index].build()
            assert item.maneuver.length_m==pytest.approx(original.length_m)
            assert abs(sum((s.k_start+s.k_end)*s.length_m/2 for s in item.maneuver.segments))==pytest.approx(
                abs(original.at(original.length_m).heading))
    assert sum(result.statistics["maneuver_counts"].values())==sum(r.family!="transition" for r in spec.inventory)*expected_repeats
    assert result.metadata["difficulty"]["label"]=="unrated"
    assert result.metadata["split"]=="unspecified"
    assert result.metadata["provenance"]["validation"]["exported_raster_footprint"]["status"]=="passed_at_sampled_poses"
    residual=result.metadata["provenance"]["identity"]["measured_halfturn_symmetry_error_m"]
    assert residual<1e-3 if spec.layout=="symmetric" else residual>1e-3
    validate_composite_metadata(result.metadata)


def test_exact_cyclic_transition_and_connector_accounting(prepared):
    result=prepared[4]
    stats=result.statistics
    windows=result.metadata["maneuvers"]
    assert len(stats["transition_count_matrix"])==6
    assert sum(sum(row.values()) for row in stats["transition_count_matrix"].values())==len(windows)
    assert sum(sum(row.values()) for row in stats["projected_primary_order_matrix"].values())==sum(stats["maneuver_counts"].values())
    assert stats["boundary_events"][-1]["to_id"]==stats["ordered_maneuver_ids"][0]
    assert any(bridge["connector_ids"] for bridge in stats["projected_primary_bridges"])
    assert sum(stats["family_exposure_fractions"].values())==pytest.approx(1)
    assert stats["primary_total_exposure"]+stats["supporting_geometry_exposure"]==pytest.approx(1)
    assert all(abs(event["curvature_jump_inv_m"])<1e-8 for event in stats["boundary_events"])
    assert any(not e["annotation_label_changed"] for e in stats["boundary_events"])
    assert stats["physical_demand_change_count"]!=stats["annotation_boundary_count"]
    assert sum(e["distance_to_next_primary_switch_m"] for e in stats["primary_switch_events"])==pytest.approx(stats["length_m"])


def test_internal_chicane_straight_is_visible_not_added_to_family_exposure(prepared):
    result=prepared[0]
    chicane=next(a for a in result.metadata["maneuvers"] if a["type"]=="chicane")
    children=result.statistics["internal_driving_regions"][chicane["id"]]
    assert any(r["driving_demand"]=="straight" and r["length_m"]>1.9 for r in children)
    assert sum(r["length_m"] for r in children)==pytest.approx(chicane["length_m"])
    assert result.statistics["active_curvature_exposure_by_family"]["chicane"]<result.statistics["family_exposure_fractions"]["chicane"]


def test_periodic_seam_and_evaluation_metadata_are_unambiguous(prepared,requests):
    result=prepared[1]
    metadata=result.metadata
    windows=metadata["maneuvers"]
    wrapping=next(a for a in windows if a["wraps_seam"] and a["s_end_m"]>0)
    assert contains(wrapping,0)
    evaluator=evaluation_rows(metadata)
    assert evaluator(0)["distance_to_next_maneuver_boundary_m"]==pytest.approx(wrapping["s_end_m"])
    for window in windows:
        at_entry=evaluator(window["s_start_m"]+1e-12)
        assert at_entry["maneuver_id"]==window["id"]
    assert len({evaluator(row["s_m"])["maneuver_id"] for row in result.geometry.profile})==len(windows)
    assert metadata["provenance"]["evaluation_metadata_only"]
    assert not metadata["provenance"]["policy_observations_changed"]
    full=interval(3,10,10)
    assert full["wraps_seam"] and full["s_start_m"]==full["s_end_m"]==3
    near_end=prepare_composite(replace(requests[0].base,seam_offset_m=prepared[0].sampled.length_m-.01))
    assert near_end.metadata["provenance"]["lap_seam"]["actual_curve_offset_m"]==0


def test_selector_estimates_require_explicit_assumptions(requests,prepared):
    analysis=prepared[0].statistics["selector_window_analysis"]
    assert analysis["selection_intervals_steps"]==[5,10,20]
    assert analysis["default_selection_steps"]==10
    assert analysis["speed_assumption_m_s"]==2
    assert analysis["environment_step_s"]==.05
    first=prepared[0].metadata["maneuvers"][0]
    assert analysis["window_estimates"][first["id"]]["traversal_time_s"]==pytest.approx(first["length_m"]/2)
    unassumed=prepare_composite(replace(requests[0].base,speed_assumption_m_s=None,environment_step_s=None))
    assert unassumed.statistics["selector_window_analysis"]["status"]=="not_estimated"
    assert "window_estimates" not in unassumed.statistics["selector_window_analysis"]
    assert unassumed.metadata["provenance"]["validation"]["feasibility_advisory"]["status"]=="not_requested"


def test_matched_ordering_preserves_inventory_but_changes_geometry(prepared):
    first,second=prepared[6],prepared[7]
    a,b=first.metadata["provenance"]["identity"],second.metadata["provenance"]["identity"]
    assert a["inventory_multiset_sha256"]==b["inventory_multiset_sha256"]
    assert a["parent_lineage_id"]==b["parent_lineage_id"]
    assert a["ordered_inventory_sha256"]!=b["ordered_inventory_sha256"]
    assert a["geometry_fingerprint"]!=b["geometry_fingerprint"]
    assert first.statistics["maneuver_counts"]==second.statistics["maneuver_counts"]
    assert first.statistics["family_exposure_fractions"]==pytest.approx(second.statistics["family_exposure_fractions"],abs=1e-7)
    assert first.statistics["ordered_primary_families"]!=second.statistics["ordered_primary_families"]


@pytest.mark.parametrize("change",[{"seam_offset_m":8.},{"clockwise":True},{"mirrored":True},{"mirrored":True,"clockwise":True}])
def test_geometry_identity_ignores_seam_reflection_and_traversal(change,requests,prepared):
    other=prepare_composite(replace(requests[0].base,**change))
    identity=other.metadata["provenance"]["identity"]
    assert identity["geometry_fingerprint"]==prepared[0].metadata["provenance"]["identity"]["geometry_fingerprint"]
    expected=-math.tau if change.get("clockwise",False) else math.tau
    assert other.statistics["directional_balance"]["signed_heading_change_rad"]==pytest.approx(expected)


def test_cyclic_inventory_rotation_is_not_an_independent_closed_layout(requests):
    base=replace(requests[4].base,approach_length_m=0.,gap_length_m=0.,seam_offset_m=0.)
    rotated=replace(base,inventory=base.inventory[1:]+base.inventory[:1])
    first,second=prepare_composite(base),prepare_composite(rotated)
    assert first.metadata["provenance"]["identity"]["geometry_fingerprint"]==second.metadata["provenance"]["identity"]["geometry_fingerprint"]


def test_ranges_and_order_generation_are_deterministic(requests):
    base=requests[0].base
    first=replace(base.inventory[0],ranges={"length_m":[14.,18.]})
    ranged=replace(base,inventory=(first,base.inventory[1]),allowed_orders=((0,1),(1,0)))
    a=sample_composite_spec(ranged,42)
    assert a==sample_composite_spec(ranged,42)
    assert a!=sample_composite_spec(ranged,43)
    assert 14<=next(r.parameters["length_m"] for r in a.inventory if r.family=="straight")<=18
    s=ManeuverRequest("s","s_curve",{"radii_m":[4,5]},ranges={"radii_m.0":[4.,4.5]})
    updated=sample_composite_spec(replace(base,inventory=(base.inventory[0],s),required_families=()),99)
    assert 4<=updated.inventory[1].parameters["radii_m"][0]<=4.5


@pytest.mark.parametrize("changes",[dict(generation_mode="specialist"),dict(layout="optimizer"),dict(seed=-1),
    dict(clockwise="yes"),dict(minimum_useful_length_m=0),dict(speed_assumption_m_s=0),dict(default_selection_steps=7),
    dict(exposure_bounds={"unknown":[0,1]}),dict(exposure_bounds={"straight":[.8,1],"chicane":[.8,1]}),
    dict(transition_count_range=[5,2]),dict(required_families=("hairpin",)),dict(allowed_orders=((0,0),))])
def test_invalid_specifications_reject(changes,requests):
    with pytest.raises(GeometryError):
        replace(requests[0].base,**changes)


def test_bounded_asymmetric_failure_and_wrong_classification_are_explicit(requests):
    bad=replace(requests[1].base,connectors=ConnectorConstraints(straight_range_m=(0,.25),solver_budget=4))
    with pytest.raises(CompositeGenerationError) as error:
        prepare_composite(bad)
    assert len(error.value.attempts)==4
    assert all(a["status"]=="rejected" for a in error.value.attempts)
    assert "bounded" in str(error.value)
    wrong=ManeuverRequest("wrong_hairpin","hairpin",dict(radius_m=8,turn_angle_rad=math.pi/2))
    spec=replace(requests[0].base,inventory=(requests[0].base.inventory[0],wrong),required_families=())
    with pytest.raises(CompositeGenerationError,match="heading-reversal"):
        prepare_composite(spec)
    with pytest.raises(CompositeGenerationError,match="Exposure"):
        prepare_composite(replace(requests[0].base,exposure_bounds={"straight":[.99,1]}))
    with pytest.raises(CompositeGenerationError,match="Exposure"):
        prepare_composite(replace(requests[0].base,exposure_bounds={"chicane":[0,.01]}))


def test_connectors_do_not_mutate_requested_primary_geometry(requests):
    base=replace(requests[1].base,clockwise=False)
    journal=[]
    assembly=next(assembly_candidates(base,journal))
    for item in assembly.items:
        if item.role=="primary":
            original=base.inventory[item.inventory_index].build()
            assert item.maneuver==original
            assert not item.adjustable
        elif item.adjustable:
            assert item.role.startswith("return_")
    assert assembly.solution["straight_lengths_m"]


def test_native_bundle_replay_and_ordinary_csv_schema(tmp_path,requests,monkeypatch):
    monkeypatch.setattr(procedural_track,"_sample_closed_bspline",lambda *a,**k:pytest.fail("Composite passed through old fitter"))
    spec=requests[0].base
    path=generate_composite_bundle(spec,tmp_path/"first")
    loaded=load_composite_spec(path.with_name(f"{spec.track_id}_generation.yaml"))
    assert loaded==spec
    second=generate_composite_bundle(loaded,tmp_path/"second")
    for asset in path.parent.iterdir():
        assert asset.read_bytes()==(second.parent/asset.name).read_bytes(),asset.name
    report=json.loads(path.with_name(f"{spec.track_id}_validation.json").read_text())
    assert report["recipe_replay"]["artifacts_compared"]==10
    assert report["physical_drivability"]=="unassessed"
    assert path.with_name(f"{spec.track_id}_centerline.csv").read_text().splitlines()[0]=="x,y,theta,velocity"
    assert "maneuver_id" in path.with_name(f"{spec.track_id}_evaluation.csv").read_text().splitlines()[0]
    with pytest.raises(FileExistsError):
        generate_composite_bundle(spec,path.parent)


def test_metadata_integrity_checks_reject_tampering(prepared):
    bad=deepcopy(prepared[0].metadata)
    bad["provenance"]["composite_statistics"]["family_exposure_fractions"]["straight"]+=.1
    with pytest.raises(GeometryError):
        validate_composite_metadata(bad)
    bad=deepcopy(prepared[0].metadata)
    bad["provenance"]["composite_statistics"]["transition_count_matrix"]["connector"]["connector"]+=1
    with pytest.raises(GeometryError):
        validate_composite_metadata(bad)


def _reference(tmp_path,monkeypatch):
    reference=tmp_path/"reference"
    (reference/"src/utils").mkdir(parents=True)
    (reference/"src/utils/map_loader.py").write_text("# controlled unit-test presence marker\n")
    monkeypatch.setattr(composite_tracks,"consumer_smoke",lambda *a:{"status":"passed","checks":{"unit_stub":True}})
    return reference


def test_partial_manifest_rejections_overwrite_and_duplicate_handling(tmp_path,requests,monkeypatch):
    reference=_reference(tmp_path,monkeypatch)
    bad=replace(requests[1].base,connectors=ConnectorConstraints(straight_range_m=(0,.25),solver_budget=2))
    report=generate_composite_pilot((CompositePilotRequest("failed",2,bad),),tmp_path/"partial",reference=reference,max_attempts=2)
    assert not report["complete"] and not report["accepted"] and len(report["rejected"])==2
    assert all(len(r["closure_attempts"])==2 for r in report["rejected"])
    with pytest.raises(FileExistsError):
        generate_composite_pilot((),tmp_path/"partial",reference=reference)
    original=requests[0]
    duplicate=CompositePilotRequest(original.category,2,replace(original.base,variant="only_seam_changed",seam_offset_m=9))
    result=generate_composite_pilot((original,duplicate),tmp_path/"duplicate",reference=reference,max_attempts=1)
    assert len(result["accepted"])==1 and not result["complete"]
    assert "cyclic-equivalent" in result["rejected"][0]["reason"]


def test_endpoint_curvature_rate_changes_are_measured_without_claiming_g3(requests):
    base=requests[0].base
    ramp=ManeuverRequest("linear_ramp","transition",dict(length_m=2,k_start_inv_m=0,k_end_inv_m=.1,ramp="linear"))
    spec=replace(base,inventory=(base.inventory[0],ramp,base.inventory[1]),required_families=())
    result=prepare_composite(spec)
    events=result.statistics["boundary_events"]
    assert any(abs(e["curvature_rate_jump_inv_m2"])>=.0499 for e in events)
    assert all(abs(e["curvature_jump_inv_m"])<1e-8 for e in events)


@pytest.mark.parametrize("index",range(8))
def test_pilot_actual_consumer_evidence_and_all_native_artifact_replay(index,tmp_path):
    root=ROOT/"examples/phase3_pilot"
    manifest=json.loads((root/"manifest.json").read_text())
    assert manifest["complete"] and len(manifest["accepted"])==8
    entry=manifest["accepted"][index]
    metadata=json.loads((root/entry["metadata"]).read_text())
    validate_composite_metadata(metadata)
    report=json.loads((root/entry["validation_report"]).read_text())
    assert report["integration"]["status"]=="passed"
    assert len(report["integration"]["reference_revision"])==40
    assert report["integration"]["checks"]["named_spawns"]==["grid_1"]
    assert report["integration"]["checks"]["finish_crossings"]=={"forward":True,"reverse":False,"beyond_endpoint":False}
    assert report["recipe_replay"]["artifacts_compared"]==10
    code=("from pathlib import Path; import sys; sys.path.insert(0,sys.argv[3]); "
          "from map_editor.services.composite_spec import load_composite_spec; "
          "from map_editor.services.composite_tracks import generate_composite_bundle; "
          "generate_composite_bundle(load_composite_spec(Path(sys.argv[1])),Path(sys.argv[2]),verify_replay=False)")
    result=subprocess.run([sys.executable,"-c",code,str(root/entry["recipe"]),str(tmp_path/"replay"),str(ROOT/"src")],
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    directory=(root/entry["map"]).parent
    for name,digest in report["artifact_sha256"].items():
        original=(directory/name).read_bytes()
        assert hashlib.sha256(original).hexdigest()==digest
        assert original==(tmp_path/"replay"/name).read_bytes(),name


def test_bounded_retry_recovers_with_new_seed_without_relaxing_connector_bounds(tmp_path,requests,monkeypatch):
    reference=_reference(tmp_path,monkeypatch)
    base=requests[0].base
    varied=replace(base.inventory[0],ranges={"length_m":[5.,25.]})
    base=replace(base,inventory=(varied,base.inventory[1]),lap_length_range_m=(78.,86.),
                 connectors=replace(base.connectors,radius_range_m=(3.5,3.5)))
    selected=None
    for seed in range(100):
        rng=random.Random(seed)
        first,second=[sample_composite_spec(base,rng.getrandbits(63)).inventory[0].parameters["length_m"] for _ in range(2)]
        if first<9 and 14<second<16:
            selected=seed
            break
    assert selected is not None
    request=CompositePilotRequest("two_families",2,base)
    report=generate_composite_pilot((request,),tmp_path/"recovered",reference=reference,seed=selected,max_attempts=2)
    assert report["complete"] and len(report["accepted"])==len(report["rejected"])==1
    assert report["accepted"][0]["attempt"]==2
    assert "Final lap length" in report["rejected"][0]["reason"]
    loaded,root_seed,budget=load_composite_pilot(tmp_path/"recovered/pilot_recipe.json")
    assert loaded[0].base==base and root_seed==selected and budget==2
    assert loaded[0].base.connectors.radius_range_m==(3.5,3.5)
