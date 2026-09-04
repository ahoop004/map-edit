#!/usr/bin/env python3
"""Generate multiple random procedural track bundles."""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from map_editor.models.annotations import Point2D
from map_editor.services.procedural_track import (
    TrackSpec,
    TrackSpecError,
    adjust_control_points_for_min_radius,
    generate_track_bundle,
)


def _parse_range(values: Iterable[float]) -> tuple[float, float]:
    items = list(values)
    if not items:
        raise ValueError("Range requires at least one value.")
    if len(items) == 1:
        return items[0], items[0]
    if len(items) == 2:
        return items[0], items[1]
    raise ValueError("Range requires one or two values.")


def _random_control_points(
    rng: random.Random,
    count: int,
    length: float,
    width: float,
) -> list[Point2D]:
    angles = sorted(rng.uniform(0.0, 2.0 * math.pi) for _ in range(count))
    a = length * 0.5
    b = width * 0.5
    points: list[Point2D] = []
    for theta in angles:
        radial_scale = rng.uniform(0.7, 1.3)
        x = a * math.cos(theta) * radial_scale
        y = b * math.sin(theta) * radial_scale
        points.append(Point2D(x, y))
    if not points:
        return []
    if len(points) < 4:
        points.append(Point2D(points[0].x, points[0].y))
    return points


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate random procedural track bundles.")
    parser.add_argument("--count", type=int, default=5, help="Number of bundles to generate.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed.")
    parser.add_argument("--output-root", type=Path, default=Path("sample_maps"), help="Output root folder.")
    parser.add_argument("--prefix", type=str, default="random_track", help="Bundle stem prefix.")
    parser.add_argument("--min-points", type=int, default=3, help="Minimum control points per track.")
    parser.add_argument("--max-points", type=int, default=8, help="Maximum control points per track.")
    parser.add_argument("--length-range", type=float, nargs="+", default=[20.0, 80.0], help="Length range (m).")
    parser.add_argument("--width-range", type=float, nargs="+", default=[10.0, 40.0], help="Width range (m).")
    parser.add_argument("--track-width-range", type=float, nargs="+", default=[2.2], help="Track width range (m).")
    parser.add_argument("--resolution", type=float, default=0.06, help="Resolution (m/px).")
    parser.add_argument("--padding", type=float, default=5.0, help="Padding (m).")
    parser.add_argument("--wall-thickness", type=int, default=2, help="Wall thickness in pixels.")
    parser.add_argument(
        "--min-curvature-radius",
        type=float,
        default=3.0,
        help="Minimum curvature radius (m).",
    )
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    min_points = max(3, args.min_points)
    max_points = max(min_points, args.max_points)
    length_min, length_max = _parse_range(args.length_range)
    width_min, width_max = _parse_range(args.width_range)
    track_w_min, track_w_max = _parse_range(args.track_width_range)

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    for idx in range(args.count):
        count = rng.randint(min_points, max_points)
        length = rng.uniform(length_min, length_max)
        width = rng.uniform(width_min, width_max)
        track_width = rng.uniform(track_w_min, track_w_max)
        control_points = _random_control_points(rng, count, length, width)
        control_points, _ = adjust_control_points_for_min_radius(
            control_points,
            args.min_curvature_radius,
            centerline_spacing=0.2,
        )
        stem = f"{args.prefix}_{idx + 1:03d}"
        spec = TrackSpec(
            stem=stem,
            control_points=control_points,
            track_width=track_width,
            centerline_spacing=0.2,
            resolution=args.resolution,
            padding=args.padding,
            wall_thickness_px=args.wall_thickness,
            min_curvature_radius=args.min_curvature_radius,
        )
        output_dir = output_root / f"{stem}_map"
        try:
            generate_track_bundle(spec, output_dir)
        except TrackSpecError as exc:
            print(f"{stem}: skipped ({exc})", file=sys.stderr)
            continue
        print(f"{stem}: {output_dir}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    raise SystemExit(main(sys.argv[1:]))
