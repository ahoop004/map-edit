"""Integration test for annotation commands, undo, and YAML round-trip."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication

from map_editor.commands import (
    AddSpawnPointCommand,
    AnnotationContext,
    SetCenterlineCommand,
    SetStartFinishLineCommand,
)
from map_editor.models.annotations import LineSegment, MapAnnotations, Point2D, Pose2D, SpawnPoint, StartFinishLine
from map_editor.models.map_bundle import MapBundle, MapMetadata
from map_editor.services.map_loader import MapBundleLoader


def test_annotation_commands_round_trip(tmp_path: Path):
    # Ensure a QApplication exists
    app = QApplication.instance() or QApplication([])
    _ = app  # silence lint

    image_path = tmp_path / "track.png"
    from PySide6.QtGui import QImage

    img = QImage(10, 10, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    img.save(str(image_path), "PNG")

    metadata = MapMetadata(
        resolution=0.05,
        origin_x=0.0,
        origin_y=0.0,
        origin_theta=0.0,
        occupied_thresh=0.65,
        free_thresh=0.196,
    )

    annotations = MapAnnotations()
    applied_annotations = annotations

    context = AnnotationContext(
        annotations=applied_annotations,
        on_annotations_changed=lambda ann: None,
    )

    undo_stack = QUndoStack()

    spawn = SpawnPoint(name="spawn_1", pose=Pose2D(1.0, 2.0, 0.0))
    undo_stack.push(AddSpawnPointCommand(context, spawn))
    assert len(applied_annotations.spawn_points) == 1

    start_finish = StartFinishLine(LineSegment(start=Point2D(0.0, 0.0), end=Point2D(3.0, 0.0)))
    undo_stack.push(SetStartFinishLineCommand(context, start_finish))
    assert applied_annotations.start_finish_line == start_finish

    centerline_points = [Point2D(0.0, 0.0), Point2D(1.0, 0.2), Point2D(2.0, 0.0)]
    undo_stack.push(SetCenterlineCommand(context, centerline_points))
    assert applied_annotations.centerline == centerline_points

    undo_stack.undo()  # remove centerline
    assert applied_annotations.centerline == []
    undo_stack.undo()  # remove start/finish line
    assert applied_annotations.start_finish_line is None

    undo_stack.redo()  # restore start/finish line
    assert applied_annotations.start_finish_line == start_finish
    undo_stack.redo()  # restore centerline
    assert applied_annotations.centerline == centerline_points

    bundle = MapBundle(
        image_path=image_path,
        yaml_path=None,
        metadata=metadata,
        annotations=applied_annotations,
    )

    loader = MapBundleLoader(search_image=False)
    yaml_path = tmp_path / "track.yaml"
    loader.save_bundle(bundle, destination=yaml_path, create_backup=False)

    result = loader.load_from_yaml(yaml_path)
    loaded = result.bundle

    assert loaded.metadata == metadata
    assert loaded.annotations.start_finish_line == start_finish
    assert loaded.annotations.spawn_points == applied_annotations.spawn_points
    assert loaded.annotations.centerline == []
