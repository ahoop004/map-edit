#!/usr/bin/env python3
"""Small geometric feasibility sweep; no exported dataset or controller rollout."""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from map_editor.geometry import GeometryError
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.parametric_track import ParametricTrackSpec, prepare_parametric_track
from map_editor.services.specialist_templates import SpecialistSpec, FAMILIES, DEFAULT_EXPOSURE, build_template


def experiment(vehicle):
    cases = []
    for family in FAMILIES:
        for level in (1, 2, 3, 4):
            parameters = {}
            if family == "straight":
                parameters["maneuver_length_m"] = {1: 10., 2: 30., 3: 50., 4: 30.}[level]
            elif family in {"hairpin", "sweeper"}:
                parameters.update(approach_length_m={1: .5, 2: 2., 3: 6., 4: 1.}[level],
                                  exit_length_m={1: .5, 2: 2., 3: 6., 4: 1.}[level])
            else:
                parameters["repetitions"] = min(level, 3)
            if level == 4:
                parameters["track_width_m"] = 20.
            spec = SpecialistSpec(family, vehicle, parameters=parameters)
            p = spec.parameters
            record = dict(family=family, parameters=p, default_minimum_exposure=DEFAULT_EXPOSURE[family])
            try:
                maneuvers, _, frame = build_template(spec)
                _, geometry, metadata, _ = prepare_parametric_track(ParametricTrackSpec("experiment", maneuvers,
                    spacing_m=p["spacing_m"], width_m=p["track_width_m"], resolution=p["resolution_m_per_pixel"],
                    padding=p["padding_m"], frame=frame, vehicle=vehicle, limits=spec.limits))
                exposure = sum(m["length_m"] for m in metadata["maneuvers"] if m["type"] == family)/geometry.metrics["length_m"]
                record.update(geometric_validity="accepted", measured_target_exposure=exposure,
                              meets_default_exposure=exposure >= DEFAULT_EXPOSURE[family])
            except GeometryError as exc:
                record.update(geometric_validity="rejected", reason=str(exc))
            cases.append(record)
    return dict(schema_version=1, kind="specialist_threshold_experiment", vehicle_source=vehicle.source,
                vehicle_sha256=vehicle.source_sha256, cases=cases, physical_drivability="unassessed",
                note="Tests geometry before applying a specialist exposure threshold. These are observed operating points, not universal feasibility bounds.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicle", type=Path, default=ROOT.parent/"marl_race/configs/vehicle/combined_slip.yaml")
    parser.add_argument("--output", type=Path, default=ROOT/"docs/phase2_thresholds.json")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file; existing evidence is not overwritten")
    args.output.write_text(json.dumps(experiment(VehicleProfile.from_yaml(args.vehicle)), indent=2)+"\n")
    print(args.output)
