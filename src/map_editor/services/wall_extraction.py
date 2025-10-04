"""Utilities for extracting wall contours and deriving centerlines."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import csv

from PySide6.QtGui import QImage

from map_editor.models.annotations import Point2D
from map_editor.models.map_bundle import MapMetadata


@dataclass
class WallExtractionResult:
    walls: List[List[Point2D]]
    grid_width: int
    grid_height: int


def extract_walls(image_path: Path, metadata: MapMetadata) -> WallExtractionResult:
    """Extract wall components as ordered contours in map coordinates."""
    image = QImage(str(image_path))
    if image.isNull():
        return WallExtractionResult([], 0, 0)
    width = image.width()
    height = image.height()

    mask = [[False for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            gray = image.pixelColor(x, y).value()
            occ_prob = (255 - gray) / 255.0
            if occ_prob >= metadata.occupied_thresh:
                mask[y][x] = True

    visited = [[False for _ in range(width)] for _ in range(height)]
    walls: List[List[Point2D]] = []

    for y in range(height):
        for x in range(width):
            if mask[y][x] and not visited[y][x]:
                component = _collect_component(mask, visited, x, y)
                if len(component) < 8:
                    continue
                component_set = set(component)
                boundary = _trace_perimeter(component_set)
                if len(boundary) >= 3:
                    walls.append([
                        _grid_to_world(px, py, metadata, height) for px, py in boundary
                    ])
    walls.sort(key=lambda contour: -_polygon_area(contour))
    return WallExtractionResult(walls=walls, grid_width=width, grid_height=height)


def derive_centerline_from_walls(walls: Sequence[Sequence[Point2D]]) -> List[Point2D]:
    """Derive a smooth centerline from the two dominant wall contours."""
    if len(walls) < 2:
        return []

    outer = list(walls[0])
    inner = list(walls[1])
    if len(outer) < 3 or len(inner) < 3:
        return []

    outer = _ensure_closed_loop(outer)
    inner = _ensure_closed_loop(inner)

    outer = _ensure_orientation(outer, clockwise=False)
    inner = _ensure_orientation(inner, clockwise=False)

    sample_count = max(len(outer), len(inner), 128)

    outer_resampled = _resample_closed_polyline(outer, sample_count)
    inner_polyline = _resample_closed_polyline(inner, len(inner) * 2)

    centerline: List[Point2D] = []
    for outer_point in outer_resampled:
        corresponding = _project_point_to_polyline(outer_point, inner_polyline)
        centerline.append(
            Point2D(
                (outer_point.x + corresponding.x) * 0.5,
                (outer_point.y + corresponding.y) * 0.5,
            )
        )
    return _smooth_polyline(centerline, passes=2)


def export_walls_csv(walls: Sequence[Sequence[Point2D]], destination: Path) -> None:
    """Write wall polylines to CSV with columns wall_id,vertex_id,x,y."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["wall_id", "vertex_id", "x", "y"])
        for wall_id, wall in enumerate(walls):
            points = list(wall)
            if len(points) >= 2 and not _points_close(points[0], points[-1]):
                points.append(Point2D(points[0].x, points[0].y))
            for vertex_id, point in enumerate(points):
                writer.writerow([wall_id, vertex_id, f"{point.x:.6f}", f"{point.y:.6f}"])


