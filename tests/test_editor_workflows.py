"""Regression coverage for map scaling, bundle export, and point reordering."""

from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from map_editor.commands import AddSpawnPointCommand, SetCenterlineCommand
from map_editor.models.annotations import MapAnnotations, Point2D, Pose2D, SpawnPoint, LineSegment, StartFinishLine
from map_editor.models.map_bundle import MapBundle, MapMetadata
from map_editor.services.map_loader import MapBundleLoader, MapBundleLoadResult
from map_editor.services.track_metrics import TrackWidthProfile, TrackWidthSample
from map_editor.ui.centerline_editor import CenterlineEditorDialog
from map_editor.ui.main_window import MainWindow


@pytest.fixture
def window(qapp, tmp_path):
    folder = tmp_path / "track"
    folder.mkdir()
    image_path = folder / "track.png"
    image = QImage(100, 100, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(image_path))
    bundle = MapBundle(image_path, None, MapMetadata.default(), MapAnnotations(
        centerline=[Point2D(1, 1), Point2D(2, 1)],
        start_finish_line=StartFinishLine(LineSegment(Point2D(1, 0), Point2D(1, 2))),
    ), negate=0, extra_fields={"custom": "preserved"})
    window = MainWindow()
    window._apply_loaded_bundle(MapBundleLoadResult(bundle))
    yield window
    window.close()


def test_scale_undo_redo_with_surrounding_annotation_edits(window, tmp_path):
    spawn = SpawnPoint("spawn", Pose2D(1, 1, 0.5))
    window._undo_stack.push(AddSpawnPointCommand(window._annotation_context, spawn))
    original = window._current_bundle
    original_spacing = window._centerline_spacing
    window._track_width_target = 2
    window._track_width_profile = TrackWidthProfile([TrackWidthSample(0, 1, 0.5, 0.5)])
    window._auto_scale_track_width()
    scaled = window._current_bundle
    assert scaled.metadata.resolution == original.metadata.resolution * 2
    assert scaled.annotations.centerline == [Point2D(2, 2), Point2D(4, 2)]
    assert scaled.annotations.spawn_points == [SpawnPoint("spawn", Pose2D(2, 2, 0.5))]
    assert scaled.annotations.start_finish_line.segment.end == Point2D(2, 4)
    assert window._centerline_spacing == original_spacing * 2

    edited_points = [Point2D(3, 3), Point2D(5, 3)]
    window._undo_stack.push(SetCenterlineCommand(window._annotation_context, edited_points))
    # Saving after scaling must not cause undo to restore a stale YAML path.
    saved_path = tmp_path / "saved.yaml"
    window._current_bundle = window._current_bundle.with_yaml_path(saved_path)
    window._save_map_bundle()
    window._undo_stack.undo()  # Centerline edit.
    assert window._current_bundle.annotations.centerline == [Point2D(2, 2), Point2D(4, 2)]
    window._undo_stack.undo()  # Scale.
    assert window._current_bundle.metadata == original.metadata
    assert window._current_bundle.annotations is original.annotations
    assert window._current_bundle.yaml_path == saved_path
    assert window._centerline_spacing == original_spacing
    window._undo_stack.undo()  # Spawn edit before scaling.
    assert window._current_bundle.annotations.spawn_points == []
    window._undo_stack.redo()
    assert window._current_bundle.annotations.spawn_points == [spawn]
    window._undo_stack.redo()
    assert window._current_bundle.metadata == scaled.metadata
    assert window._current_bundle.annotations is scaled.annotations
    assert window._centerline_spacing == original_spacing * 2
    window._undo_stack.redo()
    assert window._current_bundle.annotations.centerline == edited_points
    assert window._current_bundle.extra_fields == {"custom": "preserved"}


@pytest.mark.parametrize("in_place", [False, True])
def test_export_bundle_is_reopenable(window, tmp_path, in_place):
    source = window._current_bundle.image_path
    original_bytes = source.read_bytes()
    destination = source.parent if in_place else tmp_path / "export"
    target = window._run_export_bundle_assets(destination, show_result=False)
    assert target is not None
    loaded = MapBundleLoader(search_image=False).load_from_yaml(target).bundle
    assert loaded.image_path.parent == target.parent
    assert loaded.image_path.read_bytes() == original_bytes
    assert source.read_bytes() == original_bytes
    assert loaded.extra_fields == {"custom": "preserved"}
    assert (target.parent / "track.pgm").exists()
    assert (target.parent / "track_centerline.csv").exists()


@pytest.mark.parametrize("row,delta,expected", [(0, 1, [2, 1, 3]), (2, -1, [1, 3, 2])])
def test_reorder_centerline(qapp, row, delta, expected):
    dialog = CenterlineEditorDialog([Point2D(x, 0) for x in [1, 2, 3]])
    dialog._table.selectRow(row)
    dialog._move_selected(delta)
    assert [point.x for point in dialog.points()] == expected
    assert dialog._selected_row() == row + delta
