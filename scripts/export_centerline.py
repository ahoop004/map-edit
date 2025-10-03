#!/usr/bin/env python3
"""Export centerline waypoints from a map YAML to CSV/YAML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from map_editor.exporters.centerline import (  # noqa: E402
    export_centerline_csv,
    export_centerline_path_yaml,
    resample_centerline,
)
from map_editor.services.yaml_serializer import load_map_yaml  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export centerline waypoints from map YAML")
    parser.add_argument("map_yaml", type=Path, help="Path to map YAML with annotations.centerline")
    parser.add_argument("--spacing", type=float, default=0.2, help="Resampling spacing in meters")
    parser.add_argument("--csv", type=Path, help="Destination CSV file (x,y,theta,velocity)")
    parser.add_argument("--path", type=Path, help="Destination YAML file (nav_msgs/Path style)")
    parser.add_argument("--frame", type=str, default="map", help="Frame id for Path YAML export")
    args = parser.parse_args()
    if not args.csv and not args.path:
        parser.error("Specify at least one of --csv or --path")
    return args


def main() -> int:
    args = parse_args()
    document = load_map_yaml(args.map_yaml)
    centerline = document.annotations.centerline
    if not centerline:
        print("No centerline found in YAML.", file=sys.stderr)
        return 1

    samples = resample_centerline(centerline, args.spacing)
    if not samples:
        print("Centerline could not be resampled (too few points).", file=sys.stderr)
        return 1

    if args.csv:
        export_centerline_csv(samples, args.csv)
        print(f"Centerline CSV written to {args.csv}")
    if args.path:
        export_centerline_path_yaml(samples, args.path, frame_id=args.frame)
        print(f"Centerline path YAML written to {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