def _collect_component(mask: List[List[bool]], visited: List[List[bool]], sx: int, sy: int) -> List[tuple[int, int]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    queue = deque([(sx, sy)])
    component: List[tuple[int, int]] = []
    visited[sy][sx] = True
    while queue:
        x, y = queue.popleft()
        component.append((x, y))
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and not visited[ny][nx]:
                visited[ny][nx] = True
                queue.append((nx, ny))
    return component


def _trace_perimeter(component: set[tuple[int, int]]) -> List[tuple[int, int]]:
    if not component:
        return []
    start = _find_boundary_start(component)
    if start is None:
        return list(component)

    dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    contour: List[tuple[int, int]] = []
    current = start
    direction = 0
    visited = set()
    max_steps = len(component) * 4

    while True:
        contour.append(current)
        visited.add(current)
        step_taken = False
        for i in range(8):
            idx = (direction + i) % 8
            dx, dy = dirs[idx]
            nx, ny = current[0] + dx, current[1] + dy
            if (nx, ny) in component:
                direction = (idx + 5) % 8
                current = (nx, ny)
                step_taken = True
                break
        if not step_taken:
            break
        if current == start and len(contour) > 1:
            break
        if len(contour) >= max_steps:
            break

    return contour


def _find_boundary_start(component: set[tuple[int, int]]) -> Optional[tuple[int, int]]:
    if not component:
        return None
    for px, py in sorted(component, key=lambda p: (p[1], p[0])):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (px + dx, py + dy) not in component:
                return (px, py)
    return next(iter(component))


def _points_close(a: Point2D, b: Point2D, tol: float = 1e-6) -> bool:
    return abs(a.x - b.x) <= tol and abs(a.y - b.y) <= tol


def _grid_to_world(x: int, y: int, metadata: MapMetadata, height: int) -> Point2D:
    world_x = metadata.origin_x + x * metadata.resolution
    world_y = metadata.origin_y + (height - y) * metadata.resolution
    return Point2D(world_x, world_y)


def _polygon_area(points: Sequence[Point2D]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for i in range(len(points)):
        j = (i + 1) % len(points)
        area += points[i].x * points[j].y - points[j].x * points[i].y
    return abs(area) * 0.5


def _sort_points_by_angle(points: Sequence[Point2D]) -> List[Point2D]:
    if not points:
        return []
    cx = sum(p.x for p in points) / len(points)
    cy = sum(p.y for p in points) / len(points)
    return sorted(points, key=lambda p: math.atan2(p.y - cy, p.x - cx))


def _smooth_polyline(points: Sequence[Point2D], passes: int = 1) -> List[Point2D]:
    if len(points) < 3 or passes <= 0:
        return list(points)
    smoothed = list(points)
    for _ in range(passes):
        new_points = [smoothed[0]]
        for i in range(1, len(smoothed) - 1):
            prev_pt = smoothed[i - 1]
            cur_pt = smoothed[i]
            next_pt = smoothed[i + 1]
            new_points.append(
                Point2D(
                    (prev_pt.x + cur_pt.x + next_pt.x) / 3.0,
                    (prev_pt.y + cur_pt.y + next_pt.y) / 3.0,
                )
            )
        new_points.append(smoothed[-1])
        smoothed = new_points
    return smoothed


def _ensure_closed_loop(points: Sequence[Point2D]) -> List[Point2D]:
    pts = list(points)
    if not pts:
        return pts
    if pts[0].x != pts[-1].x or pts[0].y != pts[-1].y:
        pts.append(Point2D(pts[0].x, pts[0].y))
    return pts


def _ensure_orientation(points: Sequence[Point2D], clockwise: bool) -> List[Point2D]:
    if len(points) < 3:
        return list(points)
    area = _signed_area(points)
    is_clockwise = area < 0
    if is_clockwise != clockwise:
        return list(reversed(points))
    return list(points)


def _signed_area(points: Sequence[Point2D]) -> float:
    area = 0.0
    for i in range(len(points) - 1):
        j = i + 1
        area += points[i].x * points[j].y - points[j].x * points[i].y
    return area * 0.5


def _cumulative_lengths(points: Sequence[Point2D]) -> List[float]:
    lengths = [0.0]
    for i in range(1, len(points)):
        prev = points[i - 1]
        cur = points[i]
        lengths.append(lengths[-1] + math.hypot(cur.x - prev.x, cur.y - prev.y))
    return lengths


def _resample_closed_polyline(points: Sequence[Point2D], sample_count: int) -> List[Point2D]:
    if sample_count <= 0 or len(points) < 2:
        return list(points)
    lengths = _cumulative_lengths(points)
    total_length = lengths[-1]
    if total_length <= 0:
        return [Point2D(pt.x, pt.y) for pt in points[:sample_count]]
    result: List[Point2D] = []
    target_step = total_length / sample_count
    target = 0.0
    idx = 0
    for _ in range(sample_count):
        while idx < len(points) - 1 and lengths[idx + 1] < target:
            idx += 1
        if idx >= len(points) - 1:
            idx = len(points) - 2
        start_pt = points[idx]
        end_pt = points[idx + 1]
        seg_len = lengths[idx + 1] - lengths[idx]
        t = 0.0 if seg_len == 0 else (target - lengths[idx]) / seg_len
        result.append(
            Point2D(
                start_pt.x + (end_pt.x - start_pt.x) * t,
                start_pt.y + (end_pt.y - start_pt.y) * t,
            )
        )
        target += target_step
    return result


def _project_point_to_polyline(point: Point2D, polyline: Sequence[Point2D]) -> Point2D:
    best_point = polyline[0]
    best_dist_sq = float("inf")
    for i in range(1, len(polyline)):
        a = polyline[i - 1]
        b = polyline[i]
        candidate = _project_point_to_segment(point, a, b)
        dist_sq = (candidate.x - point.x) ** 2 + (candidate.y - point.y) ** 2
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_point = candidate
    return best_point


def _project_point_to_segment(p: Point2D, a: Point2D, b: Point2D) -> Point2D:
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    abx = bx - ax
    aby = by - ay
    denom = abx * abx + aby * aby
    if denom == 0:
        return Point2D(ax, ay)
    t = ((p.x - ax) * abx + (p.y - ay) * aby) / denom
    t = max(0.0, min(1.0, t))
    return Point2D(ax + abx * t, ay + aby * t)
