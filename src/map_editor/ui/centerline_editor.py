"""Dialog for editing centerline points."""

from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from map_editor.models.annotations import Point2D


class CenterlineEditorDialog(QDialog):
    """Provides manual editing controls for centerline nodes."""

    def __init__(self, points: list[Point2D], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Centerline Editor")
        self.resize(420, 360)

        self._table = QTableWidget(self)
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["X (m)", "Y (m)"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)

        self._add_button = QPushButton("Add point")
        self._add_button.clicked.connect(self._add_point)
        self._remove_button = QPushButton("Remove point")
        self._remove_button.clicked.connect(self._remove_selected)
        self._remove_button.setEnabled(False)

        self._move_up_button = QPushButton("Move up")
        self._move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self._move_up_button.setEnabled(False)
        self._move_down_button = QPushButton("Move down")
        self._move_down_button.clicked.connect(lambda: self._move_selected(1))
        self._move_down_button.setEnabled(False)

        self._clear_button = QPushButton("Clear")
        self._clear_button.clicked.connect(self._clear)
        self._smooth_button = QPushButton("Smooth")
        self._smooth_button.clicked.connect(self._smooth)

        button_row = QHBoxLayout()
        for button in (
            self._add_button,
            self._remove_button,
            self._move_up_button,
            self._move_down_button,
            self._smooth_button,
            self._clear_button,
        ):
            button_row.addWidget(button)
        button_row.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Edit centerline nodes below. Double-click to edit values."))
        layout.addWidget(self._table)
        layout.addLayout(button_row)
        layout.addWidget(buttons)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._populate_table(points)
        self._on_selection_changed()

    def points(self) -> list[Point2D]:
        points: list[Point2D] = []
        for row in range(self._table.rowCount()):
            x_item = self._table.item(row, 0)
            y_item = self._table.item(row, 1)
            try:
                x = float(x_item.text()) if x_item else float("nan")
                y = float(y_item.text()) if y_item else float("nan")
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError
            except ValueError as exc:
                self._table.selectRow(row)
                raise ValueError(f"Row {row + 1}: enter finite numbers for X and Y.") from exc
            points.append(Point2D(x, y))
        return points

    def accept(self) -> None:
        try:
            self.points()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid centerline point", str(exc))
            return
        super().accept()

    # Internal helpers -------------------------------------------------

    def _populate_table(self, points: list[Point2D]) -> None:
        self._table.setRowCount(0)
        for point in points:
            self._append_row(point.x, point.y)
        if points:
            self._table.selectRow(0)

    def _append_row(self, x: float, y: float) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(str(x)))
        self._table.setItem(row, 1, QTableWidgetItem(str(y)))

    def _add_point(self) -> None:
        self._append_row(0.0, 0.0)
        self._table.selectRow(self._table.rowCount() - 1)
        self._table.editItem(self._table.item(self._table.rowCount() - 1, 0))

    def _remove_selected(self) -> None:
        row = self._selected_row()
        if row is not None:
            self._table.removeRow(row)

    def _move_selected(self, delta: int) -> None:
        row = self._selected_row()
        if row is None:
            return
        new_row = row + delta
        if not (0 <= new_row < self._table.rowCount()):
            return
        for column in range(self._table.columnCount()):
            current = self._table.takeItem(row, column)
            adjacent = self._table.takeItem(new_row, column)
            self._table.setItem(row, column, adjacent)
            self._table.setItem(new_row, column, current)
        self._table.selectRow(new_row)

    def _clear(self) -> None:
        self._table.setRowCount(0)

    def _smooth(self) -> None:
        try:
            points = self.points()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid centerline point", str(exc))
            return
        if len(points) < 3:
            return
        smoothed: list[Point2D] = []
        smoothed.append(points[0])
        for i in range(1, len(points) - 1):
            prev_pt, cur_pt, next_pt = points[i - 1], points[i], points[i + 1]
            smoothed.append(
                Point2D(
                    (prev_pt.x + cur_pt.x + next_pt.x) / 3.0,
                    (prev_pt.y + cur_pt.y + next_pt.y) / 3.0,
                )
            )
        smoothed.append(points[-1])
        self._populate_table(smoothed)

    def _selected_row(self) -> int | None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        return indexes[0].row()

    def _on_selection_changed(self) -> None:
        row = self._selected_row()
        self._remove_button.setEnabled(row is not None)
        self._move_up_button.setEnabled(row is not None and row > 0)
        self._move_down_button.setEnabled(row is not None and row < self._table.rowCount() - 1)
