"""Annotation editor dock for managing spawn points and start/finish line."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from map_editor.models.annotations import (
    LineSegment,
    MapAnnotations,
    Point2D,
    Pose2D,
    SpawnPoint,
    StartFinishLine,
)
from map_editor.models.spawn_stamp import MAX_STAMP_COUNT, SpawnStampSettings
from map_editor.ui.collapsible_section import CollapsibleSection


class AnnotationPanel(QWidget):
    """Dock widget contents that expose annotation editing controls."""

    addSpawnRequested = Signal()
    editSpawnRequested = Signal(int)
    deleteSpawnRequested = Signal(int)
    setStartFinishRequested = Signal()
    clearStartFinishRequested = Signal()
    beginCenterlineRequested = Signal()
    finishCenterlineRequested = Signal()
    editCenterlineRequested = Signal()
    clearCenterlineRequested = Signal()
    stampSettingsChanged = Signal(SpawnStampSettings)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._annotations = MapAnnotations()
        self._stamp_settings = SpawnStampSettings()

        self._spawn_list = QListWidget(self)
        self._spawn_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._spawn_list.itemSelectionChanged.connect(self._update_button_states)

        self._add_button = QPushButton("Add")
        self._add_button.clicked.connect(self.addSpawnRequested.emit)
        self._add_button.setToolTip("Enter placement mode, then left-click on the map to place a spawn point.")
        self._edit_button = QPushButton("Edit")
        self._edit_button.clicked.connect(self._emit_edit_requested)
        self._edit_button.setToolTip("Edit the selected spawn point.")
        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self._emit_delete_requested)
        self._delete_button.setToolTip("Delete the selected spawn point.")

        button_row = QHBoxLayout()
        button_row.addWidget(self._add_button)
        button_row.addWidget(self._edit_button)
        button_row.addWidget(self._delete_button)

        spawn_section = CollapsibleSection(
            "Spawn Points", self, settings_key="annotations/spawn_section"
        )
        spawn_layout = spawn_section.content_layout()
        spawn_layout.addWidget(self._spawn_list)
        spawn_layout.addLayout(button_row)
        spawn_layout.addLayout(self._build_stamp_controls())

        self._start_finish_label = QLabel("No start/finish line")
        self._set_start_finish_button = QPushButton("Set…")
        self._set_start_finish_button.clicked.connect(self.setStartFinishRequested.emit)
        self._set_start_finish_button.setToolTip(
            "Enter placement mode, then click start and end points for the start/finish line."
        )
        self._clear_start_finish_button = QPushButton("Clear")
        self._clear_start_finish_button.clicked.connect(self.clearStartFinishRequested.emit)
        self._clear_start_finish_button.setToolTip("Remove the start/finish line from the map.")
        start_button_row = QHBoxLayout()
        start_button_row.addWidget(self._set_start_finish_button)
        start_button_row.addWidget(self._clear_start_finish_button)

        start_section = CollapsibleSection(
            "Start / Finish", self, settings_key="annotations/start_finish_section"
        )
        start_layout = start_section.content_layout()
        start_layout.addWidget(self._start_finish_label)
        start_layout.addLayout(start_button_row)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        root.addWidget(spawn_section)
        root.addWidget(start_section)
        root.addWidget(self._build_centerline_section())
        root.addStretch(1)

        self._update_button_states()
        self._emit_stamp_settings()

    def set_annotations(self, annotations: MapAnnotations) -> None:
        """Refresh UI state based on provided annotations."""
        self._annotations = annotations
        self._spawn_list.clear()
        for spawn in annotations.spawn_points:
            item = QListWidgetItem(
                f"{spawn.name}  (x={spawn.pose.x:.2f}, y={spawn.pose.y:.2f}, θ={spawn.pose.theta:.2f})"
            )
            self._spawn_list.addItem(item)
        if annotations.start_finish_line is None:
            self._start_finish_label.setText("No start/finish line")
        else:
            start = annotations.start_finish_line.segment.start
            end = annotations.start_finish_line.segment.end
            self._start_finish_label.setText(
                f"({start.x:.2f}, {start.y:.2f}) → ({end.x:.2f}, {end.y:.2f})"
            )
        if annotations.centerline:
            self._centerline_label.setText(f"{len(annotations.centerline)} point(s)")
        else:
            self._centerline_label.setText("No centerline")
        self._update_button_states()

    def stamp_settings(self) -> SpawnStampSettings:
        """Return the current stamp placement configuration."""
        return self._stamp_settings

    def _build_stamp_controls(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)

        self._stamp_enabled = QCheckBox("Enable stamp placement", self)
        self._stamp_enabled.setChecked(self._stamp_settings.enabled)
        self._stamp_enabled.setToolTip(
            "Place multiple spawn points at once using a configurable grid."
        )
        self._stamp_enabled.stateChanged.connect(self._on_stamp_control_changed)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        self._stamp_count = QSpinBox(self)
        self._stamp_count.setRange(1, MAX_STAMP_COUNT)
        self._stamp_count.setValue(self._stamp_settings.count)
        self._stamp_count.valueChanged.connect(self._on_stamp_control_changed)

        self._stamp_long_spacing = self._create_stamp_spin(
            0.1, 10.0, self._stamp_settings.longitudinal_spacing
        )
        self._stamp_long_spacing.setSuffix(" m")
        self._stamp_long_spacing.valueChanged.connect(self._on_stamp_control_changed)

        self._stamp_lat_spacing = self._create_stamp_spin(
            0.1, 10.0, self._stamp_settings.lateral_spacing
        )
        self._stamp_lat_spacing.setSuffix(" m")
        self._stamp_lat_spacing.valueChanged.connect(self._on_stamp_control_changed)

        form.addRow("Stamp count", self._stamp_count)
        form.addRow("Row spacing", self._stamp_long_spacing)
        form.addRow("Lane spacing", self._stamp_lat_spacing)

        layout.addWidget(self._stamp_enabled)
        layout.addLayout(form)
        self._update_stamp_controls_enabled()
        return layout

    @staticmethod
    def _create_stamp_spin(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setKeyboardTracking(False)
        spin.setValue(value)
        return spin

    def _on_stamp_control_changed(self) -> None:
        self._update_stamp_controls_enabled()
        self._emit_stamp_settings()

    def _emit_stamp_settings(self) -> None:
        self._stamp_settings = SpawnStampSettings(
            enabled=self._stamp_enabled.isChecked(),
            count=self._stamp_count.value(),
            longitudinal_spacing=self._stamp_long_spacing.value(),
            lateral_spacing=self._stamp_lat_spacing.value(),
        )
        self.stampSettingsChanged.emit(self._stamp_settings)

    def _update_stamp_controls_enabled(self) -> None:
        enabled = self._stamp_enabled.isChecked()
        for widget in (self._stamp_count, self._stamp_long_spacing, self._stamp_lat_spacing):
            widget.setEnabled(enabled)

    def selected_index(self) -> Optional[int]:
        items = self._spawn_list.selectedIndexes()
        if not items:
            return None
        return items[0].row()

    def _emit_edit_requested(self) -> None:
        index = self.selected_index()
        if index is not None:
            self.editSpawnRequested.emit(index)

    def _emit_delete_requested(self) -> None:
        index = self.selected_index()
        if index is not None:
            self.deleteSpawnRequested.emit(index)

    def _update_button_states(self) -> None:
        has_selection = self.selected_index() is not None
        self._edit_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    def _toggle_centerline_placing(self) -> None:
        active = bool(self._place_button.property("placing"))
        if active:
            self.finishCenterlineRequested.emit()
        else:
            self.beginCenterlineRequested.emit()

    def set_centerline_placing(self, active: bool) -> None:
        self._place_button.setProperty("placing", active)
        self._place_button.setText("Finish" if active else "Place…")
        self._place_button.setToolTip(
            "Click to finish placement." if active else "Place centerline points by clicking on the map."
        )

    def _build_centerline_section(self) -> CollapsibleSection:
        section = CollapsibleSection(
            "Centerline", self, settings_key="annotations/centerline_section"
        )
        layout = section.content_layout()
        layout.setSpacing(6)

        self._centerline_label = QLabel("No centerline")
        self._centerline_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        button_row = QHBoxLayout()
        self._place_button = QPushButton("Place…")
        self._place_button.setToolTip("Place centerline points by clicking on the map.")
        self._place_button.clicked.connect(self._toggle_centerline_placing)
        edit_button = QPushButton("Edit…")
        edit_button.setToolTip("Open centerline editor to add/move/delete nodes.")
        edit_button.clicked.connect(self.editCenterlineRequested.emit)
        clear_button = QPushButton("Clear")
        clear_button.setToolTip("Remove all centerline nodes.")
        clear_button.clicked.connect(self.clearCenterlineRequested.emit)
        button_row.addWidget(self._place_button)
        button_row.addWidget(edit_button)
        button_row.addWidget(clear_button)
        button_row.addStretch(1)

        layout.addWidget(self._centerline_label)
        layout.addLayout(button_row)
        return section


class SpawnPointDialog(QDialog):
    """Dialog to create or edit a spawn point."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        title: str = "Spawn Point",
        default_name: str = "spawn",
        spawn: Optional[SpawnPoint] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._name_edit = QLineEdit(spawn.name if spawn else default_name)

        self._x_spin = self._create_spin(-1000.0, 1000.0, spawn.pose.x if spawn else 0.0)
        self._y_spin = self._create_spin(-1000.0, 1000.0, spawn.pose.y if spawn else 0.0)
        self._theta_spin = self._create_spin(-3.14159, 3.14159, spawn.pose.theta if spawn else 0.0)

        form = QFormLayout()
        form.addRow("Name", self._name_edit)
        form.addRow("X (m)", self._x_spin)
        form.addRow("Y (m)", self._y_spin)
        form.addRow("Theta (rad)", self._theta_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _create_spin(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(4)
        spin.setSingleStep(0.1)
        spin.setValue(value)
        return spin

    def spawn_point(self) -> SpawnPoint:
        name = self._name_edit.text().strip() or "spawn"
        pose = Pose2D(self._x_spin.value(), self._y_spin.value(), self._theta_spin.value())
        return SpawnPoint(name=name, pose=pose)


class StartFinishDialog(QDialog):
    """Dialog to edit the start/finish line endpoints."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        title: str = "Start/Finish Line",
        line: Optional[StartFinishLine] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        start = line.segment.start if line else None
        end = line.segment.end if line else None

        self._start_x = self._create_spin(-1000.0, 1000.0, start.x if start else -1.0)
        self._start_y = self._create_spin(-1000.0, 1000.0, start.y if start else 0.0)
        self._end_x = self._create_spin(-1000.0, 1000.0, end.x if end else 1.0)
        self._end_y = self._create_spin(-1000.0, 1000.0, end.y if end else 0.0)

        form = QFormLayout()
        form.addRow("Start X", self._start_x)
        form.addRow("Start Y", self._start_y)
        form.addRow("End X", self._end_x)
        form.addRow("End Y", self._end_y)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _create_spin(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(4)
        spin.setSingleStep(0.1)
        spin.setValue(value)
        return spin

    def start_finish_line(self) -> StartFinishLine:
        start_point = Point2D(self._start_x.value(), self._start_y.value())
        end_point = Point2D(self._end_x.value(), self._end_y.value())
        return StartFinishLine(LineSegment(start=start_point, end=end_point))


__all__ = [
    "AnnotationPanel",
    "SpawnPointDialog",
    "StartFinishDialog",
]
