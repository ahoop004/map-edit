"""Diagnostics dock UI for highlighting map issues."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from map_editor.services.diagnostics import DiagnosticIssue, DiagnosticsReport


class DiagnosticsPanel(QWidget):
    """Displays diagnostics for the currently open map."""

    highlightToggled = Signal(bool)
    refreshRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._report: Optional[DiagnosticsReport] = None

        self._summary_label = QLabel("Diagnostics pending", self)
        self._summary_label.setWordWrap(True)

        self._issues_list = QListWidget(self)
        self._issues_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        self._highlight_checkbox = QCheckBox("Highlight warnings on map", self)
        self._highlight_checkbox.setChecked(True)
        self._highlight_checkbox.stateChanged.connect(self._on_highlight_changed)

        self._refresh_button = QPushButton("Re-run diagnostics", self)
        self._refresh_button.clicked.connect(self.refreshRequested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._summary_label)
        layout.addWidget(self._issues_list, stretch=1)
        layout.addWidget(self._highlight_checkbox)
        layout.addWidget(self._refresh_button)

    def set_report(self, report: Optional[DiagnosticsReport]) -> None:
        self._report = report
        self._issues_list.clear()

        if report is None:
            self._summary_label.setText("Diagnostics pending")
            return

        if not report.issues:
            self._summary_label.setText("No issues detected.")
        else:
            warning_count = sum(1 for issue in report.issues if issue.severity in {"warning", "error"})
            self._summary_label.setText(
                f"{warning_count} warning(s) detected." if warning_count else "Diagnostics completed."
            )

        for issue in report.issues:
            item = QListWidgetItem(f"[{issue.severity.upper()}] {issue.message}")
            if issue.severity == "error":
                item.setForeground(Qt.GlobalColor.red)
            elif issue.severity == "warning":
                item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                item.setForeground(Qt.GlobalColor.darkGray)
            self._issues_list.addItem(item)

    @property
    def highlight_enabled(self) -> bool:
        return self._highlight_checkbox.isChecked()

    def _on_highlight_changed(self, state: int) -> None:
        self.highlightToggled.emit(state == Qt.CheckState.Checked)

