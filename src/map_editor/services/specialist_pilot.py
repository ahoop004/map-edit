"""Bounded ten-track pilot, independent per-candidate rejection and audit records."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import platform
import random
from time import perf_counter

from map_editor.geometry import GeometryError
from map_editor.services.specialist_templates import (
    GENERATOR_VERSION, FAMILIES, SpecialistSpec, sample_spec, specialist_spec_from_recipe,
)
from map_editor.services.specialist_tracks import prepare_specialist, publish_specialist


@dataclass(frozen=True)
class CandidateRequest:
    base: SpecialistSpec
    ranges: dict

    def __post_init__(self):
        if not isinstance(self.base, SpecialistSpec) or not isinstance(self.ranges, dict):
            raise GeometryError("Candidate requests need a specialist specification and numeric ranges")
        for name, bounds in self.ranges.items():
            if name not in self.base.parameters or not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise GeometryError(f"Invalid numeric parameter range: {name}")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds) or bounds[0] > bounds[1]:
                raise GeometryError(f"Invalid finite ordered range for {name}")
            if name == "repetitions" and any(type(v) is not int for v in bounds):
                raise GeometryError("Repetition ranges require integer bounds")


def default_pilot_requests(vehicle):
    requests = []
    second = {
        "straight": dict(maneuver_length_m=45., approach_length_m=2., exit_length_m=3., connector_radius_m=3.6),
        "hairpin": dict(turn_radius_m=4., transition_length_m=.85, approach_length_m=1.5, exit_length_m=1.5),
        "sweeper": dict(turn_radius_m=9., turn_angle_rad=2.8, transition_length_m=1.4,
                        connector_transition_m=.5, approach_length_m=2., exit_length_m=2.),
        "chicane": dict(turn_radius_m=4.8, lateral_displacement_m=4.1, chicane_spacing_m=2.5,
                        connector_radius_m=3.3, connector_transition_m=1.2, approach_length_m=1.2, exit_length_m=1.4),
        "s_curve": dict(first_radius_m=5., second_radius_m=6.5, turn_angle_rad=1.2, transition_length_m=1.2,
                        connector_radius_m=3.5, connector_transition_m=1.1, approach_length_m=1.5, exit_length_m=1.5),
    }
    varied = {"straight": "maneuver_length_m", "hairpin": "turn_radius_m", "sweeper": "turn_radius_m",
              "chicane": "lateral_displacement_m", "s_curve": "first_radius_m"}
    for family in FAMILIES:
        for variant in (1, 2):
            base = SpecialistSpec(family, vehicle, parameters={} if variant == 1 else second[family],
                                  variant_number=variant, clockwise=variant == 2)
            key = varied[family]
            value = base.parameters[key]
            requests.append(CandidateRequest(base, {key: [value*.98, value*1.02]}))
    return tuple(requests)


def pilot_recipe(requests, seed, max_attempts):
    return dict(schema_version=1, generator=GENERATOR_VERSION, kind="specialist_pilot",
                seed=seed, max_attempts_per_request=max_attempts,
                requests=[dict(base=r.base.recipe(), ranges=r.ranges) for r in requests])


def load_pilot_recipe(path):
    data = json.loads(Path(path).read_text())
    if data.get("schema_version") != 1 or data.get("generator") != GENERATOR_VERSION or data.get("kind") != "specialist_pilot":
        raise GeometryError("Unsupported specialist pilot recipe")
    requests = tuple(CandidateRequest(specialist_spec_from_recipe(r["base"]), r["ranges"]) for r in data["requests"])
    return requests, data["seed"], data["max_attempts_per_request"]


def feature_signature(prepared):
    target = prepared.metadata["requested"]["target_family"]
    annotations = [m for m in prepared.metadata["maneuvers"] if m["type"] == target and m["requested"]["template_role"] == "target"]
    def average(key):
        values = [abs(m["measured"][key]) for m in annotations if m["measured"][key] is not None]
        return sum(values)/len(values) if values else None
    return dict(lap_length_m=prepared.statistics["length_m"], target_count=len(annotations),
                target_mean_length_m=sum(m["length_m"] for m in annotations)/len(annotations),
                target_mean_radius_m=average("minimum_radius_m"),
                target_mean_absolute_heading_rad=average("absolute_heading_change_rad"),
                target_mean_displacement_m=average("lateral_displacement_m"))


def meaningfully_different(first, second, minimum_relative_change=.05):
    return any(a is not None and b is not None and abs(b-a) >= minimum_relative_change*max(abs(a), abs(b), 1e-8)
               for key, a in first.items() for b in [second[key]])


def generate_pilot(requests, output_dir, *, seed=42, max_attempts=8, reference, progress=None, profile_path=None):
    if type(seed) is not int or seed < 0 or type(max_attempts) is not int or not 1 <= max_attempts <= 100:
        raise GeometryError("Pilot seed must be nonnegative; candidate budget must be 1..100 per request")
    requested = [(r.base.target_family, r.base.variant_number) for r in requests]
    if len(requested) != len(set(requested)):
        raise GeometryError("Pilot requests cannot repeat a family/variant identity")
    if Path(output_dir).exists():
        raise FileExistsError(f"Refusing to overwrite pilot directory: {output_dir}")
    if profile_path is not None and Path(profile_path).exists():
        raise FileExistsError(f"Refusing to overwrite runtime evidence: {profile_path}")
    if not (Path(reference)/"src/utils/map_loader.py").is_file():
        raise GeometryError("A local marl_race checkout is required to accept pilot tracks")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    configuration = pilot_recipe(requests, seed, max_attempts)
    (output_dir/"pilot_recipe.json").write_text(json.dumps(configuration, indent=2)+"\n")
    report = dict(schema_version=1, generator=GENERATOR_VERSION, requested_tracks=len(requests), complete=False,
                  requested_counts=dict((f, sum(r.base.target_family == f for r in requests)) for f in FAMILIES),
                  seed=seed, max_attempts_per_request=max_attempts, accepted=[], rejected=[], incomplete_requests=[])
    manifest = output_dir/"manifest.json"
    def save():
        manifest.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    save()
    rng = random.Random(seed)
    ids, shapes, fingerprints = set(), set(), set()
    signatures = {}
    timings = []
    started = perf_counter()
    for request in requests:
        accepted = False
        for attempt in range(1, max_attempts+1):
            candidate_seed = rng.getrandbits(63)
            candidate, prepared = None, None
            begin = perf_counter()
            try:
                candidate = sample_spec(request.base, request.ranges, candidate_seed)
                if candidate.track_id in ids:
                    raise GeometryError("Duplicate track identifier")
                prepared = prepare_specialist(candidate)
                fingerprint = prepared.metadata["provenance"]["identity"]["geometry_fingerprint"]
                if candidate.shape_id in shapes or fingerprint in fingerprints:
                    raise GeometryError("Duplicate geometry; changing a seed or traversal is not a new layout")
                signature = feature_signature(prepared)
                family = candidate.target_family
                if family in signatures and not meaningfully_different(signatures[family], signature):
                    raise GeometryError("Pilot variant has less than 5% change in all measured feature dimensions")
                prepare_seconds = perf_counter()-begin
                publish_begin = perf_counter()
                path = publish_specialist(candidate, prepared, output_dir/candidate.track_id, reference=reference)
                publish_seconds = perf_counter()-publish_begin
            except GeometryError as exc:
                reason = str(exc)
                report["rejected"].append(dict(family=request.base.target_family, variant=request.base.variant_number,
                    attempt=attempt, seed=candidate_seed, reason=reason,
                    sampled_recipe=candidate.recipe() if candidate else None,
                    base_recipe=request.base.recipe(), ranges=request.ranges))
                timings.append(dict(family=request.base.target_family, attempt=attempt, outcome="rejected", seconds=perf_counter()-begin))
                if progress:
                    progress(f"Rejected {request.base.target_family} variant {request.base.variant_number}, attempt {attempt}: {reason}")
                save()
                continue
            ids.add(candidate.track_id)
            shapes.add(candidate.shape_id)
            fingerprints.add(fingerprint)
            signatures[family] = signature
            report["accepted"].append(dict(track_id=candidate.track_id, family=family, variant=candidate.variant_number,
                seed=candidate_seed, attempt=attempt, map=str(path.relative_to(output_dir)),
                metadata=f"{candidate.track_id}/{candidate.track_id}_metadata.json",
                validation_report=f"{candidate.track_id}/{candidate.track_id}_validation.json",
                recipe=f"{candidate.track_id}/{candidate.track_id}_generation.yaml",
                identity=prepared.metadata["provenance"]["identity"], features=signature, statistics=prepared.statistics,
                minimum_target_exposure=candidate.minimum_target_exposure, integration="passed", recipe_replay="passed",
                difficulty="unrated", physical_drivability="unassessed", split="unspecified"))
            timings.append(dict(track_id=candidate.track_id, family=family, attempt=attempt, outcome="accepted",
                                prepare_seconds=prepare_seconds, publish_replay_smoke_seconds=publish_seconds))
            if progress:
                progress(f"Accepted {family} variant {candidate.variant_number}: exposure {prepared.statistics['target_exposure_fraction']:.3f}, lap {prepared.statistics['length_m']:.2f} m")
            accepted = True
            save()
            break
        if not accepted:
            report["incomplete_requests"].append(dict(family=request.base.target_family, variant=request.base.variant_number,
                                                       exhausted_attempts=max_attempts))
    report["complete"] = len(report["accepted"]) == len(requests)
    save()
    if profile_path is not None:
        profile = dict(python=platform.python_version(), platform=platform.platform(), total_seconds=perf_counter()-started,
                       attempts=timings, note="Timings are separate from deterministic bundle/manifest artifacts; publication includes a fresh full recipe replay and actual consumer smoke.")
        Path(profile_path).parent.mkdir(parents=True, exist_ok=True)
        Path(profile_path).write_text(json.dumps(profile, indent=2)+"\n")
    return report
