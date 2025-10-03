"""Utilities for extracting wall contours and deriving centerlines."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

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
                hull = _convex_hull(component)
                if len(hull) >= 3:
                    walls.append([
                        _grid_to_world(px, py, metadata, height) for px, py in hull
                    ])
    walls.sort(key=lambda contour: -_polygon_area(contour))
    return WallExtractionResult(walls=walls, grid_width=width, grid_height=height)


def derive_centerline_from_walls(walls: Sequence[Sequence[Point2D]]) -> List[Point2D]:
    """Rudimentary centerline derived from two largest wall contours."""
    if len(walls) < 2:
        return []
    outer = walls[0]
    inner = walls[1]
    outer_sorted = _sort_points_by_angle(outer)
    inner_sorted = _sort_points_by_angle(inner)
    count = min(len(outer_sorted), len(inner_sorted))
    if count == 0:
        return []
    centerline = []
    for i in range(count):
        op = outer_sorted[i]
        ip = inner_sorted[i]
        centerline.append(Point2D((op.x + ip.x) * 0.5, (op.y + ip.y) * 0.5))
    return centerline


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


def _convex_hull(points: Iterable[tuple[int, int]]) -> List[tuple[int, int]]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[tuple[int, int]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: List[tuple[int, int]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


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
*** End Patch
