#!/usr/bin/env python3
"""Generate the Phase 3B technical pilot or replay a native technical recipe."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.technical_spec import load_technical_spec
from map_editor.services.technical_tracks import publish_technical
from map_editor.services.technical_pilot import default_technical_specs,generate_technical_pilot,load_technical_pilot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    pilot=sub.add_parser('pilot');replay=sub.add_parser('replay')
    pilot.add_argument('--recipe',type=Path)
    pilot.add_argument('--vehicle',type=Path,default=ROOT.parent/'marl_race/configs/vehicle/combined_slip.yaml')
    pilot.add_argument('--profile',type=Path)
    replay.add_argument('recipe',type=Path)
    for command in (pilot,replay):
        command.add_argument('--output',type=Path,required=True)
        command.add_argument('--marl-race-root',type=Path,default=ROOT.parent/'marl_race')
    args=parser.parse_args()
    try:
        if args.command=='replay':
            print(publish_technical(load_technical_spec(args.recipe),args.output,reference=args.marl_race_root));return 0
        specs=load_technical_pilot(args.recipe) if args.recipe else default_technical_specs(VehicleProfile.from_yaml(args.vehicle))
        report=generate_technical_pilot(specs,args.output,reference=args.marl_race_root,profile_path=args.profile,
            progress=lambda s:print(s,flush=True))
        print(f"Technical pilot {len(report['accepted'])}/{report['requested_tracks']}; {report['candidate_accounting']}")
        return 0 if report['complete'] else 2
    except (ValueError,OSError) as exc:
        parser.exit(1,str(exc)+'\n')

if __name__=='__main__':raise SystemExit(main())
