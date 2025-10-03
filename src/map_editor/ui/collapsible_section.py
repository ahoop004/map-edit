"""Reusable collapsible section widget for dock panels."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """Header + content container that can collapse to save vertical space."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        *,
        settings_key: Optional[str] = None,
        default_expanded: bool = True,
    ) -> None:
        super().__init__(parent)
        self._settings_key = settings_key
        self._settings = QSettings() if settings_key else None

        self._toggle = QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setCheckable(True)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow)

        self._content = QFrame(self)
        self._content.setFrameShape(QFrame.Shape.NoFrame)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._toggle)
        layout.addWidget(self._content)

        self._toggle.toggled.connect(self._on_toggled)

        expanded = self._load_initial_state(default_expanded)
        self._toggle.setChecked(expanded)
        self._apply_expanded_state(expanded)

    def content_layout(self) -> QVBoxLayout:
        """Return the layout that holds section content."""
        return self._content_layout

    def set_expanded(self, expanded: bool) -> None:
        if self._toggle.isChecked() != expanded:
            self._toggle.setChecked(expanded)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    # Internal API ------------------------------------------------------

    def _load_initial_state(self, default_expanded: bool) -> bool:
        if not self._settings:
            return default_expanded
        stored = self._settings.value(self._settings_key, default_expanded)
        if isinstance(stored, bool):
            return stored
        if isinstance(stored, str):
            return stored.lower() in {"true", "1", "yes"}
        return default_expanded

    def _on_toggled(self, expanded: bool) -> None:
        self._apply_expanded_state(expanded)
        if self._settings:
            self._settings.setValue(self._settings_key, expanded)
        self.toggled.emit(expanded)

    def _apply_expanded_state(self, expanded: bool) -> None:
        self._content.setVisible(expanded)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)


__all__ = ["CollapsibleSection"]
