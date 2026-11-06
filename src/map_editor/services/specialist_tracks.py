"""Specialist intent, measured exposure, safe publication and replay verification."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np

from map_editor.exporters.centerline import CenterlineSample
from map_editor.geometry import GeometryError
from map_editor.geometry.measurement import measure, position_curvatures, validate_maneuver
from map_editor.geometry.spatial import minimum_boundary_separation, self_intersects
from map_editor.geometry.validation import validate_raster_footprint
from map_editor.models.annotations import Point2D, Pose2D, SpawnPoint
from map_editor.services.geometry_metadata import validate_geometry_metadata
from map_editor.services.parametric_track import ParametricTrackSpec, periodic_interval, prepare_parametric_track
from map_editor.services.procedural_track import _rasterize_walls, export_track_geometry
from map_editor.services.specialist_templates import (
    GENERATOR_VERSION, FAMILIES, SpecialistSpec, build_template, canonical_hash, load_specialist_spec,
)
from map_editor.services.track_profile import profile_metrics
from map_editor.services.yaml_serializer import load_map_yaml, dump_map_yaml

ROOT = Path(__file__).resolve().parents[3]


def _distribution(values):
    values = [float(v) for v in values]
    return dict(values=values, count=len(values), minimum=min(values) if values else None,
                maximum=max(values) if values else None, mean=sum(values)/len(values) if values else None)


def geometry_fingerprint(points):
    vertices = [(round(p.x, 5), round(p.y, 5)) for p in points]
    def cycle(values):
        first = min(range(len(values)), key=values.__getitem__)
        return values[first:] + values[:first]
    return canonical_hash(min(cycle(vertices), cycle(list(reversed(vertices)))))


def composition_statistics(metadata, sampled, roles, target_family):
    annotations = metadata["maneuvers"]
    length = metadata["measured"]["length_m"]
    if not math.isclose(sum(a["length_m"] for a in annotations), length, rel_tol=1e-10, abs_tol=1e-8):
        raise GeometryError("Maneuver intervals must partition the entire exported lap")
    family_lengths, counts, role_lengths = defaultdict(float), Counter(), defaultdict(float)
    straight_lengths, radii = [], []
    active_target_length, zero_length, transitions = 0., 0., 0.
    before_turn = []
    for index, (a, role, (start, end), maneuver) in enumerate(zip(annotations, roles, sampled.spans, sampled.maneuvers)):
        family_lengths[a["type"]] += a["length_m"]
        role_lengths[role] += a["length_m"]
        counts[a["type"]] += 1
        if a["type"] == "straight":
            straight_lengths.append(a["length_m"])
        else:
            run = 0.
            for offset in range(1, len(annotations)):
                preceding = annotations[(index-offset) % len(annotations)]
                if preceding["type"] != "straight":
                    break
                run += preceding["length_m"]
            before_turn.append(run)
        last_sign, peak = 0, 0.
        for state in sampled.states[start:end+1]:
            sign = 1 if state.curvature > 1e-5 else -1 if state.curvature < -1e-5 else 0
            if sign and last_sign and sign != last_sign:
                radii.append(1/peak)
                peak = 0.
            if sign:
                last_sign = sign
                peak = max(peak, abs(state.curvature))
        if peak:
            radii.append(1/peak)
        for left, right in zip(sampled.states[start:end], sampled.states[start+1:end+1]):
            chord = math.hypot(right.x-left.x, right.y-left.y)
            active = max(abs(left.curvature), abs(right.curvature)) > 1e-5
            if not active:
                zero_length += chord
            elif a["type"] == target_family:
                active_target_length += chord
        transitions += sum(segment.length_m for segment in maneuver.segments if segment.k_start != segment.k_end)
    fractions = {family: family_lengths.get(family, 0.)/length for family in (*FAMILIES, "transition")}
    if not math.isclose(sum(fractions.values()), 1., abs_tol=1e-9):
        raise GeometryError("Exposure fractions must sum to one without overlapping intervals")
    # Merge physically contiguous pure-straight annotations, including the seam.
    runs, current = [], 0.
    for a in annotations:
        if a["type"] == "straight":
            current += a["length_m"]
        elif current:
            runs.append(current)
            current = 0.
    if current:
        if annotations[0]["type"] == "straight" and runs:
            runs[0] += current
        else:
            runs.append(current)
    heading_changes = np.diff([p.heading for p in sampled.states])
    left_heading = float(sum(max(v, 0.) for v in heading_changes))
    right_heading = float(sum(max(-v, 0.) for v in heading_changes))
    total_heading = left_heading+right_heading
    aggregate = measure(sampled.states, width_m=metadata["requested"]["track_width_m"])
    return dict(length_m=length, curve_length_m=sampled.length_m,
        target_family=target_family, target_exposure_fraction=fractions[target_family],
        family_exposure_fractions=fractions,
        supporting_family_exposure_fractions={k: v for k, v in fractions.items() if k != target_family and v},
        primary_target_role_exposure_fraction=role_lengths["target"]/length,
        role_exposure_fractions={k: v/length for k, v in role_lengths.items()},
        maneuver_counts=dict(counts), direction_counts=dict(Counter(a["direction"] for a in annotations)),
        annotated_straight_lengths_m=_distribution(straight_lengths), continuous_straight_runs_m=_distribution(runs),
        turn_radius_distribution_m=_distribution(radii), straight_before_turn_lengths_m=_distribution(before_turn),
        directional_balance=dict(left_heading_change_rad=left_heading, right_heading_change_rad=right_heading,
                                 left_fraction=left_heading/total_heading, right_fraction=right_heading/total_heading,
                                 signed_heading_change_rad=left_heading-right_heading),
        total_absolute_heading_change_rad=total_heading,
        peak_curvature_inv_m=max(abs(p.curvature) for p in sampled.states),
        peak_exported_curvature_inv_m=1/metadata["measured"]["minimum_radius_m"],
        peak_curvature_change_rate_inv_m2=max(abs(p.curvature_rate) for p in sampled.states),
        total_zero_curvature_fraction=zero_length/length,
        target_active_turn_fraction_of_lap=active_target_length/length,
        embedded_transition_physical_length_m=transitions,
        embedded_transition_accounting="subset of family intervals; never added again",
        aggregate_measurements=aggregate)


@dataclass
class PreparedSpecialist:
    export_settings: object
    geometry: object
    metadata: dict
    sampled: object
    statistics: dict


def prepare_specialist(spec: SpecialistSpec):
    maneuvers, roles, frame = build_template(spec)
    p = spec.parameters
    parametric = ParametricTrackSpec(spec.track_id, maneuvers, spacing_m=p["spacing_m"], width_m=p["track_width_m"],
        resolution=p["resolution_m_per_pixel"], padding=p["padding_m"], frame=frame, limits=spec.limits,
        vehicle=spec.vehicle, random_seed=spec.seed, dataset_id=spec.dataset_id)
    settings, geometry, metadata, sampled = prepare_parametric_track(parametric)
    # Phase 2 measures intervals on the actual six-decimal CSV coordinates.
    rounded_states = tuple(replace(s, x=float(f"{s.x:.6f}"), y=float(f"{s.y:.6f}")) for s in sampled.states)
    rounded_states = (*rounded_states[:-1], replace(rounded_states[-1], x=rounded_states[0].x, y=rounded_states[0].y))
    sampled = replace(sampled, states=tuple(rounded_states))
    points = sampled.points
    if self_intersects(points, closed=True):
        raise GeometryError("CSV coordinate quantization introduced a centerline intersection")
    geometry.walls = [[Point2D(float(f"{q.x:.6f}"), float(f"{q.y:.6f}")) for q in wall] for wall in geometry.walls]
    if any(self_intersects(wall, closed=True) for wall in geometry.walls):
        raise GeometryError("CSV coordinate quantization introduced a boundary intersection")
    gap = minimum_boundary_separation(*geometry.walls, closed=True)
    if gap-2*spec.limits.footprint_margin_m < spec.limits.minimum_usable_width_m:
        raise GeometryError("Exported wall clearance below the configured minimum")
    distance = np.r_[0., np.cumsum([math.hypot(b.x-a.x, b.y-a.y) for a, b in zip(sampled.states, sampled.states[1:])])]
    curvature = position_curvatures((sampled.states[-2], *sampled.states[:-1], sampled.states[1]))[1:-1]
    for i, row in enumerate(geometry.profile):
        row.update(s_m=float(distance[i]), x_m=points[i].x, y_m=points[i].y, curvature_inv_m=float(curvature[i]))
    geometry.samples = [CenterlineSample(s.x, s.y, s.heading) for s in sampled.states[:-1]]
    geometry.metrics = profile_metrics(points, geometry.profile)
    metadata["measured"] = geometry.metrics
    validation = metadata["provenance"]["validation"]
    validation["exported_global_boundary_separation_m"] = gap
    raster = _rasterize_walls(geometry.walls, resolution=p["resolution_m_per_pixel"], padding=p["padding_m"],
                              thickness_px=1, occupancy_mode="corridor")
    validation["exported_raster_footprint"] = validate_raster_footprint(sampled, (*raster, p["resolution_m_per_pixel"]),
                                                                      spec.vehicle, spec.limits.footprint_margin_m)
    validation["csv_coordinate_precision_m"] = .000001
    for annotation, maneuver, (start, end), role in zip(metadata["maneuvers"], maneuvers, sampled.spans, roles):
        annotation.update(periodic_interval(float(distance[start]), float(distance[end]), float(distance[-1])))
        annotation["measured"] = validate_maneuver(maneuver, sampled.states[start:end+1], width_m=p["track_width_m"])
        annotation["requested"]["template_role"] = role
    stats = composition_statistics(metadata, sampled, roles, spec.target_family)
    stats.update(global_boundary_separation_m=gap,
                 minimum_usable_corridor_width_m=gap-2*spec.limits.footprint_margin_m,
                 raster_usable_width_lower_bound_m=gap-2*spec.limits.footprint_margin_m-4*math.sqrt(2)*p["resolution_m_per_pixel"])
    if stats["raster_usable_width_lower_bound_m"] < spec.limits.minimum_usable_width_m:
        raise GeometryError("Exported raster usable-width bound is below the configured minimum")
    if stats["target_exposure_fraction"]+1e-12 < spec.minimum_target_exposure:
        raise GeometryError(f"Target exposure {stats['target_exposure_fraction']:.6f} below requested {spec.minimum_target_exposure:.6f}")
    expected_turn = -math.tau if spec.clockwise else math.tau
    if not math.isclose(stats["directional_balance"]["signed_heading_change_rad"], expected_turn, abs_tol=1e-7):
        raise GeometryError("Traversal winding disagrees with requested direction")
    # Intent is explicit; composition is measured separately. Phase 1 is untouched.
    metadata.update(generator_version=GENERATOR_VERSION, generation_mode="specialist", geometry_family=f"specialist_{spec.target_family}")
    metadata["requested"].update(target_family=spec.target_family, minimum_target_exposure_fraction=spec.minimum_target_exposure,
                                  specialist_parameters=dict(p), clockwise=spec.clockwise)
    identity = dict(template_family=spec.target_family, template_revision=spec.template_revision,
                    parent_lineage_id=spec.lineage_id, variant_number=spec.variant_number, generation_seed=spec.seed,
                    configuration_sha256=spec.configuration_id, parameter_shape_id=spec.shape_id,
                    geometry_fingerprint=geometry_fingerprint(points), vehicle=asdict(spec.vehicle))
    metadata["provenance"].update(identity=identity, experimental_intent={"mode": "specialist", "target_family": spec.target_family},
                                  specialist_statistics=stats, validation_report=f"{spec.track_id}_validation.json")
    metadata["difficulty"] = {"label": "unrated", "indicators": {
        "target_exposure_fraction": stats["target_exposure_fraction"],
        "peak_curvature_inv_m": stats["peak_curvature_inv_m"],
        "peak_curvature_change_rate_inv_m2": stats["peak_curvature_change_rate_inv_m2"],
        "global_clearance_m": gap, "target_maneuver_count": stats["maneuver_counts"][spec.target_family],
        "minimum_turn_radius_m": stats["turn_radius_distribution_m"]["minimum"],
        "minimum_usable_corridor_width_m": stats["minimum_usable_corridor_width_m"],
        "target_feature_frequency_per_100m": 100*stats["maneuver_counts"][spec.target_family]/stats["length_m"],
        "longest_straight_before_turn_m": stats["straight_before_turn_lengths_m"]["maximum"] or 0.}}
    metadata["provenance"]["geometric_difficulty"] = {
        "requested_dimensions": {k: v for k, v in p.items() if k not in {"spacing_m", "resolution_m_per_pixel", "padding_m"}},
        "measured_dimensions": dict(metadata["difficulty"]["indicators"]),
        "categorical_driving_difficulty": "unrated", "physical_drivability": "unassessed"}
    validate_specialist_metadata(metadata)
    return PreparedSpecialist(settings, geometry, metadata, sampled, stats)


def validate_specialist_metadata(metadata):
    validate_geometry_metadata(metadata)
    if metadata["generator_version"] != GENERATOR_VERSION or metadata["generation_mode"] != "specialist":
        raise GeometryError("Specialist generator must retain explicit specialist intent")
    target = metadata["requested"]["target_family"]
    if target not in FAMILIES:
        raise GeometryError("Unknown target family")
    length = metadata["measured"]["length_m"]
    actual = sum(a["length_m"] for a in metadata["maneuvers"] if a["type"] == target)/length
    recorded = metadata["provenance"]["specialist_statistics"]["target_exposure_fraction"]
    if not math.isclose(actual, recorded, abs_tol=1e-10) or actual+1e-12 < metadata["requested"]["minimum_target_exposure_fraction"]:
        raise GeometryError("Specialist exposure must agree with final nonoverlapping intervals")
    stats = metadata["provenance"]["specialist_statistics"]
    if set(stats["family_exposure_fractions"]) != set((*FAMILIES, "transition")):
        raise GeometryError("Family exposure must account for the complete controlled vocabulary")
    for family, fraction in stats["family_exposure_fractions"].items():
        measured = sum(a["length_m"] for a in metadata["maneuvers"] if a["type"] == family)/length
        if not math.isclose(measured, fraction, abs_tol=1e-10):
            raise GeometryError("Supporting-family exposure must agree with intervals")
    if stats["maneuver_counts"] != dict(Counter(a["type"] for a in metadata["maneuvers"])):
        raise GeometryError("Maneuver counts must agree with final annotations")
    if metadata["provenance"]["experimental_intent"] != {"mode": "specialist", "target_family": target}:
        raise GeometryError("Experimental intent disagrees with the target family")
    if not math.isclose(sum(a["length_m"] for a in metadata["maneuvers"]), length, abs_tol=1e-8):
        raise GeometryError("Specialist annotations must cover the full lap")
    if metadata["split"] != "unspecified" or metadata["difficulty"]["label"] != "unrated":
        raise GeometryError("Phase 2 leaves dataset split unspecified and driving difficulty unrated")


def _write_bundle(spec, prepared, directory):
    path = export_track_geometry(prepared.export_settings, prepared.geometry, directory,
                                 metadata_contract=prepared.metadata, generation_recipe=spec.recipe())
    document = load_map_yaml(path)
    states = prepared.sampled.states
    index = max(0, next((i for i, s in enumerate(states) if s.s >= states[-1].s-1.0), len(states)-2)-1)
    pose = states[index]
    document.annotations.spawn_points = [SpawnPoint("grid_1", Pose2D(pose.x, pose.y, pose.heading))]
    dump_map_yaml(document, path)
    return path


def consumer_smoke(path, reference):
    try:
        result = subprocess.run([sys.executable, str(ROOT/"scripts/smoke_marl_race.py"), str(path),
                                 "--marl-race-root", str(reference)], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise GeometryError("Actual marl_race smoke exceeded its 120-second budget") from exc
    if result.returncode:
        raise GeometryError("Actual marl_race smoke failed: "+(result.stderr or result.stdout)[-3000:])
    report = json.loads(result.stdout)
    report["bundle"] = path.name
    revision = subprocess.run(["git", "-C", str(reference), "rev-parse", "HEAD"], capture_output=True, text=True)
    return {"status": "passed", "checks": report, "reference_revision": revision.stdout.strip() if revision.returncode == 0 else None}


def publish_specialist(spec, prepared, output_dir, *, reference=None, verify_replay=True):
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing bundle directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".specialist-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)/"bundle"
        path = _write_bundle(spec, prepared, staging)
        integration = consumer_smoke(path, reference) if reference is not None else {"status": "not_run"}
        artifacts = prepared.metadata["artifacts"]
        hashes = {key: hashlib.sha256((staging/name).read_bytes()).hexdigest() for key, name in artifacts.items()}
        replay = {"status": "not_run"}
        if verify_replay:
            reloaded = load_specialist_spec(staging/artifacts["recipe"])
            replay_prepared = prepare_specialist(reloaded)
            replay_dir = Path(temporary)/"replay"
            _write_bundle(reloaded, replay_prepared, replay_dir)
            for name in artifacts.values():
                if (staging/name).read_bytes() != (replay_dir/name).read_bytes():
                    raise GeometryError(f"Recipe replay changed artifact: {name}")
            replay = {"status": "passed", "artifacts_compared": len(artifacts), "byte_identical": True}
        report = dict(schema_version=1, generator=GENERATOR_VERSION, track_id=spec.track_id,
                      geometric_validity="accepted", physical_drivability="unassessed", difficulty="unrated",
                      identity=prepared.metadata["provenance"]["identity"], requested=spec.recipe(),
                      statistics=prepared.statistics, validation=prepared.metadata["provenance"]["validation"],
                      continuity=prepared.metadata["provenance"]["continuity_residuals"],
                      integration=integration, recipe_replay=replay, artifact_sha256=hashes)
        (staging/f"{spec.track_id}_validation.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
        # Atomically reserve the final directory. Never replace pre-existing data.
        output_dir.mkdir(exist_ok=False)
        try:
            for artifact in staging.iterdir():
                shutil.move(str(artifact), output_dir/artifact.name)
        except BaseException:
            shutil.rmtree(output_dir)
            raise
    return output_dir/path.name


def generate_specialist_bundle(spec, output_dir, *, reference=None, verify_replay=True):
    if Path(output_dir).exists():
        raise FileExistsError(f"Refusing to overwrite existing bundle directory: {output_dir}")
    return publish_specialist(spec, prepare_specialist(spec), output_dir, reference=reference, verify_replay=verify_replay)
