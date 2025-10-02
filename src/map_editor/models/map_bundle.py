"""Aggregated map bundle data structure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

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


@dataclass
class MapBundle:
    """Bundle tying together the bitmap, YAML metadata, and annotations."""

    image_path: Path
    yaml_path: Optional[Path]
    metadata: MapMetadata
    annotations: MapAnnotations

    def with_metadata(self, metadata: MapMetadata) -> "MapBundle":
        """Return a copy with updated metadata."""
        return MapBundle(self.image_path, self.yaml_path, metadata, self.annotations)

    def with_annotations(self, annotations: MapAnnotations) -> "MapBundle":
        return MapBundle(self.image_path, self.yaml_path, self.metadata, annotations)

    @property
    def stem(self) -> str:
        """Base filename stem shared by the map bundle."""
        return self.image_path.stem


__all__ = ["MapMetadata", "MapBundle"]
