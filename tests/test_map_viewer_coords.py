"""Unit tests for MapViewer coordinate conversions."""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication

from map_editor.models.annotations import Point2D
from map_editor.models.map_bundle import MapMetadata
from map_editor.models.spawn_stamp import SpawnStampSettings
from map_editor.ui.map_viewer import MapViewer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
app = QApplication.instance() or QApplication([])


def test_world_scene_round_trip():
    viewer = MapViewer()
    metadata = MapMetadata(
        resolution=0.05,
        origin_x=-10.0,
        origin_y=-5.0,
        origin_theta=0.0,
        occupied_thresh=0.65,
        free_thresh=0.196,
    )
    viewer.set_metadata(metadata)
    viewer._pixmap_height = 400.0  # simulate 20 m tall image

    world_point = (-9.5, -4.0)
    scene_point = viewer._world_to_scene(*world_point)
    round_trip = viewer._scene_to_world(scene_point)

    assert round_trip is not None
    assert abs(round_trip[0] - world_point[0]) < 1e-6
    assert abs(round_trip[1] - world_point[1]) < 1e-6


def test_spawn_vehicle_polygon_scales_with_resolution():
    viewer = MapViewer()
    metadata = MapMetadata(
        resolution=0.1,
        origin_x=0.0,
        origin_y=0.0,
        origin_theta=0.0,
        occupied_thresh=0.65,
        free_thresh=0.196,
    )
    viewer.set_metadata(metadata)
    viewer._pixmap_height = 500.0

    polygon = viewer._spawn_vehicle_polygon(2.0, 3.0, 0.0)
    xs = [point.x() for point in polygon]
    ys = [point.y() for point in polygon]
    length_pixels = max(xs) - min(xs)
    width_pixels = max(ys) - min(ys)

    expected_length_pixels = MapViewer._CAR_LENGTH_M / metadata.resolution
    expected_width_pixels = MapViewer._CAR_WIDTH_M / metadata.resolution

    assert length_pixels == pytest.approx(expected_length_pixels, rel=1e-6)
    assert width_pixels == pytest.approx(expected_width_pixels, rel=1e-6)


def test_spawn_vehicle_polygon_visible_without_metadata():
    viewer = MapViewer()
    viewer._pixmap_height = 500.0

    polygon = viewer._spawn_vehicle_polygon(0.0, 0.0, 0.0)
    xs = [point.x() for point in polygon]
    ys = [point.y() for point in polygon]

    assert max(xs) - min(xs) > 0.0
    assert max(ys) - min(ys) > 0.0


def test_generate_stamp_poses_produces_columns_with_remainder():
    viewer = MapViewer()
    viewer.set_spawn_stamp_settings(
        SpawnStampSettings(enabled=True, count=5, longitudinal_spacing=1.0, lateral_spacing=0.4)
    )
    viewer._spawn_stamp_active = True

    poses = viewer._generate_stamp_poses(0.0, 0.0, 0.0)

    assert len(poses) == 5
    # Column spacing along +x axis
    assert poses[2].x == pytest.approx(1.0)
    # Remainder goes to the final column on the left lane
    assert poses[-1].y > 0
    # Rows straddle equally around 0 within tolerance
    assert poses[0].y == pytest.approx(-poses[1].y)


def test_closest_centerline_frame_projects_to_segment():
    viewer = MapViewer()
    viewer._annotations_cache.centerline = [
        Point2D(0.0, 0.0),
        Point2D(5.0, 0.0),
    ]

    result = viewer._closest_centerline_frame(1.0, 1.0)
    assert result is not None
    proj_x, proj_y, theta, distance = result
    assert proj_y == pytest.approx(0.0)
    assert proj_x == pytest.approx(1.0)
    assert theta == pytest.approx(0.0)
    assert distance == pytest.approx(1.0)
