"""Specialist intent, exact templates, measurable exposure, bounded pilots and replay."""
from copy import deepcopy
from dataclasses import replace
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import numpy as np
import pytest

from map_editor.geometry import GeometryError
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.parametric_track import ParametricTrackSpec, prepare_parametric_track
from map_editor.services.specialist_templates import (
    GENERATOR_VERSION, FAMILIES, SpecialistSpec, build_template, default_ranges,
    load_specialist_spec, sample_spec, vehicle_kinematic_radius,
)
from map_editor.services.specialist_tracks import (
    generate_specialist_bundle, prepare_specialist, validate_specialist_metadata,
)
from map_editor.services import specialist_tracks
from map_editor.services.specialist_pilot import (
    CandidateRequest, default_pilot_requests, generate_pilot, load_pilot_recipe,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def vehicle():
    return VehicleProfile(.5, .27, .15875, .17145, -.523599, .523599, -3.2, 3.2,
                          "combined_slip.yaml", "fb8bab7a7c49cb913c6adafbec84d4560e02d927087ff61956be0145f6288016", "uncalibrated")


@pytest.fixture(scope="module")
def prepared(vehicle):
    return {family: prepare_specialist(SpecialistSpec(family, vehicle)) for family in FAMILIES}


@pytest.mark.parametrize("family", FAMILIES)
def test_specialist_intent_is_independent_of_composition(family, prepared):
    result = prepared[family]
    metadata = result.metadata
    assert metadata["schema_version"] == "1.0.0"
    assert metadata["generator_version"] == GENERATOR_VERSION
    assert metadata["generation_mode"] == "specialist"
    assert len(result.statistics["maneuver_counts"]) >= 2
    assert metadata["requested"]["target_family"] == family
    assert metadata["difficulty"]["label"] == "unrated"
    assert metadata["split"] == "unspecified"
    assert result.statistics["target_exposure_fraction"] >= metadata["requested"]["minimum_target_exposure_fraction"]
    assert abs(sum(result.statistics["family_exposure_fractions"].values())-1) < 1e-12
    validate_specialist_metadata(metadata)


@pytest.mark.parametrize("family", FAMILIES)
def test_clockwise_reverses_same_layout_and_preserves_features(family, prepared, vehicle):
    forward = prepared[family]
    reverse = prepare_specialist(SpecialistSpec(family, vehicle, clockwise=True))
    a = np.array([(p.x, p.y) for p in forward.sampled.states])
    b = np.array([(p.x, p.y) for p in reverse.sampled.states])
    assert a.shape == b.shape
    assert np.allclose(a, b[::-1], atol=1.1e-6)
    assert reverse.statistics["target_exposure_fraction"] == pytest.approx(forward.statistics["target_exposure_fraction"], abs=1e-8)
    assert reverse.statistics["directional_balance"]["signed_heading_change_rad"] == pytest.approx(-math.tau)
    assert forward.statistics["directional_balance"]["signed_heading_change_rad"] == pytest.approx(math.tau)
    assert reverse.metadata["provenance"]["validation"]["exported_raster_footprint"]["status"] == "passed_at_sampled_poses"


@pytest.mark.parametrize("family", FAMILIES)
def test_default_ranges_are_seeded_and_vehicle_based(family, vehicle):
    base = SpecialistSpec(family, vehicle)
    ranges = default_ranges(family, vehicle)
    first = sample_spec(base, ranges, 123)
    assert first == sample_spec(base, dict(reversed(list(ranges.items()))), 123)
    assert first != sample_spec(base, ranges, 124)
    assert vehicle_kinematic_radius(vehicle) == pytest.approx(.597069, abs=1e-6)
    assert base.parameters["connector_radius_m"] > 4*vehicle_kinematic_radius(vehicle)
    assert base.parameters["track_width_m"] > vehicle.width_m + .04


def test_identity_provenance_and_lineage_are_stable(vehicle):
    first = SpecialistSpec("hairpin", vehicle)
    assert first.track_id == SpecialistSpec("hairpin", vehicle).track_id
    sibling = replace(first, seed=43, variant_number=2, clockwise=True)
    assert sibling.track_id != first.track_id
    assert sibling.shape_id == first.shape_id
    assert sibling.lineage_id == first.lineage_id
    changed = replace(first, parameters=dict(first.parameters, turn_radius_m=4))
    assert changed.shape_id != first.shape_id
    assert changed.lineage_id == first.lineage_id
    changed_vehicle = replace(first, vehicle=replace(vehicle, source_sha256="f"*64))
    assert changed_vehicle.configuration_id != first.configuration_id
    assert len(first.configuration_id) == 64


@pytest.mark.parametrize("changes", [dict(seed=-1), dict(seed=True), dict(variant_number=0),
    dict(experimental_mode="composite"), dict(minimum_target_exposure=.49), dict(minimum_target_exposure=1.01),
    dict(template_revision="future.v2"), dict(clockwise="yes"), dict(parent_lineage=""),
    dict(parameters={"unrecognized": 1}), dict(parameters={"track_width_m": float("nan")}),
    dict(parameters={"repetitions": 2.5})])
def test_invalid_intent_and_parameters_reject(vehicle, changes):
    with pytest.raises(GeometryError):
        SpecialistSpec("chicane", vehicle, **changes)


def test_turn_angle_and_overdetermined_length_are_not_distorted(vehicle):
    spec = SpecialistSpec("hairpin", vehicle, parameters={"turn_angle_rad": math.radians(165), "connector_transition_m": .5})
    result = prepare_specialist(spec)
    targets = [a for a in result.metadata["maneuvers"] if a["requested"]["template_role"] == "target"]
    assert all(abs(a["measured"]["signed_heading_change_rad"]) == pytest.approx(math.radians(165)) for a in targets)
    assert all(a["measured"]["minimum_radius_m"] == 3 for a in targets)
    assert any(a["requested"]["template_role"] == "heading_connector" for a in result.metadata["maneuvers"])
    with pytest.raises(GeometryError, match="conflicts"):
        prepare_specialist(replace(spec, parameters=dict(spec.parameters, maneuver_length_m=1)))
    with pytest.raises(GeometryError, match="too small"):
        prepare_specialist(replace(spec, parameters=dict(spec.parameters, turn_angle_rad=math.pi-.01)))


def test_exposure_and_support_metrics_are_validated(prepared, vehicle):
    metadata = prepared["straight"].metadata
    stats = metadata["provenance"]["specialist_statistics"]
    assert stats["continuous_straight_runs_m"]["values"] == pytest.approx([32., 32.])
    assert stats["straight_before_turn_lengths_m"]["values"] == pytest.approx([32., 32.])
    assert len(stats["annotated_straight_lengths_m"]["values"]) == 6
    assert stats["embedded_transition_physical_length_m"] == 4
    for key in ["target_exposure_fraction", "supporting"]:
        bad = deepcopy(metadata)
        if key == "target_exposure_fraction":
            bad["provenance"]["specialist_statistics"][key] += .1
        else:
            bad["provenance"]["specialist_statistics"]["family_exposure_fractions"]["hairpin"] += .1
        with pytest.raises(GeometryError):
            validate_specialist_metadata(bad)
    with pytest.raises(GeometryError, match="Target exposure"):
        prepare_specialist(SpecialistSpec("straight", vehicle, minimum_target_exposure=.99))


def test_bundle_recipe_metadata_csv_partition_and_safe_replay(tmp_path, vehicle):
    spec = SpecialistSpec("hairpin", vehicle)
    path = generate_specialist_bundle(spec, tmp_path/"first")
    loaded = load_specialist_spec(path.with_name(f"{spec.track_id}_generation.yaml"))
    assert loaded == spec
    second = generate_specialist_bundle(loaded, tmp_path/"second")
    for artifact in path.parent.iterdir():
        assert artifact.read_bytes() == (second.parent/artifact.name).read_bytes()
    report = json.loads(path.with_name(f"{spec.track_id}_validation.json").read_text())
    assert report["recipe_replay"] == {"status": "passed", "artifacts_compared": 9, "byte_identical": True}
    assert report["integration"]["status"] == "not_run"
    assert report["physical_drivability"] == "unassessed"
    metadata = json.loads(path.with_name(f"{spec.track_id}_metadata.json").read_text())
    points = np.loadtxt(path.with_name(f"{spec.track_id}_centerline.csv"), delimiter=",", skiprows=1, usecols=(0, 1))
    distances = np.r_[0., np.cumsum(np.linalg.norm(np.roll(points, -1, axis=0)-points, axis=1))]
    assert metadata["measured"]["length_m"] == pytest.approx(distances[-1], abs=1e-10)
    assert sum(a["length_m"] for a in metadata["maneuvers"]) == pytest.approx(distances[-1], abs=1e-10)
    assert metadata["maneuvers"][-1]["wraps_seam"]
    assert metadata["maneuvers"][-1]["s_end_m"] == 0
    for key, digest in report["artifact_sha256"].items():
        assert hashlib.sha256((path.parent/metadata["artifacts"][key]).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        generate_specialist_bundle(spec, path.parent)
    with pytest.raises(GeometryError):
        generate_specialist_bundle(replace(spec, minimum_target_exposure=1.), tmp_path/"invalid")
    assert not (tmp_path/"invalid").exists()


def _stub_reference(tmp_path, monkeypatch):
    reference = tmp_path/"reference"
    (reference/"src/utils").mkdir(parents=True)
    (reference/"src/utils/map_loader.py").write_text("# unit-test presence stub\n")
    monkeypatch.setattr(specialist_tracks, "consumer_smoke", lambda path, root: {"status": "passed", "checks": {"unit_stub": True}})
    return reference


def test_bounded_real_geometry_retries_and_deterministic_collection(tmp_path, monkeypatch, vehicle):
    reference = _stub_reference(tmp_path, monkeypatch)
    base = SpecialistSpec("straight", vehicle)
    ranges = {"maneuver_length_m": [3., 45.]}
    chosen = None
    for seed in range(50):
        rng = random.Random(seed)
        a, b = [sample_spec(base, ranges, rng.getrandbits(63)).parameters["maneuver_length_m"] for _ in range(2)]
        if a < 20 and b > 27:
            chosen = seed
            break
    assert chosen is not None
    request = (CandidateRequest(base, ranges),)
    first = generate_pilot(request, tmp_path/"a", seed=chosen, max_attempts=2, reference=reference)
    assert first["complete"] and len(first["accepted"]) == len(first["rejected"]) == 1
    assert "Target exposure" in first["rejected"][0]["reason"]
    second = generate_pilot(request, tmp_path/"b", seed=chosen, max_attempts=2, reference=reference)
    assert first == second
    loaded, seed, budget = load_pilot_recipe(tmp_path/"a/pilot_recipe.json")
    assert loaded == request and seed == chosen and budget == 2
    with pytest.raises(FileExistsError):
        generate_pilot(request, tmp_path/"a", reference=reference)


def test_incomplete_pilot_never_relaxes_threshold_and_rejects_duplicate_geometry(tmp_path, monkeypatch, vehicle):
    reference = _stub_reference(tmp_path, monkeypatch)
    impossible = SpecialistSpec("straight", vehicle, minimum_target_exposure=1.)
    report = generate_pilot((CandidateRequest(impossible, {}),), tmp_path/"partial", reference=reference, max_attempts=2)
    assert not report["complete"] and not report["accepted"] and len(report["rejected"]) == 2
    assert report["incomplete_requests"][0]["exhausted_attempts"] == 2
    assert all(r["sampled_recipe"]["minimum_target_exposure"] == 1 for r in report["rejected"])
    base = SpecialistSpec("straight", vehicle)
    duplicate = generate_pilot((CandidateRequest(base, {}), CandidateRequest(replace(base, variant_number=2, clockwise=True), {})),
                              tmp_path/"duplicate", reference=reference, max_attempts=1)
    assert not duplicate["complete"] and len(duplicate["accepted"]) == 1
    assert "Duplicate geometry" in duplicate["rejected"][0]["reason"]


def test_phase1_original_generator_and_artifact_bytes_are_unchanged(tmp_path, vehicle):
    maneuvers, _, frame = build_template(SpecialistSpec("straight", vehicle))
    _, _, old_metadata, _ = prepare_parametric_track(ParametricTrackSpec("old", maneuvers, frame=frame))
    assert old_metadata["generation_mode"] == "composite"
    golden = ROOT/"examples/phase1/closed_stadium"
    result = subprocess.run([sys.executable, str(ROOT/"scripts/generate_parametric.py"),
                             str(golden/"closed_stadium_generation.yaml"), "--output", str(tmp_path/"replay")],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    metadata = json.loads((golden/"closed_stadium_metadata.json").read_text())
    for artifact in metadata["artifacts"].values():
        assert (golden/artifact).read_bytes() == (tmp_path/"replay"/artifact).read_bytes()


def test_pilot_requests_are_exactly_two_meaningful_variants_per_family(vehicle):
    requests = default_pilot_requests(vehicle)
    assert len(requests) == 10
    assert {(r.base.target_family, r.base.variant_number) for r in requests} == {(family, variant) for family in FAMILIES for variant in (1, 2)}
    assert len({r.base.track_id for r in requests}) == 10


@pytest.mark.parametrize("family", FAMILIES)
def test_pilot_assets_actual_integration_evidence_and_golden_replay(family, tmp_path):
    root = ROOT/"examples/phase2_pilot"
    manifest = json.loads((root/"manifest.json").read_text())
    assert manifest["complete"] and len(manifest["accepted"]) == 10
    entries = [e for e in manifest["accepted"] if e["family"] == family]
    assert len(entries) == 2
    code = ("from pathlib import Path; import sys; sys.path.insert(0, sys.argv[3]); "
            "from map_editor.services.specialist_templates import load_specialist_spec; "
            "from map_editor.services.specialist_tracks import generate_specialist_bundle; "
            "generate_specialist_bundle(load_specialist_spec(Path(sys.argv[1])), Path(sys.argv[2]), verify_replay=False)")
    for entry in entries:
        metadata = json.loads((root/entry["metadata"]).read_text())
        validate_specialist_metadata(metadata)
        report = json.loads((root/entry["validation_report"]).read_text())
        assert report["integration"]["status"] == "passed"
        assert len(report["integration"]["reference_revision"]) == 40
        assert report["integration"]["checks"]["named_spawns"] == ["grid_1"]
        assert report["integration"]["checks"]["finish_crossings"] == {"forward": True, "reverse": False, "beyond_endpoint": False}
        assert report["recipe_replay"]["byte_identical"]
        replay = tmp_path/entry["track_id"]
        result = subprocess.run([sys.executable, "-c", code, str(root/entry["recipe"]), str(replay), str(ROOT/"src")],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        for artifact in metadata["artifacts"].values():
            assert ((root/entry["map"]).parent/artifact).read_bytes() == (replay/artifact).read_bytes(), artifact
        for key, digest in report["artifact_sha256"].items():
            assert hashlib.sha256(((root/entry["map"]).parent/metadata["artifacts"][key]).read_bytes()).hexdigest() == digest
