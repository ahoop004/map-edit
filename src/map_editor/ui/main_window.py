"""Main window definition for the map editor."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QWidget,
)
from PySide6.QtGui import QUndoStack

from map_editor.commands import (
    AddSpawnPointCommand,
    AnnotationContext,
    DeleteSpawnPointCommand,
    SetStartFinishLineCommand,
    UpdateSpawnPointCommand,
)
from map_editor.models.annotations import (
    LineSegment,
    MapAnnotations,
    Point2D,
    Pose2D,
    SpawnPoint,
    StartFinishLine,
)
from map_editor.models.map_bundle import MapBundle, MapMetadata
from map_editor.ui.annotation_panel import AnnotationPanel, SpawnPointDialog, StartFinishDialog
from map_editor.ui.map_viewer import MapViewer
from map_editor.ui.metadata_panel import MapMetadataPanel
from map_editor.services.map_loader import MapBundleLoader
from map_editor.services.yaml_serializer import MapYamlError


class MainWindow(QMainWindow):
    """Top-level window that hosts the map canvas and editor panels."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ROS Map Editor")
        self.resize(1280, 720)

        self._current_map: Optional[Path] = None
        self._current_bundle: Optional[MapBundle] = None
        self._bundle_loader = MapBundleLoader()
        self._map_viewer = MapViewer(self)
        self._metadata_panel = MapMetadataPanel(self)
        self._annotation_panel = AnnotationPanel(self)
        self._undo_stack = QUndoStack(self)
        self._annotation_context: Optional[AnnotationContext] = None

        self._init_status_bar()
        self._init_central_widget()
        self._create_actions()
        self._create_menus()
        self._create_docks()
        self._connect_viewer_signals()

    def _init_status_bar(self) -> None:
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

    def _init_central_widget(self) -> None:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._map_viewer)
        self.setCentralWidget(container)

    def _create_actions(self) -> None:
        self._action_open = QAction("&Open Map…", self)
        self._action_open.setShortcut("Ctrl+O")
        self._action_open.triggered.connect(self._select_map_bundle)

        self._action_save = QAction("&Save Map", self)
        self._action_save.setShortcut("Ctrl+S")
        self._action_save.triggered.connect(self._save_map_bundle)
        self._action_save.setEnabled(False)

        self._action_exit = QAction("E&xit", self)
        self._action_exit.setShortcut("Ctrl+Q")
        self._action_exit.triggered.connect(self.close)

        self._action_undo = self._undo_stack.createUndoAction(self, "&Undo")
        self._action_undo.setShortcut("Ctrl+Z")
        self._action_redo = self._undo_stack.createRedoAction(self, "&Redo")
        self._action_redo.setShortcut("Ctrl+Shift+Z")

        self._action_add_spawn = QAction("Add Spawn Point", self)
        self._action_add_spawn.triggered.connect(self._add_spawn_point)

        self._action_edit_spawn = QAction("Edit Selected Spawn Point", self)
        self._action_edit_spawn.triggered.connect(self._edit_selected_spawn_point)

        self._action_delete_spawn = QAction("Delete Selected Spawn Point", self)
        self._action_delete_spawn.triggered.connect(self._delete_selected_spawn_point)

        self._action_set_start_finish = QAction("Set Start/Finish Line", self)
        self._action_set_start_finish.triggered.connect(self._set_start_finish_line)

        self._action_clear_start_finish = QAction("Clear Start/Finish Line", self)
        self._action_clear_start_finish.triggered.connect(self._clear_start_finish_line)

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self._action_open)
        file_menu.addAction(self._action_save)
        file_menu.addSeparator()
        file_menu.addAction(self._action_exit)

        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction(self._action_undo)
        edit_menu.addAction(self._action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self._action_add_spawn)
        edit_menu.addAction(self._action_edit_spawn)
        edit_menu.addAction(self._action_delete_spawn)
        edit_menu.addSeparator()
        edit_menu.addAction(self._action_set_start_finish)
        edit_menu.addAction(self._action_clear_start_finish)

    def _create_docks(self) -> None:
        metadata_dock = QDockWidget("Metadata", self)
        metadata_dock.setObjectName("metadataDock")
        metadata_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        metadata_dock.setWidget(self._metadata_panel)
        metadata_dock.setMinimumWidth(280)
        metadata_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, metadata_dock)
        self._metadata_panel.metadataChanged.connect(self._handle_metadata_changed)

        annotation_dock = QDockWidget("Annotations", self)
        annotation_dock.setObjectName("annotationDock")
        annotation_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        annotation_dock.setWidget(self._annotation_panel)
        annotation_dock.setMinimumWidth(320)
        annotation_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, annotation_dock)

        self._annotation_panel.addSpawnRequested.connect(self._add_spawn_point)
        self._annotation_panel.editSpawnRequested.connect(self._edit_spawn_point)
        self._annotation_panel.deleteSpawnRequested.connect(self._delete_spawn_point)
        self._annotation_panel.setStartFinishRequested.connect(self._set_start_finish_line)
        self._annotation_panel.clearStartFinishRequested.connect(self._clear_start_finish_line)

    def _connect_viewer_signals(self) -> None:
        self._map_viewer.spawnPlacementCompleted.connect(self._finalize_spawn_point)
        self._map_viewer.startFinishPlacementCompleted.connect(self._finalize_start_finish_line)
        self._map_viewer.placementStatusChanged.connect(self.statusBar().showMessage)
        self._map_viewer.placementCancelled.connect(self._on_viewer_placement_cancelled)

    def _select_map_bundle(self) -> None:
        start_dir = str(self._current_map.parent if self._current_map else Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open map bundle",
            start_dir,
            "ROS map YAML files (*.yaml);;Image files (*.png *.jpg *.jpeg *.bmp);;All files (*)",
        )
        if not file_path:
            return

        selected_path = Path(file_path)
        suffix = selected_path.suffix.lower()

        self._map_viewer.cancel_placement()

        if suffix in {".png", ".jpg", ".jpeg", ".bmp"}:
            if self._map_viewer.set_map_image(selected_path):
                bundle = MapBundle(
                    image_path=selected_path,
                    yaml_path=None,
                    metadata=MapMetadata.default(),
                    annotations=MapAnnotations(),
                )
                self._current_map = selected_path
                self._current_bundle = bundle
                self._map_viewer.set_metadata(bundle.metadata)
                self._metadata_panel.set_metadata(bundle.metadata)
                self._map_viewer.update_annotations(bundle.annotations)
                self._annotation_panel.set_annotations(bundle.annotations)
                self._undo_stack.clear()
                self._refresh_annotation_context()
                self._action_save.setEnabled(True)
                self.statusBar().showMessage(f"Loaded image: {selected_path.name}")
            else:
                QMessageBox.warning(self, "Failed to load image", selected_path.name)
            return

        # Default to YAML handling; full parsing will come later.
        try:
            result = self._bundle_loader.load_from_yaml(selected_path)
        except MapYamlError as exc:
            QMessageBox.critical(self, "Failed to load map", str(exc))
            return

        bundle = result.bundle
        self._current_map = bundle.yaml_path or bundle.image_path
        self._current_bundle = bundle
        self._map_viewer.set_map_image(bundle.image_path)
        self._map_viewer.set_metadata(bundle.metadata)
        self._metadata_panel.set_metadata(bundle.metadata)
        self._map_viewer.update_annotations(bundle.annotations)
        self._annotation_panel.set_annotations(bundle.annotations)
        self._undo_stack.clear()
        self._refresh_annotation_context()
        self._action_save.setEnabled(True)
        message = f"Loaded bundle: {bundle.yaml_path.name}" if bundle.yaml_path else "Loaded bundle"
        if result.warnings:
            message += " (" + "; ".join(result.warnings) + ")"
        self.statusBar().showMessage(message)

    def _save_map_bundle(self) -> None:
        if not self._current_bundle:
            QMessageBox.warning(self, "No map loaded", "Load a map before saving.")
            return

        bundle = self._current_bundle
        if bundle.yaml_path is None:
            suggested_dir = str(bundle.image_path.parent)
            default_name = bundle.image_path.with_suffix(".yaml").name
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save map YAML",
                str(Path(suggested_dir) / default_name),
                "ROS map YAML files (*.yaml);;All files (*)",
            )
            if not file_path:
                return
            bundle = bundle.with_yaml_path(Path(file_path))

        try:
            saved_path = self._bundle_loader.save_bundle(bundle)
        except Exception as exc:  # noqa: BLE001 - surface all errors to the user
            QMessageBox.critical(self, "Failed to save map", str(exc))
            return

        self._current_bundle = bundle
        self._current_map = saved_path
        self._refresh_annotation_context()
        self.statusBar().showMessage(f"Saved: {saved_path.name}")

    def _handle_metadata_changed(self, metadata: MapMetadata) -> None:
        if self._current_bundle is not None:
            self._current_bundle = self._current_bundle.with_metadata(metadata)
        self._map_viewer.set_metadata(metadata)
        if self._current_bundle is not None:
            self._map_viewer.update_annotations(self._current_bundle.annotations)
        self.statusBar().showMessage(
            f"Metadata updated: res={metadata.resolution:.3f}, origin=({metadata.origin_x:.2f}, {metadata.origin_y:.2f})"
        )

    def _refresh_annotation_context(self) -> None:
        if self._current_bundle is None:
            self._annotation_context = None
            self._annotation_panel.set_annotations(MapAnnotations())
            return
        self._annotation_context = AnnotationContext(
            annotations=self._current_bundle.annotations,
            on_annotations_changed=self._handle_annotation_change,
        )
        self._annotation_panel.set_annotations(self._current_bundle.annotations)

    def _handle_annotation_change(self, annotations: MapAnnotations) -> None:
        if self._current_bundle is not None:
            self._current_bundle = self._current_bundle.with_annotations(annotations)
        self._map_viewer.update_annotations(annotations)
        self._annotation_panel.set_annotations(annotations)
        self._action_save.setEnabled(True)
        self.statusBar().showMessage(
            f"Annotations updated (spawn points: {len(annotations.spawn_points)})"
        )

    def _ensure_annotation_context(self) -> Optional[AnnotationContext]:
        if self._annotation_context is None:
            QMessageBox.information(self, "No map", "Load a map before editing annotations.")
            return None
        return self._annotation_context

    def _add_spawn_point(self) -> None:
        if self._annotation_context is None:
            if self._ensure_annotation_context() is None:
                return
        if not self._map_viewer.begin_spawn_placement():
            return

    def _edit_selected_spawn_point(self) -> None:
        index = self._annotation_panel.selected_index()
        if index is None:
            QMessageBox.information(self, "No selection", "Select a spawn point to edit.")
            return
        self._edit_spawn_point(index)

    def _edit_spawn_point(self, index: int) -> None:
        self._map_viewer.cancel_placement()
        context = self._ensure_annotation_context()
        if context is None:
            return
        if not (0 <= index < len(context.annotations.spawn_points)):
            return
        existing = context.annotations.spawn_points[index]
        dialog = SpawnPointDialog(
            self,
            title="Edit Spawn Point",
            default_name=existing.name,
            spawn=existing,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_spawn = dialog.spawn_point()
            self._undo_stack.push(UpdateSpawnPointCommand(context, index, new_spawn))

    def _delete_selected_spawn_point(self) -> None:
        index = self._annotation_panel.selected_index()
        if index is None:
            QMessageBox.information(self, "No selection", "Select a spawn point to delete.")
            return
        self._delete_spawn_point(index)

    def _delete_spawn_point(self, index: int) -> None:
        self._map_viewer.cancel_placement()
        context = self._ensure_annotation_context()
        if context is None:
            return
        if not (0 <= index < len(context.annotations.spawn_points)):
            return
        self._undo_stack.push(DeleteSpawnPointCommand(context, index))

    def _set_start_finish_line(self) -> None:
        if self._annotation_context is None:
            if self._ensure_annotation_context() is None:
                return
        if not self._map_viewer.begin_start_finish_placement():
            return

    def _clear_start_finish_line(self) -> None:
        self._map_viewer.cancel_placement()
        context = self._ensure_annotation_context()
        if context is None:
            return
        self._undo_stack.push(SetStartFinishLineCommand(context, None, "Clear start/finish line"))

    def _on_viewer_placement_cancelled(self) -> None:
        # No additional work required beyond the viewer status message.
        pass

    def _finalize_spawn_point(self, x: float, y: float) -> None:
        context = self._annotation_context
        if context is None:
            return
        next_index = len(context.annotations.spawn_points) + 1
        default_spawn = SpawnPoint(name=f"spawn_{next_index}", pose=Pose2D(x, y, 0.0))
        dialog = SpawnPointDialog(
            self,
            title="Add Spawn Point",
            default_name=default_spawn.name,
            spawn=default_spawn,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            spawn = dialog.spawn_point()
            self._undo_stack.push(AddSpawnPointCommand(context, spawn))
            self.statusBar().showMessage(
                f"Added spawn '{spawn.name}' at ({spawn.pose.x:.2f}, {spawn.pose.y:.2f})."
            )
        else:
            self.statusBar().showMessage("Spawn placement cancelled.")

    def _finalize_start_finish_line(self, sx: float, sy: float, ex: float, ey: float) -> None:
        context = self._annotation_context
        if context is None:
            return
        provisional = StartFinishLine(LineSegment(Point2D(sx, sy), Point2D(ex, ey)))
        dialog = StartFinishDialog(self, line=provisional)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            line = dialog.start_finish_line()
            self._undo_stack.push(SetStartFinishLineCommand(context, line, "Set start/finish line"))
            start = line.segment.start
            end = line.segment.end
            self.statusBar().showMessage(
                f"Start/finish line set from ({start.x:.2f}, {start.y:.2f}) to ({end.x:.2f}, {end.y:.2f})."
            )
        else:
            self.statusBar().showMessage("Start/finish placement cancelled.")
