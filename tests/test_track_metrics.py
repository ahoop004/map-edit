"""Unit tests for track width metric calculations."""

from __future__ import annotations

from map_editor.models.annotations import Point2D
from map_editor.services.track_metrics import compute_track_width_profile


def test_compute_track_width_profile_simple_rectangle():
    centerline = [
        Point2D(0.0, 0.0),
        Point2D(10.0, 0.0),
    ]
    walls = [
        [Point2D(0.0, -1.0), Point2D(10.0, -1.0)],
        [Point2D(0.0, 1.0), Point2D(10.0, 1.0)],
    ]

    profile = compute_track_width_profile(centerline, walls)
    assert len(profile.samples) == 2
    for sample in profile.samples:
        assert sample.width is not None
        assert sample.width == 2.0


def test_compute_track_width_profile_handles_missing_intersections():
    centerline = [Point2D(0.0, 0.0), Point2D(1.0, 0.0)]
    walls = [[Point2D(0.0, 3.0), Point2D(1.0, 3.0)]]  # Only one wall

    profile = compute_track_width_profile(centerline, walls)
    assert len(profile.samples) == 2
    assert profile.samples[0].width is None
    assert profile.average_width is None
