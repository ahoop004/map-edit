"""Regression coverage for editing, scene replacement, and unsaved changes."""

import math
import threading
from dataclasses import replace

import pytest
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from map_editor.commands import AddSpawnPointCommand
from map_editor.models.annotations import MapAnnotations, Point2D, Pose2D, SpawnPoint
from map_editor.models.map_bundle import MapBundle, MapMetadata
from map_editor.services.map_loader import MapBundleLoadResult
from map_editor.services.track_metrics import TrackWidthProfile, TrackWidthSample
from map_editor.services.wall_extraction import WallExtractionError, extract_walls
from map_editor.ui.centerline_editor import CenterlineEditorDialog
from map_editor.ui.main_window import MainWindow
from map_editor.ui.map_viewer import MapViewer
from map_editor.ui.metadata_panel import MapMetadataPanel
from map_editor.ui.progress import run_in_thread


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bundle(tmp_path, app):
    image_path = tmp_path / "track.png"
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    assert image.save(str(image_path))
    return MapBundle(image_path, None, MapMetadata.default(), MapAnnotations())


@pytest.fixture
def window(app, bundle):
    window = MainWindow()
    window._apply_loaded_bundle(MapBundleLoadResult(bundle))
    yield window
    window.setWindowModified(False)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_centerline_move_both_directions_and_preserve_precision(app):
    points = [Point2D(0.123456789, 1.0), Point2D(2.0, 3.0), Point2D(4.0, 5.0)]
    dialog = CenterlineEditorDialog(points)
    assert dialog._remove_button.isEnabled()
    assert not dialog._move_up_button.isEnabled()
    dialog._move_selected(1)
    assert dialog.points() == [points[1], points[0], points[2]]
    assert dialog._selected_row() == 1
    dialog._move_selected(-1)
    assert dialog.points() == points


@pytest.mark.parametrize("invalid", ["oops", "nan", "inf", ""])
def test_invalid_centerline_cannot_be_accepted_or_smoothed(app, monkeypatch, invalid):
    dialog = CenterlineEditorDialog([Point2D(1, 2), Point2D(3, 4), Point2D(5, 6)])
    dialog._table.item(1, 0).setText(invalid)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    dialog.accept()
    dialog._smooth()
    assert dialog.result() == 0
    assert dialog._table.rowCount() == 3
    assert len(warnings) == 2


@pytest.mark.parametrize("mode", ["spawn", "centerline"])
@pytest.mark.parametrize("clear", [False, True])
def test_scene_replacement_with_active_previews(app, bundle, mode, clear):
    viewer = MapViewer()
    assert viewer.set_map_image(bundle.image_path)
    viewer.set_metadata(bundle.metadata)
    viewer.set_diagnostic_highlight(True, True)
    if mode == "spawn":
        viewer.begin_spawn_placement()
        viewer._update_spawn_preview([Pose2D(1, 1, 0)])
    else:
        viewer.begin_centerline_placement()
        viewer._centerline_temp_points.append(Point2D(1, 1))
        viewer._update_centerline_preview()
    if clear:
        viewer.clear_map()
        viewer.set_diagnostic_highlight(True, True)
        assert not viewer.has_map
    else:
        assert viewer.set_map_image(bundle.image_path)
        viewer.update_annotations(MapAnnotations())
    assert viewer.placement_mode() is MapViewer.PlacementMode.IDLE
    assert not viewer._centerline_preview_items
    assert not viewer._spawn_preview_polygons


def test_failed_image_load_keeps_current_map(app, bundle):
    viewer = MapViewer()
    viewer.set_map_image(bundle.image_path)
    original = viewer._pixmap_item
    assert not viewer.set_map_image(bundle.image_path.with_name("missing.png"))
    assert viewer._pixmap_item is original
    assert viewer.has_map


def test_right_click_cancels_centerline(app, bundle):
    viewer = MapViewer()
    viewer.set_map_image(bundle.image_path)
    viewer.set_metadata(bundle.metadata)
    viewer.begin_centerline_placement()
    viewer._centerline_temp_points.extend([Point2D(1, 1), Point2D(2, 2)])
    completed = []
    viewer.centerlinePlacementFinished.connect(completed.append)
    QTest.mouseClick(viewer.viewport(), Qt.MouseButton.RightButton)
    assert viewer.placement_mode() is MapViewer.PlacementMode.IDLE
    assert not completed


def test_unsaved_changes_follow_undo_save_and_metadata(window, tmp_path, monkeypatch):
    assert not window.isWindowModified()
    window._undo_stack.push(AddSpawnPointCommand(
        window._annotation_context, SpawnPoint("spawn_1", Pose2D(1, 2))
    ))
    assert window.isWindowModified()
    window._undo_stack.undo()
    assert not window.isWindowModified()
    window._undo_stack.redo()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "track.yaml"), ""))
    assert window._save_map_bundle()
    assert not window.isWindowModified()
    window._undo_stack.undo()
    assert window.isWindowModified()
    window._undo_stack.redo()
    assert not window.isWindowModified()
    window._handle_metadata_changed(replace(window._current_bundle.metadata, resolution=0.1))
    assert window.isWindowModified()


