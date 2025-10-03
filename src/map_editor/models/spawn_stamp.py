"""Configuration model for spawn stamp placement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpawnStampSettings:
    """User-configurable options for stamp-based spawn placement."""

    enabled: bool = False
    count: int = 4
    longitudinal_spacing: float = 0.7  # meters between cars along heading
    lateral_spacing: float = 0.35  # meters between opposing rows
    auto_align_radius: float = 1.0  # meters from centerline to trigger auto orientation


MAX_STAMP_COUNT = 20


__all__ = ["SpawnStampSettings", "MAX_STAMP_COUNT"]
