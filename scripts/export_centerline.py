#!/usr/bin/env python3
"""Export centerline waypoints from a map YAML to CSV."""

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
    resample_centerline,
)
from map_editor.services.yaml_serializer import load_map_yaml  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export centerline waypoints from map YAML")
    parser.add_argument("map_yaml", type=Path, help="Path to map YAML with annotations.centerline")
    parser.add_argument("--spacing", type=float, default=0.2, help="Resampling spacing in meters")
    parser.add_argument("--csv", type=Path, required=True, help="Destination CSV file (x,y,theta,velocity)")
    args = parser.parse_args()
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

    export_centerline_csv(samples, args.csv)
    print(f"Centerline CSV written to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
