"""YAML parsing and serialization utilities for ROS map bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from map_editor.models.annotations import (
    LineSegment,
    MapAnnotations,
    Point2D,
    Pose2D,
    SpawnPoint,
    StartFinishLine,
)
from map_editor.models.map_bundle import MapMetadata


class MapYamlError(Exception):
    """Raised when the YAML map document fails validation."""


@dataclass
class MapYamlDocument:
    """Structured representation of a ROS map YAML file."""

    yaml_path: Path
    image: str
    metadata: MapMetadata
    annotations: MapAnnotations = field(default_factory=MapAnnotations)
    negate: int = 0
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Convert the document back into a serializable mapping."""
        data: Dict[str, Any] = {
            "image": self.image,
            "resolution": self.metadata.resolution,
            "origin": [
                self.metadata.origin_x,
                self.metadata.origin_y,
                self.metadata.origin_theta,
            ],
            "occupied_thresh": self.metadata.occupied_thresh,
            "free_thresh": self.metadata.free_thresh,
            "negate": self.negate,
        }
        if self.extra_fields:
            data.update(self.extra_fields)

        annotations_dict = _annotations_to_dict(self.annotations)
        if annotations_dict:
            data["annotations"] = annotations_dict

        return data


def load_map_yaml(yaml_path: Path) -> MapYamlDocument:
    """Load and validate a ROS map YAML file."""
    if not yaml_path.exists():
        raise MapYamlError(f"YAML file does not exist: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)

    if not isinstance(parsed, dict):
        raise MapYamlError("Map YAML must be a mapping at the top level")

    try:
        image_value = _expect_str(parsed, "image")
        resolution = _expect_float(parsed, "resolution")
        origin_values = _expect_sequence(parsed, "origin", length=3)
    except KeyError as exc:
        raise MapYamlError(f"Missing required field: {exc.args[0]}") from exc

    metadata = MapMetadata(
        resolution=resolution,
        origin_x=float(origin_values[0]),
        origin_y=float(origin_values[1]),
        origin_theta=float(origin_values[2]),
        occupied_thresh=_expect_float(parsed, "occupied_thresh", default=0.65),
        free_thresh=_expect_float(parsed, "free_thresh", default=0.196),
    )

    negate = int(parsed.get("negate", 0))

    extra_fields = {
        key: value
        for key, value in parsed.items()
        if key
        not in {
            "image",
            "resolution",
            "origin",
            "occupied_thresh",
            "free_thresh",
            "negate",
            "annotations",
        }
    }

    annotations = _parse_annotations(parsed.get("annotations", {}))

    return MapYamlDocument(
        yaml_path=yaml_path,
        image=image_value,
        metadata=metadata,
        annotations=annotations,
        negate=negate,
        extra_fields=extra_fields,
    )


def dump_map_yaml(document: MapYamlDocument, destination: Optional[Path] = None) -> str:
    """Serialize the map document to YAML, optionally writing to disk."""
    data = document.as_dict()
    yaml_text = yaml.safe_dump(data, sort_keys=False)

    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(yaml_text, encoding="utf-8")

    return yaml_text


def _expect_str(mapping: Dict[str, Any], key: str) -> str:
    value = mapping[key]
    if not isinstance(value, str):
        raise MapYamlError(f"Field '{key}' must be a string")
    return value


def _expect_float(mapping: Dict[str, Any], key: str, default: Optional[float] = None) -> float:
    if key not in mapping:
        if default is None:
            raise KeyError(key)
        return float(default)
    value = mapping[key]
    if not isinstance(value, (int, float)):
        raise MapYamlError(f"Field '{key}' must be a number")
    return float(value)


def _expect_sequence(mapping: Dict[str, Any], key: str, length: Optional[int] = None) -> List[Any]:
    if key not in mapping:
        raise KeyError(key)
    value = mapping[key]
    if not isinstance(value, (list, tuple)):
        raise MapYamlError(f"Field '{key}' must be a sequence")
    sequence = list(value)
    if length is not None and len(sequence) < length:
        raise MapYamlError(f"Field '{key}' must contain at least {length} values")
    return sequence


def _parse_annotations(data: Any) -> MapAnnotations:
    annotations = MapAnnotations()
    if not data:
        return annotations
    if not isinstance(data, dict):
        raise MapYamlError("Annotations section must be a mapping")

    start_finish_raw = data.get("start_finish")
    if start_finish_raw is not None:
        annotations.start_finish_line = _parse_start_finish(start_finish_raw)

    spawn_points_raw = data.get("spawn_points", [])
    if spawn_points_raw:
        annotations.replace_spawn_points(_parse_spawn_points(spawn_points_raw))

    centerline_raw = data.get("centerline", [])
    if centerline_raw:
        annotations.centerline = _parse_centerline(centerline_raw)

    return annotations


def _parse_start_finish(raw: Any) -> StartFinishLine:
    if not isinstance(raw, dict):
        raise MapYamlError("start_finish must be a mapping")
    start = _parse_point(raw.get("start"), "start_finish.start")
    end = _parse_point(raw.get("end"), "start_finish.end")
    return StartFinishLine(LineSegment(start=start, end=end))


def _parse_spawn_points(raw: Any) -> Iterable[SpawnPoint]:
    if not isinstance(raw, list):
        raise MapYamlError("spawn_points must be a list")

    result: List[SpawnPoint] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise MapYamlError("Each spawn point must be a mapping")
        name = entry.get("name") or f"spawn_{index + 1}"
        pose_values = entry.get("pose") or entry.get("position")
        if pose_values is None:
            raise MapYamlError(f"Spawn point '{name}' missing pose array")
        pose = _parse_pose(pose_values, f"spawn_points[{index}].pose")
        result.append(SpawnPoint(name=name, pose=pose))
    return result


def _parse_point(raw: Any, field_name: str) -> Point2D:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise MapYamlError(f"{field_name} must be a 2-long array")
    x, y = raw[0], raw[1]
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise MapYamlError(f"{field_name} values must be numeric")
    return Point2D(float(x), float(y))


def _parse_pose(raw: Any, field_name: str) -> Pose2D:
    if not isinstance(raw, (list, tuple)) or len(raw) < 3:
        raise MapYamlError(f"{field_name} must be a 3-long array [x, y, theta]")
    x, y, theta = raw[:3]
    if not all(isinstance(value, (int, float)) for value in (x, y, theta)):
        raise MapYamlError(f"{field_name} values must be numeric")
    return Pose2D(float(x), float(y), float(theta))


def _parse_centerline(raw: Any) -> List[Point2D]:
    if not isinstance(raw, list):
        raise MapYamlError("centerline must be a list of [x, y] points")
    points: List[Point2D] = []
    for index, point in enumerate(raw):
        points.append(_parse_point(point, f"centerline[{index}]"))
    return points


def _annotations_to_dict(annotations: MapAnnotations) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if annotations.start_finish_line is not None:
        payload["start_finish"] = {
            "start": [
                annotations.start_finish_line.segment.start.x,
                annotations.start_finish_line.segment.start.y,
            ],
            "end": [
                annotations.start_finish_line.segment.end.x,
                annotations.start_finish_line.segment.end.y,
            ],
        }
    if annotations.spawn_points:
        payload["spawn_points"] = [
            {
                "name": spawn.name,
                "pose": [spawn.pose.x, spawn.pose.y, spawn.pose.theta],
            }
            for spawn in annotations.spawn_points
        ]
    if annotations.centerline:
        payload["centerline"] = [[point.x, point.y] for point in annotations.centerline]
    return payload


__all__ = ["MapYamlError", "MapYamlDocument", "load_map_yaml", "dump_map_yaml"]
