#!/usr/bin/env python3
"""Record bounded, deliberately infeasible composite requests without exporting maps."""
from dataclasses import replace
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.composite_spec import ConnectorConstraints,ManeuverRequest
from map_editor.services.composite_pilot import default_composite_requests
from map_editor.services.composite_tracks import prepare_composite,CompositeGenerationError


def audit(vehicle):
    requests=default_composite_requests(vehicle)
    bad_hairpin=ManeuverRequest("wrong_hairpin","hairpin",dict(radius_m=8,turn_angle_rad=math.pi/2))
    cases={
        "asymmetric_return_outside_bounds":replace(requests[1].base,connectors=ConnectorConstraints(straight_range_m=(0,.25),solver_budget=4)),
        "wrong_maneuver_identity":replace(requests[0].base,inventory=(requests[0].base.inventory[0],bad_hairpin),required_families=()),
        "unattainable_exposure_request":replace(requests[0].base,exposure_bounds={"straight":[.99,1]}),
        "unattainable_lap_length":replace(requests[0].base,lap_length_range_m=(20,21)),
    }
    report=dict(schema_version=1,kind="composite_rejection_audit",cases=[],physical_drivability="unassessed")
    for name,spec in cases.items():
        try:
            prepare_composite(spec)
        except CompositeGenerationError as exc:
            report["cases"].append(dict(case=name,status="rejected",reason=str(exc),closure_attempts=exc.attempts,recipe=spec.recipe()))
        else:
            raise RuntimeError(f"Expected rejection was not enforced: {name}")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicle",type=Path,default=ROOT.parent/"marl_race/configs/vehicle/combined_slip.yaml")
    parser.add_argument("--output",type=Path,default=ROOT/"docs/phase3_rejections.json")
    args=parser.parse_args()
    if args.output.exists():
        parser.error("Use a fresh rejection-evidence path")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(audit(VehicleProfile.from_yaml(args.vehicle)),indent=2)+"\n")
    print(args.output)
