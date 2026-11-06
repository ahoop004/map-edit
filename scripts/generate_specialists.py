#!/usr/bin/env python3
"""Generate the Phase 2 pilot, or replay a versioned specialist template recipe."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.specialist_templates import load_specialist_spec
from map_editor.services.specialist_tracks import generate_specialist_bundle
from map_editor.services.specialist_pilot import default_pilot_requests, generate_pilot, load_pilot_recipe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--output", type=Path, required=True)
    pilot.add_argument("--vehicle", type=Path, default=ROOT.parent/"marl_race/configs/vehicle/combined_slip.yaml")
    pilot.add_argument("--recipe", type=Path, help="Optional saved pilot_recipe.json instead of default requests")
    pilot.add_argument("--seed", type=int, default=42)
    pilot.add_argument("--max-attempts", type=int, default=8)
    pilot.add_argument("--profile", type=Path)
    replay = sub.add_parser("replay")
    replay.add_argument("recipe", type=Path)
    replay.add_argument("--output", type=Path, required=True)
    for command in (pilot, replay):
        command.add_argument("--marl-race-root", type=Path, default=ROOT.parent/"marl_race")
    args = parser.parse_args()
    try:
        if args.command == "replay":
            print(generate_specialist_bundle(load_specialist_spec(args.recipe), args.output, reference=args.marl_race_root))
            return 0
        if args.recipe:
            requests, seed, budget = load_pilot_recipe(args.recipe)
        else:
            requests, seed, budget = default_pilot_requests(VehicleProfile.from_yaml(args.vehicle)), args.seed, args.max_attempts
        report = generate_pilot(requests, args.output, seed=seed, max_attempts=budget,
                                reference=args.marl_race_root, profile_path=args.profile, progress=lambda value: print(value, flush=True))
        print(f"Pilot: {len(report['accepted'])}/{report['requested_tracks']} accepted; {len(report['rejected'])} rejected candidates; complete={report['complete']}")
        return 0 if report["complete"] else 2
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Generation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
