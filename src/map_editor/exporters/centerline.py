"""Export utilities for centerline waypoints."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path as RosPath

from map_editor.models.annotations import Point2D


@dataclass(frozen=True)
class CenterlineSample:
    x: float
    y: float
    theta: float
    velocity: Optional[float] = None


def resample_centerline(points: Iterable[Point2D], spacing: float) -> List[CenterlineSample]:
    """Resample a polyline to roughly `spacing` meters between samples."""
    pts = list(points)
    if len(pts) < 2:
        return []

    samples: List[CenterlineSample] = []
    accumulated = 0.0
    prev = pts[0]
    for idx in range(1, len(pts)):
        current = pts[idx]
        segment_dx = current.x - prev.x
        segment_dy = current.y - prev.y
        segment_length = math.hypot(segment_dx, segment_dy)
        if segment_length == 0:
            continue
        direction = (segment_dx / segment_length, segment_dy / segment_length)
        while accumulated + segment_length >= spacing or not samples:
            if samples:
                overshoot = spacing - accumulated
            else:
                overshoot = 0.0
            t = overshoot / segment_length if segment_length else 0.0
            sample_x = prev.x + direction[0] * overshoot
            sample_y = prev.y + direction[1] * overshoot
            theta = math.atan2(direction[1], direction[0])
            samples.append(CenterlineSample(sample_x, sample_y, theta))
            segment_length -= overshoot
            prev = Point2D(sample_x, sample_y)
            accumulated = 0.0
            if segment_length <= 1e-6:
                break
            direction = (current.x - prev.x, current.y - prev.y)
            length_remaining = math.hypot(direction[0], direction[1])
            if length_remaining == 0:
                break
            direction = (direction[0] / length_remaining, direction[1] / length_remaining)
        accumulated += segment_length
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
    """Write centerline samples to a CSV with columns: x,y,theta[,velocity]."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y", "theta", "velocity"])
        for sample in samples:
            row = [f"{sample.x:.6f}", f"{sample.y:.6f}", f"{sample.theta:.6f}"]
            row.append("" if sample.velocity is None else f"{sample.velocity:.3f}")
            writer.writerow(row)


def centerline_to_ros_path(samples: Iterable[CenterlineSample], frame_id: str = "map") -> RosPath:
    """Convert centerline samples to a nav_msgs/Path message."""
    path_msg = RosPath()
    path_msg.header.frame_id = frame_id
    for index, sample in enumerate(samples):
        pose = PoseStamped()
        pose.header.frame_id = frame_id
        pose.header.seq = index
        pose.pose.position.x = sample.x
        pose.pose.position.y = sample.y
        pose.pose.position.z = 0.0
        qw, qz = _yaw_to_quaternion(sample.theta)
        pose.pose.orientation.w = qw
        pose.pose.orientation.z = qz
        path_msg.poses.append(pose)
    return path_msg


def _yaw_to_quaternion(yaw: float) -> tuple[float, float]:
    half = yaw * 0.5
    return math.cos(half), math.sin(half)
