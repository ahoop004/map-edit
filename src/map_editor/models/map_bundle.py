"""Aggregated map bundle data structure."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from map_editor.models.annotations import MapAnnotations


@dataclass(frozen=True)
class MapMetadata:
    """Core ROS map YAML metadata values."""

    resolution: float
    origin_x: float
    origin_y: float
    origin_theta: float
    occupied_thresh: float
    free_thresh: float

    @classmethod
    def default(cls) -> "MapMetadata":
        """Return sensible defaults for new maps."""
        return cls(
            resolution=0.05,
            origin_x=0.0,
            origin_y=0.0,
            origin_theta=0.0,
            occupied_thresh=0.65,
            free_thresh=0.196,
        )

    def with_origin(self, x: float, y: float) -> "MapMetadata":
        return replace(self, origin_x=x, origin_y=y)

    def with_origin_theta(self, theta: float) -> "MapMetadata":
        return replace(self, origin_theta=theta)

    def pixel_to_world(self, x: float, y: float, image_height: float) -> tuple[float, float]:
        """Convert image coordinates (Y down) to the rotated map frame."""
        local_x = x * self.resolution
        local_y = (image_height - y) * self.resolution
        cosine, sine = math.cos(self.origin_theta), math.sin(self.origin_theta)
        return (
            self.origin_x + cosine * local_x - sine * local_y,
            self.origin_y + sine * local_x + cosine * local_y,
        )

    def world_to_pixel(self, x: float, y: float, image_height: float) -> tuple[float, float]:
        """Invert the map transform for annotation display and placement."""
        dx, dy = x - self.origin_x, y - self.origin_y
        cosine, sine = math.cos(self.origin_theta), math.sin(self.origin_theta)
        return (
            (cosine * dx + sine * dy) / self.resolution,
            image_height - (-sine * dx + cosine * dy) / self.resolution,
        )


@dataclass
class MapBundle:
    """Bundle tying together the bitmap, YAML metadata, and annotations."""

    image_path: Path
    yaml_path: Path | None
    metadata: MapMetadata
    annotations: MapAnnotations
    negate: int = 0
    extra_fields: dict[str, Any] = field(default_factory=dict)

    def with_metadata(self, metadata: MapMetadata) -> "MapBundle":
        """Return a copy with updated metadata."""
        return replace(self, metadata=metadata)

    def with_annotations(self, annotations: MapAnnotations) -> "MapBundle":
        return replace(self, annotations=annotations)

    def with_yaml_path(self, yaml_path: Path) -> "MapBundle":
        return replace(self, yaml_path=yaml_path)

    @property
    def stem(self) -> str:
        """Base filename stem shared by the map bundle."""
        return self.image_path.stem


__all__ = ["MapMetadata", "MapBundle"]
