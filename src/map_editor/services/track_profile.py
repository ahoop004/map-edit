"""Periodic geometric observations for a closed track in map coordinates."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Sequence

from map_editor.models.annotations import Point2D
from map_editor.services.track_metrics import _ray_wall_distance


def closed_length(points: Sequence[Point2D]) -> float:
    return sum(math.hypot(b.x - a.x, b.y - a.y)
               for a, b in zip(points, [*points[1:], points[0]])) if points else 0.0


def build_track_profile(
    points: Sequence[Point2D], walls: Sequence[Sequence[Point2D]],
) -> list[dict[str, float]]:
    """One row per centerline vertex; positive curvature means a left turn.

    Widths are ray intersections with the final closed boundaries, rather than
    the requested nominal width. The closing vertex is not repeated.
    """
    segments = [(a, b) for wall in walls
                for a, b in zip(wall, [*wall[1:], wall[0]])]
    rows = []
    distance = 0.0
    for i, point in enumerate(points):
        previous, following = points[i - 1], points[(i + 1) % len(points)]
        dx, dy = following.x - previous.x, following.y - previous.y
        norm = math.hypot(dx, dy)
        if norm <= 1e-9:
            raise ValueError("Centerline has a degenerate tangent.")
        left = _ray_wall_distance(point, (-dy / norm, dx / norm), segments)
        right = _ray_wall_distance(point, (dy / norm, -dx / norm), segments)
        if left is None or right is None:
            raise ValueError("Centerline must have a boundary on both sides.")
        ab = math.hypot(point.x - previous.x, point.y - previous.y)
        bc = math.hypot(following.x - point.x, following.y - point.y)
        ac = math.hypot(dx, dy)
        cross = ((point.x - previous.x) * (following.y - point.y)
                 - (point.y - previous.y) * (following.x - point.x))
        curvature = 2.0 * cross / (ab * bc * ac) if ab * bc * ac > 1e-12 else 0.0
        rows.append(dict(s_m=distance, x_m=point.x, y_m=point.y,
                         heading_rad=math.atan2(dy, dx), curvature_inv_m=curvature,
                         width_m=left + right, left_width_m=left, right_width_m=right))
        distance += bc
    return rows


def profile_metrics(points: Sequence[Point2D], rows: list[dict[str, float]]) -> dict:
    max_curvature = max(abs(row["curvature_inv_m"]) for row in rows)
    widths = [row["width_m"] for row in rows]
    return {
        "length_m": closed_length(points),
        "minimum_radius_m": 1.0 / max_curvature if max_curvature > 1e-9 else None,
        "minimum_width_m": min(widths),
        "maximum_width_m": max(widths),
        "mean_width_m": sum(widths) / len(widths),
        "sample_count": len(points),
    }


def export_track_profile(rows: list[dict[str, float]], destination: Path) -> None:
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({key: f"{value:.9f}" for key, value in row.items()} for row in rows)