def test_close_cancel_and_cancelled_save_preserve_edits(window, monkeypatch):
    window._handle_metadata_changed(replace(window._current_bundle.metadata, resolution=0.1))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Cancel)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    assert not window._confirm_discard_changes()
    assert window.isWindowModified()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Discard)
    assert window._confirm_discard_changes()


def test_switching_placement_resets_finish_button(window):
    window._start_centerline_placement()
    assert window._annotation_panel._place_button.text() == "Finish"
    window._add_spawn_point()
    assert window._annotation_panel._place_button.text() == "Place…"
    assert window._map_viewer.hasMouseTracking()


def test_worker_keeps_event_loop_responsive_and_propagates_errors(app, monkeypatch):
    monkeypatch.delenv("MAP_EDITOR_BACKGROUND_TASKS", raising=False)
    released = threading.Event()
    QTimer.singleShot(10, released.set)
    assert run_in_thread(lambda: released.wait(timeout=1))
    for _ in range(20):
        assert run_in_thread(lambda: 42) == 42
    with pytest.raises(ValueError, match="worker failed"):
        run_in_thread(lambda: (_ for _ in ()).throw(ValueError("worker failed")))


def test_export_into_existing_map_folder(window, bundle):
    target = window._run_export_bundle_assets(bundle.image_path.parent, show_result=False)
    assert target is not None
    loaded = window._bundle_loader.load_from_yaml(target).bundle
    assert loaded.image_path.parent == target.parent
    # The second export copies an image onto itself; this must remain usable.
    window._apply_loaded_bundle(MapBundleLoadResult(loaded))
    assert window._run_export_bundle_assets(target.parent, show_result=False) == target


def test_metadata_edit_preserves_untouched_precision_and_range(app):
    metadata = replace(MapMetadata.default(), resolution=0.00001234, origin_x=12345.678901)
    panel = MapMetadataPanel()
    panel.set_metadata(metadata)
    panel._free_thresh.setValue(0.2)
    assert panel.metadata() == replace(metadata, free_thresh=0.2)


def test_initial_map_fit_survives_window_layout(window, app):
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    viewer = window._map_viewer
    displayed = viewer.mapFromScene(viewer._pixmap_item.sceneBoundingRect()).boundingRect()
    assert min(displayed.width(), displayed.height()) > 300
    assert window.width() == 1000
    assert window.height() == 700


def test_scaling_discards_commands_bound_to_old_coordinates(window):
    window._undo_stack.push(AddSpawnPointCommand(
        window._annotation_context, SpawnPoint("spawn_1", Pose2D(1, 2))
    ))
    window._track_width_profile = TrackWidthProfile([TrackWidthSample(0, 1.1, 0.55, 0.55)])
    window._auto_scale_track_width()
    assert window._current_bundle.annotations.spawn_points[0].pose == Pose2D(2, 4)
    assert window.isWindowModified()
    assert not window._undo_stack.canUndo()
    window._undo_stack.push(AddSpawnPointCommand(
        window._annotation_context, SpawnPoint("spawn_2", Pose2D(3, 4))
    ))
    window._undo_stack.undo()
    assert window._current_bundle.annotations.spawn_points[0].pose == Pose2D(2, 4)


def test_centerline_generation_reports_extraction_failure(window, monkeypatch):
    def fail(*args, **kwargs):
        raise WallExtractionError("missing image")
    monkeypatch.setattr("map_editor.ui.main_window.extract_walls", fail)
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args))
    window._generate_centerline_from_walls()
    assert len(errors) == 1
    assert "missing image" in errors[0][-1]
    assert window._current_bundle.annotations.centerline == []


def test_rotated_map_coordinates_match_display_and_extracted_walls(app, bundle):
    metadata = replace(bundle.metadata, origin_x=10, origin_y=20, origin_theta=math.pi / 2)
    viewer = MapViewer()
    viewer.set_map_image(bundle.image_path)
    viewer.set_metadata(metadata)
    # Pixel (20, 60) is locally (1, 2) metres, rotated to (-2, 1).
    world = viewer._scene_to_world(QPointF(20, 60))
    assert world == pytest.approx((8, 21))
    scene = viewer._world_to_scene(8, 21)
    assert (scene.x(), scene.y()) == pytest.approx((20, 60))
    assert extract_walls(bundle.image_path, metadata).walls == []
    # Negated maps treat this white test image as occupied.
    walls = extract_walls(bundle.image_path, metadata, negate=1).walls
    assert walls
    assert walls[0][0].x == pytest.approx(5)
    assert walls[0][0].y == pytest.approx(20)
