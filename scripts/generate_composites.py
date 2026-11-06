#!/usr/bin/env python3
"""Generate/replay versioned composite circuits without modifying legacy generators."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.composite_spec import load_composite_spec
from map_editor.services.composite_tracks import generate_composite_bundle
from map_editor.services.composite_pilot import default_composite_requests,generate_composite_pilot,load_composite_pilot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    pilot=sub.add_parser("pilot")
    pilot.add_argument("--vehicle",type=Path,default=ROOT.parent/"marl_race/configs/vehicle/combined_slip.yaml")
    pilot.add_argument("--recipe",type=Path)
    pilot.add_argument("--seed",type=int,default=42)
    pilot.add_argument("--max-attempts",type=int,default=4)
    pilot.add_argument("--profile",type=Path)
    replay=sub.add_parser("replay")
    replay.add_argument("recipe",type=Path)
    for command in (pilot,replay):
        command.add_argument("--output",type=Path,required=True)
        command.add_argument("--marl-race-root",type=Path,default=ROOT.parent/"marl_race")
    args=parser.parse_args()
    try:
        if args.command=="replay":
            print(generate_composite_bundle(load_composite_spec(args.recipe),args.output,reference=args.marl_race_root))
            return 0
        if args.recipe:
            requests,seed,budget=load_composite_pilot(args.recipe)
        else:
            requests=default_composite_requests(VehicleProfile.from_yaml(args.vehicle))
            seed,budget=args.seed,args.max_attempts
        report=generate_composite_pilot(requests,args.output,reference=args.marl_race_root,seed=seed,max_attempts=budget,
            profile_path=args.profile,progress=lambda text:print(text,flush=True))
        print(f"Composite pilot: {len(report['accepted'])}/{report['requested_tracks']} accepted, {len(report['rejected'])} rejected; complete={report['complete']}")
        return 0 if report["complete"] else 2
    except (ValueError,OSError) as exc:
        parser.exit(1,f"Composite generation failed: {exc}\n")


if __name__=="__main__":
    raise SystemExit(main())
