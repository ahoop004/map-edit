"""Utilities for computing track width metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from map_editor.models.annotations import Point2D


@dataclass
class TrackWidthSample:
    """Width measurement at a specific point along the centerline."""

    distance: float
    width: Optional[float]
    left: Optional[float]
    right: Optional[float]


@dataclass
class TrackWidthProfile:
    """Collection of width samples with helper statistics."""

    samples: List[TrackWidthSample]

    @property
    def valid_samples(self) -> List[TrackWidthSample]:
        return [sample for sample in self.samples if sample.width is not None]

    @property
    def average_width(self) -> Optional[float]:
        valid = self.valid_samples
        if not valid:
            return None
        return sum(sample.width for sample in valid if sample.width is not None) / len(valid)

    @property
    def minimum_width(self) -> Optional[float]:
        valid = self.valid_samples
        if not valid:
            return None
        return min(sample.width for sample in valid if sample.width is not None)

    @property
    def maximum_width(self) -> Optional[float]:
        valid = self.valid_samples
        if not valid:
            return None
        return max(sample.width for sample in valid if sample.width is not None)


def compute_track_width_profile(
    centerline: Sequence[Point2D], walls: Sequence[Sequence[Point2D]]
) -> TrackWidthProfile:
    """Compute per-point width measurements using the supplied walls."""

    if len(centerline) < 2 or not walls:
        return TrackWidthProfile(samples=[])

    wall_segments = _wall_segments(walls)
    if not wall_segments:
        return TrackWidthProfile(samples=[])

    samples: List[TrackWidthSample] = []
    cumulative_distance = 0.0

    for index, point in enumerate(centerline):
        tangent = _centerline_tangent(centerline, index)
        if tangent is None:
            samples.append(TrackWidthSample(cumulative_distance, None, None, None))
            continue

        normal_x = -tangent[1]
        normal_y = tangent[0]
        normal_len = math.hypot(normal_x, normal_y)
        if normal_len == 0:
            samples.append(TrackWidthSample(cumulative_distance, None, None, None))
            continue
        normal_x /= normal_len
        normal_y /= normal_len

        left = _ray_wall_distance(point, (normal_x, normal_y), wall_segments)
        right = _ray_wall_distance(point, (-normal_x, -normal_y), wall_segments)
        width = None
        if left is not None and right is not None:
            width = left + right

        samples.append(TrackWidthSample(cumulative_distance, width, left, right))

        if index + 1 < len(centerline):
            next_point = centerline[index + 1]
            cumulative_distance += math.hypot(
                next_point.x - point.x,
                next_point.y - point.y,
            )

    return TrackWidthProfile(samples=samples)


def _centerline_tangent(points: Sequence[Point2D], index: int) -> Optional[Tuple[float, float]]:
    if len(points) < 2:
        return None
    if index == 0:
        next_point = points[1]
        dx = next_point.x - points[0].x
        dy = next_point.y - points[0].y
    elif index == len(points) - 1:
        prev_point = points[-2]
        dx = points[-1].x - prev_point.x
        dy = points[-1].y - prev_point.y
    else:
        prev_point = points[index - 1]
        next_point = points[index + 1]
        dx = next_point.x - prev_point.x
        dy = next_point.y - prev_point.y

    length = math.hypot(dx, dy)
    if length == 0:
        return None
    return dx / length, dy / length


def _wall_segments(walls: Sequence[Sequence[Point2D]]) -> List[Tuple[Point2D, Point2D]]:
    segments: List[Tuple[Point2D, Point2D]] = []
    for wall in walls:
        if len(wall) < 2:
            continue
        for start, end in zip(wall[:-1], wall[1:]):
            segments.append((start, end))
    return segments


def _ray_wall_distance(
    origin: Point2D,
    direction: Tuple[float, float],
    segments: Iterable[Tuple[Point2D, Point2D]],
) -> Optional[float]:
    min_distance: Optional[float] = None
    for start, end in segments:
        distance = _ray_segment_intersection(origin, direction, start, end)
        if distance is None:
            continue
        if distance <= 0:
            continue
        if min_distance is None or distance < min_distance:
            min_distance = distance
    return min_distance


def _ray_segment_intersection(
    origin: Point2D,
    direction: Tuple[float, float],
    start: Point2D,
    end: Point2D,
) -> Optional[float]:
    dir_x, dir_y = direction
    seg_dx = end.x - start.x
    seg_dy = end.y - start.y

    denom = dir_x * (-seg_dy) + dir_y * seg_dx
    if abs(denom) < 1e-9:
        return None

    diff_x = start.x - origin.x
    diff_y = start.y - origin.y

    t = (diff_x * (-seg_dy) + diff_y * seg_dx) / denom
    u = (dir_x * diff_y - dir_y * diff_x) / denom

    if t < 0 or u < 0 or u > 1:
        return None
    return t * math.hypot(dir_x, dir_y)


__all__ = [
    "TrackWidthSample",
    "TrackWidthProfile",
    "compute_track_width_profile",
]
