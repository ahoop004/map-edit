"""Annotation data structures for racetrack features."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class Point2D:
    """Cartesian point in map coordinates (meters)."""

    x: float
    y: float


@dataclass(frozen=True)
class Pose2D:
    """Pose with heading in radians."""

    x: float
    y: float
    theta: float = 0.0


@dataclass(frozen=True)
class LineSegment:
    """Simple line segment defined by two endpoints."""

    start: Point2D
    end: Point2D


@dataclass(frozen=True)
class StartFinishLine:
    """Start/finish line represented as a line segment."""

    segment: LineSegment


@dataclass
class SpawnPoint:
    """Starting grid position for an agent."""

    name: str
    pose: Pose2D


@dataclass
class MapAnnotations:
    """Container for map-level annotations."""

    start_finish_line: Optional[StartFinishLine] = None
    spawn_points: List[SpawnPoint] = field(default_factory=list)
    centerline: List[Point2D] = field(default_factory=list)

    def replace_spawn_points(self, points: Iterable[SpawnPoint]) -> None:
        """Replace the spawn point list in-place."""
        self.spawn_points = list(points)

    def clear(self) -> None:
        """Remove all annotations."""
        self.start_finish_line = None
        self.spawn_points.clear()
        self.centerline.clear()


__all__ = [
    "Point2D",
    "Pose2D",
    "LineSegment",
    "StartFinishLine",
    "SpawnPoint",
    "MapAnnotations",
]
