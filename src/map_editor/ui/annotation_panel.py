"""Annotation editor dock for managing spawn points and start/finish line."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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


class AnnotationPanel(QWidget):
    """Dock widget contents that expose annotation editing controls."""

    addSpawnRequested = Signal()
    editSpawnRequested = Signal(int)
    deleteSpawnRequested = Signal(int)
    setStartFinishRequested = Signal()
    clearStartFinishRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._annotations = MapAnnotations()

        self._spawn_list = QListWidget(self)
        self._spawn_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._spawn_list.itemSelectionChanged.connect(self._update_button_states)

        self._add_button = QPushButton("Add")
        self._add_button.clicked.connect(self.addSpawnRequested.emit)
        self._edit_button = QPushButton("Edit")
        self._edit_button.clicked.connect(self._emit_edit_requested)
        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self._emit_delete_requested)

        button_row = QHBoxLayout()
        button_row.addWidget(self._add_button)
        button_row.addWidget(self._edit_button)
        button_row.addWidget(self._delete_button)

        spawn_group = QGroupBox("Spawn Points", self)
        spawn_layout = QVBoxLayout(spawn_group)
        spawn_layout.addWidget(self._spawn_list)
        spawn_layout.addLayout(button_row)

        self._start_finish_label = QLabel("No start/finish line")
        self._set_start_finish_button = QPushButton("Set…")
        self._set_start_finish_button.clicked.connect(self.setStartFinishRequested.emit)
        self._clear_start_finish_button = QPushButton("Clear")
        self._clear_start_finish_button.clicked.connect(self.clearStartFinishRequested.emit)
        start_button_row = QHBoxLayout()
        start_button_row.addWidget(self._set_start_finish_button)
        start_button_row.addWidget(self._clear_start_finish_button)

        start_group = QGroupBox("Start / Finish", self)
        start_layout = QVBoxLayout(start_group)
        start_layout.addWidget(self._start_finish_label)
        start_layout.addLayout(start_button_row)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        root.addWidget(spawn_group)
        root.addWidget(start_group)
        root.addStretch(1)

        self._update_button_states()

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
        self._update_button_states()

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
