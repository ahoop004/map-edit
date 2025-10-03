"""Main window definition for the map editor."""

from __future__ import annotations

import csv

import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
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
    AddSpawnBatchCommand,
    AddSpawnPointCommand,
    AnnotationContext,
    DeleteSpawnPointCommand,
    SetCenterlineCommand,
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
from map_editor.models.spawn_stamp import SpawnStampSettings
from map_editor.services.diagnostics import DiagnosticsReport, analyse_bundle
from map_editor.exporters.centerline import (
    export_centerline_csv,
    export_centerline_path_yaml,
    resample_centerline,
)
from map_editor.services.wall_extraction import (
    derive_centerline_from_walls,
    export_walls_csv,
    extract_walls,
)
from map_editor.exporters.image import export_png_as_pgm
from map_editor.ui.annotation_panel import AnnotationPanel, SpawnPointDialog, StartFinishDialog
from map_editor.ui.centerline_editor import CenterlineEditorDialog
from map_editor.ui.diagnostics_panel import DiagnosticsPanel
from map_editor.ui.map_viewer import MapViewer
from map_editor.ui.metadata_panel import MapMetadataPanel
from map_editor.services.map_loader import MapBundleLoader, MapBundleLoadResult
from map_editor.services.yaml_serializer import MapYamlError
from map_editor.ui.progress import show_busy_dialog
from map_editor.services.track_metrics import compute_track_width_profile, TrackWidthProfile
from map_editor.ui.track_metrics_panel import TrackMetricsPanel


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
        self._diagnostics_panel = DiagnosticsPanel(self)
        self._track_metrics_panel = TrackMetricsPanel(self)
        self._undo_stack = QUndoStack(self)
        self._annotation_context: Optional[AnnotationContext] = None
        self._diagnostics_report: Optional[DiagnosticsReport] = None
        self._centerline_spacing: float = 0.2
        self._spawn_stamp_settings: SpawnStampSettings = self._annotation_panel.stamp_settings()
        self._track_width_profile: Optional[TrackWidthProfile] = None
        self._track_width_target: float = 2.2

        self._init_status_bar()
        self._init_central_widget()
        self._create_actions()
        self._create_menus()
        self._create_docks()
        self._connect_viewer_signals()
        self._track_metrics_panel.autoScaleRequested.connect(self._auto_scale_track_width)
        self._map_viewer.set_spawn_stamp_settings(self._spawn_stamp_settings)

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
        self._action_add_spawn.setToolTip("Enter placement mode, then left-click on the map to add a spawn point.")

        self._action_edit_spawn = QAction("Edit Selected Spawn Point", self)
        self._action_edit_spawn.triggered.connect(self._edit_selected_spawn_point)
        self._action_edit_spawn.setToolTip("Edit the highlighted spawn point in the annotations list.")

        self._action_delete_spawn = QAction("Delete Selected Spawn Point", self)
        self._action_delete_spawn.triggered.connect(self._delete_selected_spawn_point)
        self._action_delete_spawn.setToolTip("Remove the highlighted spawn point.")

        self._action_set_start_finish = QAction("Set Start/Finish Line", self)
        self._action_set_start_finish.triggered.connect(self._set_start_finish_line)
        self._action_set_start_finish.setToolTip(
            "Enter placement mode, then left-click start and end points for the start/finish line."
        )

        self._action_clear_start_finish = QAction("Clear Start/Finish Line", self)
        self._action_clear_start_finish.triggered.connect(self._clear_start_finish_line)
        self._action_clear_start_finish.setToolTip("Remove the current start/finish line from the map.")

        self._action_place_centerline = QAction("Place Centerline (click to add)", self)
        self._action_place_centerline.triggered.connect(self._start_centerline_placement)
        self._action_place_centerline.setToolTip(
            "Enter centerline placement mode to click points directly on the map."
        )
        self._action_import_centerline = QAction("Import Centerline CSV…", self)
        self._action_import_centerline.triggered.connect(self._import_centerline_csv)
        self._action_import_centerline.setToolTip("Load centerline nodes from a CSV file (x,y[,theta]).")

        self._action_edit_centerline = QAction("Edit Centerline…", self)
        self._action_edit_centerline.triggered.connect(self._edit_centerline)
        self._action_edit_centerline.setToolTip("Open the centerline editor to add or adjust nodes.")

        self._action_clear_centerline = QAction("Clear Centerline", self)
        self._action_clear_centerline.triggered.connect(self._clear_centerline)
        self._action_clear_centerline.setToolTip("Remove all centerline nodes from the map.")

        self._action_export_centerline_csv = QAction("Export Centerline CSV…", self)
        self._action_export_centerline_csv.triggered.connect(self._export_centerline_csv)
        self._action_export_centerline_path = QAction("Export Centerline Path YAML…", self)
        self._action_export_centerline_path.triggered.connect(self._export_centerline_path)
        self._action_export_map_pgm = QAction("Export Map as PGM…", self)
        self._action_export_map_pgm.triggered.connect(self._export_map_as_pgm)
        self._action_export_walls_csv = QAction("Export Walls CSV…", self)
        self._action_export_walls_csv.triggered.connect(self._export_walls_csv)
        self._action_export_bundle = QAction("Export Bundle Assets…", self)
        self._action_export_bundle.triggered.connect(self._export_bundle_assets)

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self._action_open)
        file_menu.addAction(self._action_save)
        file_menu.addSeparator()
        file_menu.addAction(self._action_export_bundle)
        file_menu.addSeparator()
        file_menu.addAction(self._action_export_centerline_csv)
        file_menu.addAction(self._action_export_centerline_path)
        file_menu.addAction(self._action_export_walls_csv)
        file_menu.addAction(self._action_export_map_pgm)
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
        edit_menu.addSeparator()
        edit_menu.addAction(self._action_place_centerline)
        edit_menu.addAction(self._action_import_centerline)
        edit_menu.addAction(self._action_edit_centerline)
        edit_menu.addAction(self._action_clear_centerline)
        edit_menu.addSeparator()
        self._action_generate_centerline = QAction("Generate Centerline from Map", self)
        self._action_generate_centerline.triggered.connect(self._generate_centerline_from_walls)
        edit_menu.addAction(self._action_generate_centerline)

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
        self._annotation_panel.beginCenterlineRequested.connect(self._start_centerline_placement)
        self._annotation_panel.finishCenterlineRequested.connect(self._finish_centerline_placement)
        self._annotation_panel.editCenterlineRequested.connect(self._edit_centerline)
        self._annotation_panel.clearCenterlineRequested.connect(self._clear_centerline)
        self._annotation_panel.stampSettingsChanged.connect(self._on_stamp_settings_changed)

        diagnostics_dock = QDockWidget("Diagnostics", self)
        diagnostics_dock.setObjectName("diagnosticsDock")
        diagnostics_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        diagnostics_dock.setWidget(self._diagnostics_panel)
        diagnostics_dock.setMinimumWidth(300)
        diagnostics_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, diagnostics_dock)

        self._diagnostics_panel.highlightToggled.connect(self._on_diagnostics_highlight_changed)
        self._diagnostics_panel.refreshRequested.connect(self._refresh_diagnostics)

        metrics_dock = QDockWidget("Track Metrics", self)
        metrics_dock.setObjectName("metricsDock")
        metrics_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        metrics_dock.setWidget(self._track_metrics_panel)
        metrics_dock.setMinimumWidth(320)
        metrics_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, metrics_dock)

    def _connect_viewer_signals(self) -> None:
        self._map_viewer.spawnPlacementCompleted.connect(self._finalize_spawn_point)
        self._map_viewer.spawnStampPlacementCompleted.connect(self._finalize_spawn_stamp)
        self._map_viewer.startFinishPlacementCompleted.connect(self._finalize_start_finish_line)
        self._map_viewer.placementStatusChanged.connect(self.statusBar().showMessage)
        self._map_viewer.placementCancelled.connect(self._on_viewer_placement_cancelled)
        self._map_viewer.centerlinePlacementFinished.connect(self._handle_centerline_placement_finished)

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
                self._refresh_diagnostics()
            else:
                QMessageBox.warning(self, "Failed to load image", selected_path.name)
            return

        # Default to YAML handling; full parsing will come later.
        try:
            result = self._bundle_loader.load_from_yaml(selected_path)
        except MapYamlError as exc:
            QMessageBox.critical(self, "Failed to load map", str(exc))
            return

        self._apply_loaded_bundle(result)

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
        self._refresh_diagnostics()

    def _handle_metadata_changed(self, metadata: MapMetadata) -> None:
        if self._current_bundle is not None:
            self._current_bundle = self._current_bundle.with_metadata(metadata)
        self._map_viewer.set_metadata(metadata)
        if self._current_bundle is not None:
            self._map_viewer.update_annotations(self._current_bundle.annotations)
        self._refresh_diagnostics()
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

    def _apply_loaded_bundle(
        self,
        result: MapBundleLoadResult,
        message: Optional[str] = None,
    ) -> None:
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

        if message is None:
            message = (
                f"Loaded bundle: {bundle.yaml_path.name}"
                if bundle.yaml_path
                else "Loaded bundle"
            )
        if result.warnings:
            message += " (" + "; ".join(result.warnings) + ")"

        self.statusBar().showMessage(message)
        self._refresh_diagnostics()

    def _handle_annotation_change(self, annotations: MapAnnotations) -> None:
        if self._current_bundle is not None:
            self._current_bundle = self._current_bundle.with_annotations(annotations)
        self._map_viewer.update_annotations(annotations)
        self._annotation_panel.set_annotations(annotations)
        self._action_save.setEnabled(True)
        self.statusBar().showMessage(
            f"Annotations updated (spawn points: {len(annotations.spawn_points)})"
        )
        self._refresh_diagnostics()

    def _on_stamp_settings_changed(self, settings: SpawnStampSettings) -> None:
        self._spawn_stamp_settings = settings
        self._map_viewer.set_spawn_stamp_settings(settings)

    def _ensure_annotation_context(self) -> Optional[AnnotationContext]:
        if self._annotation_context is None:
            QMessageBox.information(self, "No map", "Load a map before editing annotations.")
            return None
        return self._annotation_context

    def _add_spawn_point(self) -> None:
        if self._annotation_context is None:
            if self._ensure_annotation_context() is None:
                return
        self._map_viewer.set_spawn_stamp_settings(self._spawn_stamp_settings)
        use_stamp = self._spawn_stamp_settings.enabled
        if not self._map_viewer.begin_spawn_placement(use_stamp):
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
        self.statusBar().showMessage("Start/finish line cleared.")

    def _on_viewer_placement_cancelled(self) -> None:
        # No additional work required beyond the viewer status message.
        self._annotation_panel.set_centerline_placing(False)

    def _start_centerline_placement(self) -> None:
        if self._annotation_context is None and self._ensure_annotation_context() is None:
            return
        if self._map_viewer.begin_centerline_placement():
            self._annotation_panel.set_centerline_placing(True)
            self.statusBar().showMessage(
                "Centerline placement mode: left-click to add points, Enter/right-click to finish."
            )

    def _finish_centerline_placement(self) -> None:
        if self._map_viewer.placement_mode() != MapViewer.PlacementMode.CENTERLINE:
            self._annotation_panel.set_centerline_placing(False)
            return
        self._map_viewer.complete_centerline_placement()

    def _handle_centerline_placement_finished(self, points: object) -> None:
        context = self._ensure_annotation_context()
        if context is None:
            return
        typed_points = [Point2D(p.x, p.y) for p in points] if isinstance(points, list) else []
        if len(typed_points) < 2:
            self.statusBar().showMessage("Centerline requires at least two points.")
            self._annotation_panel.set_centerline_placing(False)
            return
        self._undo_stack.push(SetCenterlineCommand(context, typed_points))
        self.statusBar().showMessage(f"Centerline placed ({len(typed_points)} point(s)).")
        self._annotation_panel.set_centerline_placing(False)
        self._refresh_diagnostics()

    def _import_centerline_csv(self) -> None:
        context = self._ensure_annotation_context()
        if context is None:
            return
        default_path = self._suggest_export_path("centerline.csv")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import centerline CSV",
            str(Path(default_path).parent),
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return
        try:
            points = self._read_centerline_csv(Path(file_path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", f"Could not read centerline CSV: {exc}")
            return
        if len(points) < 2:
            QMessageBox.warning(self, "Insufficient points", "Centerline must contain at least two points.")
            return
        self._undo_stack.push(SetCenterlineCommand(context, points))
        self.statusBar().showMessage(f"Imported centerline with {len(points)} point(s).")
        self._refresh_diagnostics()

    def _read_centerline_csv(self, path: Path) -> list[Point2D]:
        points: list[Point2D] = []
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            headers = next(reader, None)
            for row in reader:
                if not row:
                    continue
                if headers and row == headers:
                    continue
                try:
                    x = float(row[0])
                    y = float(row[1])
                except (IndexError, ValueError) as exc:
                    raise ValueError(f"Invalid row: {row}") from exc
                points.append(Point2D(x, y))
        return points

    def _generate_centerline_from_walls(self) -> None:
        context = self._ensure_annotation_context()
        if context is None:
            return
        if not self._current_bundle:
            QMessageBox.information(self, "No map", "Load a map before generating a centerline.")
            return
        with show_busy_dialog(self, "Generating centerline…", minimum_duration=0) as progress:
            progress.setLabelText("Extracting walls…")
            QApplication.processEvents()
            extraction = extract_walls(
                self._current_bundle.image_path,
                self._current_bundle.metadata,
            )
            if len(extraction.walls) < 2:
                QMessageBox.warning(
                    self,
                    "Insufficient walls",
                    "Need at least two wall contours to derive a centerline.",
                )
                return
            progress.setLabelText("Deriving centerline path…")
            QApplication.processEvents()
            centerline_points = derive_centerline_from_walls(extraction.walls)
        if len(centerline_points) < 2:
            QMessageBox.warning(self, "Centerline generation failed", "Could not derive a usable centerline from walls.")
            return
        self._undo_stack.push(SetCenterlineCommand(context, centerline_points))
        self.statusBar().showMessage(
            f"Generated centerline from occupancy map ({len(centerline_points)} point(s))."
        )
        self._refresh_diagnostics()

        exported_yaml = self._export_bundle_assets(show_result=False)
        if exported_yaml:
            try:
                result = self._bundle_loader.load_from_yaml(exported_yaml)
            except MapYamlError as exc:
                QMessageBox.critical(
                    self,
                    "Reload failed",
                    f"Bundle exported but could not be reopened: {exc}",
                )
                return
            self._apply_loaded_bundle(
                result,
                message=f"Reloaded bundle: {exported_yaml.name}",
            )

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
        self._refresh_diagnostics()

    def _finalize_spawn_stamp(self, poses: list[Pose2D]) -> None:
        context = self._annotation_context
        if context is None:
            return
        if not poses:
            self.statusBar().showMessage("Stamp placement cancelled.")
            return

        start_index = len(context.annotations.spawn_points) + 1
        spawns = [
            SpawnPoint(name=f"spawn_{start_index + idx}", pose=pose)
            for idx, pose in enumerate(poses)
        ]
        self._undo_stack.push(AddSpawnBatchCommand(context, spawns))
        self.statusBar().showMessage(
            f"Added {len(spawns)} spawn point(s) via stamp placement."
        )
        self._refresh_diagnostics()

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

        self._refresh_diagnostics()

    def _edit_centerline(self) -> None:
        self._map_viewer.cancel_placement()
        context = self._ensure_annotation_context()
        if context is None:
            return

        dialog = CenterlineEditorDialog(context.annotations.centerline, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_points = dialog.points()
        if new_points == context.annotations.centerline:
            return
        self._undo_stack.push(SetCenterlineCommand(context, new_points))
        self.statusBar().showMessage(f"Centerline updated ({len(new_points)} point(s)).")

    def _clear_centerline(self) -> None:
        self._map_viewer.cancel_placement()
        context = self._ensure_annotation_context()
        if context is None:
            return
        if not context.annotations.centerline:
            self.statusBar().showMessage("Centerline already empty.")
            return
        self._undo_stack.push(SetCenterlineCommand(context, []))
        self.statusBar().showMessage("Centerline cleared.")
        self._refresh_diagnostics()

    def _export_centerline_csv(self) -> None:
        if not self._current_bundle or not self._current_bundle.annotations.centerline:
            QMessageBox.information(self, "No centerline", "Create a centerline before exporting.")
            return
        samples = resample_centerline(
            self._current_bundle.annotations.centerline,
            self._centerline_spacing,
        )
        if not samples:
            QMessageBox.warning(self, "Centerline too short", "Not enough points to export.")
            return
        default_path = self._suggest_export_path("centerline.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export centerline CSV",
            default_path,
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return
        export_centerline_csv(samples, Path(file_path))
        self.statusBar().showMessage(f"Centerline CSV exported: {Path(file_path).name}")

    def _export_centerline_path(self) -> None:
        if not self._current_bundle or not self._current_bundle.annotations.centerline:
            QMessageBox.information(self, "No centerline", "Create a centerline before exporting.")
            return
        samples = resample_centerline(
            self._current_bundle.annotations.centerline,
            self._centerline_spacing,
        )
        if not samples:
            QMessageBox.warning(self, "Centerline too short", "Not enough points to export.")
            return
        default_path = self._suggest_export_path("centerline_path.yaml")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export centerline Path YAML",
            default_path,
            "YAML files (*.yaml);;All files (*)",
        )
        if not file_path:
            return
        frame = "map"
        export_centerline_path_yaml(samples, Path(file_path), frame_id=frame)
        self.statusBar().showMessage(f"Centerline Path exported: {Path(file_path).name}")

    def _export_walls_csv(self) -> None:
        if not self._current_bundle:
            QMessageBox.information(self, "No map", "Load a map before exporting walls.")
            return
        extraction = extract_walls(self._current_bundle.image_path, self._current_bundle.metadata)
        if not extraction.walls:
            QMessageBox.warning(self, "No walls detected", "Could not find occupied regions to export.")
            return
        default_path = self._suggest_export_path("walls.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export walls CSV",
            default_path,
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return
        export_walls_csv(extraction.walls, Path(file_path))
        self.statusBar().showMessage(f"Walls CSV exported: {Path(file_path).name}")

    def _suggest_export_path(self, suffix: str) -> str:
        if self._current_map:
            base = Path(self._current_map)
            return str(base.with_name(f"{base.stem}_{suffix}"))
        return str(Path.home() / suffix)

    def _export_map_as_pgm(self) -> None:
        if not self._current_bundle:
            QMessageBox.information(self, "No map", "Load a map before exporting.")
            return
        source = self._current_bundle.image_path
        if not source.exists():
            QMessageBox.warning(self, "Missing image", f"Image file not found: {source}")
            return
        default_path = self._suggest_export_path("map.pgm")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export map as PGM",
            default_path,
            "PGM files (*.pgm);;All files (*)",
        )
        if not file_path:
            return
        try:
            export_png_as_pgm(source, Path(file_path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(f"Map exported as PGM: {Path(file_path).name}")

    def _export_bundle_assets(
        self,
        destination_dir: Optional[Path] = None,
        *,
        show_result: bool = True,
    ) -> Optional[Path]:
        if not self._current_bundle:
            if show_result:
                QMessageBox.information(self, "No map", "Load a map before exporting.")
            return None

        bundle = self._current_bundle
        if destination_dir is None:
            default_dir = str(bundle.image_path.parent)
            selected = QFileDialog.getExistingDirectory(
                self,
                "Select export folder",
                default_dir,
            )
            if not selected:
                return None
            destination_root = Path(selected)
        else:
            destination_root = destination_dir

        stem = bundle.stem
        destination = destination_root / stem
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            if show_result:
                QMessageBox.critical(self, "Export failed", f"Could not create folder '{destination}': {exc}")
            return None

        exported: list[str] = []
        skipped: list[str] = []
        yaml_target: Optional[Path] = None

        try:
            with show_busy_dialog(self, "Exporting bundle assets…", minimum_duration=0) as progress:
                progress.setLabelText("Copying map image…")
                QApplication.processEvents()
                image_target = destination / f"{stem}{bundle.image_path.suffix.lower()}"
                shutil.copy2(bundle.image_path, image_target)
                exported.append(image_target.name)

                progress.setLabelText("Generating PGM…")
                QApplication.processEvents()
                pgm_target = destination / f"{stem}.pgm"
                export_png_as_pgm(bundle.image_path, pgm_target)
                exported.append(pgm_target.name)

                progress.setLabelText("Writing YAML metadata…")
                QApplication.processEvents()
                yaml_target = destination / f"{stem}.yaml"
                self._bundle_loader.save_bundle(bundle, destination=yaml_target, create_backup=False)
                exported.append(yaml_target.name)

                if bundle.annotations.centerline:
                    progress.setLabelText("Exporting centerline CSV…")
                    QApplication.processEvents()
                    samples = resample_centerline(
                        bundle.annotations.centerline,
                        self._centerline_spacing,
                    )
                    if samples:
                        centerline_target = destination / f"{stem}_centerline.csv"
                        export_centerline_csv(samples, centerline_target)
                        exported.append(centerline_target.name)
                    else:
                        skipped.append("centerline too short to export")
                else:
                    skipped.append("no centerline defined")

                progress.setLabelText("Extracting walls…")
                QApplication.processEvents()
                extraction = extract_walls(bundle.image_path, bundle.metadata)
                if extraction.walls:
                    walls_target = destination / f"{stem}_walls.csv"
                    export_walls_csv(extraction.walls, walls_target)
                    exported.append(walls_target.name)
                else:
                    skipped.append("no walls detected")
        except Exception as exc:  # noqa: BLE001
            if show_result:
                QMessageBox.critical(self, "Export failed", str(exc))
            return None

        if show_result:
            if exported:
                summary = f"Exported to {destination.name}: {', '.join(exported)}"
            else:
                summary = f"No files exported to {destination.name}"
            message_parts = [summary]
            if skipped:
                message_parts.append("Skipped: " + ", ".join(skipped))
            self.statusBar().showMessage("; ".join(message_parts), 8000)

        return yaml_target

    def _refresh_diagnostics(self) -> None:
        if self._current_bundle is None:
            self._diagnostics_report = None
            self._diagnostics_panel.set_report(None)
            self._map_viewer.set_diagnostic_highlight(False, False)
            return
        with show_busy_dialog(self, "Analyzing diagnostics…") as progress:
            progress.setLabelText("Extracting walls…")
            QApplication.processEvents()
            extraction = extract_walls(
                self._current_bundle.image_path,
                self._current_bundle.metadata,
            )
            progress.setLabelText("Computing width profile…")
            QApplication.processEvents()
            self._track_width_profile = compute_track_width_profile(
                self._current_bundle.annotations.centerline,
                extraction.walls,
            )
            progress.setLabelText("Running diagnostics…")
            QApplication.processEvents()
            self._diagnostics_report = analyse_bundle(self._current_bundle)
        self._diagnostics_panel.set_report(self._diagnostics_report)
        self._map_viewer.set_diagnostic_highlight(
            self._diagnostics_panel.highlight_enabled,
            self._diagnostics_report.has_warnings,
        )
        self._update_track_metrics()

    def _on_diagnostics_highlight_changed(self, enabled: bool) -> None:
        has_issues = self._diagnostics_report.has_warnings if self._diagnostics_report else False
        self._map_viewer.set_diagnostic_highlight(enabled, has_issues)

    def _update_track_metrics(self) -> None:
        profile = self._track_width_profile
        self._track_metrics_panel.set_profile(profile, self._track_width_target)
        highlights: list[tuple[Point2D, Point2D]] = []
        if (
            profile
            and profile.samples
            and self._current_bundle
            and self._current_bundle.annotations.centerline
        ):
            centerline = self._current_bundle.annotations.centerline
            for index in range(min(len(centerline) - 1, len(profile.samples) - 1)):
                width_current = profile.samples[index].width
                width_next = profile.samples[index + 1].width
                if width_current is None and width_next is None:
                    continue
                if (
                    (width_current is not None and width_current < self._track_width_target)
                    or (width_next is not None and width_next < self._track_width_target)
                ):
                    highlights.append((centerline[index], centerline[index + 1]))
        self._map_viewer.set_track_width_highlights(highlights, self._track_width_target)

    def _auto_scale_track_width(self) -> None:
        if not self._current_bundle or not self._track_width_profile:
            QMessageBox.information(
                self,
                "Track width",
                "Load a map with a centerline and walls before scaling.",
            )
            return

        average_width = self._track_width_profile.average_width
        if not average_width or average_width <= 0:
            QMessageBox.information(
                self,
                "Track width",
                "Unable to compute average width.",
            )
            return

        scale_factor = self._track_width_target / average_width
        if abs(scale_factor - 1.0) < 1e-3:
            self.statusBar().showMessage("Track already at target width.")
            return

        bundle = self._current_bundle
        metadata = bundle.metadata

        new_metadata = MapMetadata(
            resolution=metadata.resolution * scale_factor,
            origin_x=metadata.origin_x * scale_factor,
            origin_y=metadata.origin_y * scale_factor,
            origin_theta=metadata.origin_theta,
            occupied_thresh=metadata.occupied_thresh,
            free_thresh=metadata.free_thresh,
        )

        annotations = bundle.annotations
        scaled_centerline = [
            Point2D(point.x * scale_factor, point.y * scale_factor)
            for point in annotations.centerline
        ]
        scaled_spawns = [
            SpawnPoint(
                name=spawn.name,
                pose=Pose2D(spawn.pose.x * scale_factor, spawn.pose.y * scale_factor, spawn.pose.theta),
            )
            for spawn in annotations.spawn_points
        ]
        scaled_start_finish = None
        if annotations.start_finish_line is not None:
            start = annotations.start_finish_line.segment.start
            end = annotations.start_finish_line.segment.end
            scaled_start_finish = StartFinishLine(
                LineSegment(
                    start=Point2D(start.x * scale_factor, start.y * scale_factor),
                    end=Point2D(end.x * scale_factor, end.y * scale_factor),
                )
            )

        new_annotations = MapAnnotations(
            start_finish_line=scaled_start_finish,
            spawn_points=scaled_spawns,
            centerline=scaled_centerline,
        )

        self._current_bundle = bundle.with_metadata(new_metadata).with_annotations(new_annotations)
        self._centerline_spacing *= scale_factor

        self._metadata_panel.set_metadata(new_metadata)
        self._map_viewer.set_metadata(new_metadata)
        self._map_viewer.update_annotations(new_annotations)
        self._annotation_panel.set_annotations(new_annotations)
        self._refresh_annotation_context()
        self._refresh_diagnostics()
        self.statusBar().showMessage(
            f"Scaled map by {scale_factor:.3f} to achieve {self._track_width_target:.2f} m width."
        )
