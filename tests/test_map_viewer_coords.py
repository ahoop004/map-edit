"""Unit tests for MapViewer coordinate conversions."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from map_editor.models.map_bundle import MapMetadata
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
