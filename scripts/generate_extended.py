#!/usr/bin/env python3
"""Generate/replay Phase 4B circuits entirely offline using a local vehicle snapshot."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.extended_spec import load_vehicle_snapshot,load_extended_spec
from map_editor.services.extended_tracks import publish_extended
from map_editor.services.extended_pilot import default_extended_specs,load_extended_pilot,generate_extended_pilot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    pilot=sub.add_parser('pilot');replay=sub.add_parser('replay')
    pilot.add_argument('--snapshot',type=Path,default=ROOT/'profiles/f110_resolved_phase3b.json')
    pilot.add_argument('--recipe',type=Path);pilot.add_argument('--profile',type=Path)
    replay.add_argument('recipe',type=Path)
    for command in (pilot,replay):command.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='replay':
            print(publish_extended(load_extended_spec(args.recipe),args.output));return 0
        specs=load_extended_pilot(args.recipe) if args.recipe else default_extended_specs(load_vehicle_snapshot(args.snapshot))
        report=generate_extended_pilot(specs,args.output,profile_path=args.profile,progress=lambda s:print(s,flush=True))
        print(f"Offline pilot {len(report['accepted'])}/{report['requested_tracks']}; complete={report['complete']}; {report['candidate_accounting']}")
        return 0 if report['complete'] else 2
    except (ValueError,OSError) as exc:parser.exit(1,str(exc)+'\n')

if __name__=='__main__':raise SystemExit(main())
