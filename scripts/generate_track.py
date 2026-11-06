#!/usr/bin/env python3
"""Generate a procedural track bundle from a YAML spec."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from dataclasses import replace

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from map_editor.services.procedural_track import (
    TrackSpecError,
    generate_track_bundle,
    load_track_spec,
)
from map_editor.services.paper_tracks import build_paper_track_spec, generate_paper_collection


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a procedural track bundle.")
    parser.add_argument("input", type=Path, nargs="?", help="YAML track spec or generation recipe path.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: sample_maps/<stem>_map).",
    )
    parser.add_argument(
        "--preset",
        default="sample_default",
        choices=["sample_default", "paper_l"],
        help="Preset name for default settings.",
    )
    parser.add_argument("--count", type=int, default=0, help="Paper variants in addition to the reference (0 = reference only).")
    parser.add_argument("--seed", type=int, default=42, help="Collection random seed.")
    parser.add_argument("--variation", type=float, default=0.2, help="Shape variation fraction, in (0, 0.5].")
    parser.add_argument("--max-attempts", type=int, help="Candidate budget; incomplete collections exit with status 2.")
    parser.add_argument("--target-length", type=float, help="Target centerline lap length in meters.")
    parser.add_argument("--track-width", type=float, help="Track width in meters.")
    parser.add_argument("--min-radius", type=float, help="Minimum centerline corner radius in meters.")
    parser.add_argument("--occupancy-mode", choices=["walls", "corridor"],
                        help="Legacy boundary-only image or occupied exterior/infield (recipe default preserved).")
    args = parser.parse_args(argv)

    if args.input and args.preset != "sample_default":
        parser.error("Choose either an input recipe or --preset paper_l.")
    if not args.input and args.preset != "paper_l":
        parser.error("Provide a YAML spec or --preset paper_l.")
    if args.count < 0:
        parser.error("--count must be nonnegative.")
    try:
        spec = load_track_spec(args.input) if args.input else build_paper_track_spec()
        changes = {}
        if args.occupancy_mode is not None:
            changes["occupancy_mode"] = args.occupancy_mode
        if args.target_length is not None:
            changes["target_length"] = args.target_length
        if args.track_width is not None:
            changes.update(track_width=args.track_width, min_wall_separation=args.track_width)
        if args.min_radius is not None:
            changes["min_curvature_radius"] = args.min_radius
        spec = replace(spec, **changes)
        output_dir = args.output or Path("sample_maps") / (
            "paper_l_collection" if args.count else f"{spec.stem}_map")
        if args.count:
            report = generate_paper_collection(
                spec, output_dir, count=args.count, seed=args.seed,
                variation=args.variation, max_attempts=args.max_attempts,
            )
            print(f"Generated reference and {len(report['accepted'])}/{args.count} variants; "
                  f"{len(report['rejected'])} candidates rejected.")
            print(f"Metrics and recipes: {output_dir / 'collection.yaml'}")
            return 0 if report["complete"] else 2
        yaml_path = generate_track_bundle(spec, output_dir)
    except (TrackSpecError, OSError) as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Generated bundle: {yaml_path}")
    recipe = yaml.safe_load((output_dir / f"{spec.stem}_generation.yaml").read_text(encoding="utf-8"))
    print(f"Measured geometry: {recipe['achieved']}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    raise SystemExit(main(sys.argv[1:]))
