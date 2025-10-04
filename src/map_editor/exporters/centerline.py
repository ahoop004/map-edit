"""Export utilities for centerline waypoints."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from map_editor.models.annotations import Point2D


@dataclass(frozen=True)
class CenterlineSample:
    x: float
    y: float
    theta: float
    velocity: Optional[float] = None


def resample_centerline(points: Iterable[Point2D], spacing: float) -> List[CenterlineSample]:
    """Resample polyline points so samples are roughly `spacing` meters apart."""
    pts = list(points)
    if len(pts) < 2 or spacing <= 0:
        return []

    samples: List[CenterlineSample] = []
    accumulated = 0.0
    prev = pts[0]

    for idx in range(1, len(pts)):
        current = pts[idx]
        seg_dx = current.x - prev.x
        seg_dy = current.y - prev.y
        seg_length = math.hypot(seg_dx, seg_dy)
        if seg_length <= 1e-9:
            continue
        direction = (seg_dx / seg_length, seg_dy / seg_length)

        while accumulated + seg_length >= spacing or not samples:
            overshoot = spacing - accumulated if samples else 0.0
            if overshoot > seg_length:
                break
            sample_x = prev.x + direction[0] * overshoot
            sample_y = prev.y + direction[1] * overshoot
            theta = math.atan2(direction[1], direction[0])
            samples.append(CenterlineSample(sample_x, sample_y, theta))
            seg_length -= overshoot
            prev = Point2D(sample_x, sample_y)
            accumulated = 0.0
            if seg_length <= 1e-9:
                break
            direction = (
                (current.x - prev.x) / seg_length,
                (current.y - prev.y) / seg_length,
            )
        accumulated += seg_length
        prev = current

    last = pts[-1]
    if not samples or math.hypot(samples[-1].x - last.x, samples[-1].y - last.y) > spacing * 0.5:
        if len(pts) >= 2:
            prev_point = pts[-2]
            theta = math.atan2(last.y - prev_point.y, last.x - prev_point.x)
        else:
            theta = 0.0
        samples.append(CenterlineSample(last.x, last.y, theta))

    return samples


def export_centerline_csv(samples: Iterable[CenterlineSample], destination: Path) -> None:
    """Export centerline samples to CSV columns: x,y,theta,velocity."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y", "theta", "velocity"])
        for sample in samples:
            row = [f"{sample.x:.6f}", f"{sample.y:.6f}", f"{sample.theta:.6f}"]
            row.append("" if sample.velocity is None else f"{sample.velocity:.3f}")
            writer.writerow(row)
