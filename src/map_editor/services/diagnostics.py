"""Diagnostics utilities for map bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from PySide6.QtGui import QImage

from map_editor.models.map_bundle import MapBundle, MapMetadata


@dataclass(frozen=True)
class DiagnosticIssue:
    """A single diagnostic issue discovered when analysing a map bundle."""

    severity: str  # "info", "warning", "error"
    message: str


@dataclass(frozen=True)
class DiagnosticsReport:
    """Aggregate diagnostics for a map bundle."""

    image_size: tuple[int, int]
    map_dimensions_m: tuple[float, float]
    metadata: MapMetadata
    issues: List[DiagnosticIssue] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity in {"warning", "error"} for issue in self.issues)


def analyse_bundle(bundle: MapBundle) -> DiagnosticsReport:
    """Run basic diagnostics against the supplied bundle."""
    width_px, height_px = _read_image_dimensions(bundle.image_path)
    map_width_m = width_px * bundle.metadata.resolution
    map_height_m = height_px * bundle.metadata.resolution

    issues: List[DiagnosticIssue] = []

    _append_metadata_checks(bundle.metadata, issues)
    _append_origin_checks(bundle.metadata, map_width_m, map_height_m, issues)

    issues.append(
        DiagnosticIssue(
            severity="info",
            message=(
                f"Image size {width_px}×{height_px} px (~{map_width_m:.2f}×{map_height_m:.2f} m)"
            ),
        )
    )

    return DiagnosticsReport(
        image_size=(width_px, height_px),
        map_dimensions_m=(map_width_m, map_height_m),
        metadata=bundle.metadata,
        issues=issues,
    )


def _read_image_dimensions(image_path: Path) -> tuple[int, int]:
    image = QImage(str(image_path))
    if image.isNull():
        return 0, 0
    return image.width(), image.height()


def _append_metadata_checks(metadata: MapMetadata, issues: List[DiagnosticIssue]) -> None:
    if metadata.resolution <= 0:
        issues.append(
            DiagnosticIssue(
                severity="error",
                message="Resolution must be positive.",
            )
        )
    elif metadata.resolution > 0.5:
        issues.append(
            DiagnosticIssue(
                severity="warning",
                message=f"Resolution {metadata.resolution:.3f} m/pixel is high; map detail may be coarse.",
            )
        )

    if not (0.0 <= metadata.free_thresh <= 1.0):
        issues.append(
            DiagnosticIssue(
                severity="error",
                message="free_thresh must be between 0 and 1.",
            )
        )
    if not (0.0 <= metadata.occupied_thresh <= 1.0):
        issues.append(
            DiagnosticIssue(
                severity="error",
                message="occupied_thresh must be between 0 and 1.",
            )
        )
    if metadata.free_thresh >= metadata.occupied_thresh:
        issues.append(
            DiagnosticIssue(
                severity="warning",
                message="free_thresh >= occupied_thresh; occupancy classification may be ambiguous.",
            )
        )


def _append_origin_checks(
    metadata: MapMetadata,
    map_width_m: float,
    map_height_m: float,
    issues: List[DiagnosticIssue],
) -> None:
    if map_width_m == 0 or map_height_m == 0:
        issues.append(
            DiagnosticIssue(
                severity="warning",
                message="Image failed to load; diagnostics limited.",
            )
        )
        return

    max_extent = max(map_width_m, map_height_m)
    if abs(metadata.origin_x) > max_extent * 5:
        issues.append(
            DiagnosticIssue(
                severity="warning",
                message=(
                    f"Origin X ({metadata.origin_x:.2f} m) is far from map centre (~±{max_extent:.2f} m)."
                ),
            )
        )
    if abs(metadata.origin_y) > max_extent * 5:
        issues.append(
            DiagnosticIssue(
                severity="warning",
                message=(
                    f"Origin Y ({metadata.origin_y:.2f} m) is far from map centre (~±{max_extent:.2f} m)."
                ),
            )
        )

