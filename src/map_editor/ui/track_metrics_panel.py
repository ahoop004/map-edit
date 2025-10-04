"""Dock content for displaying track width metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from map_editor.services.track_metrics import TrackWidthProfile, TrackWidthSample
from map_editor.ui.collapsible_section import CollapsibleSection


class WidthProfileView(QWidget):
    """Minimal line chart showing width vs distance."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._samples: list[TrackWidthSample] = []
        self._threshold: Optional[float] = None
        self.setMinimumHeight(120)

    def set_profile(self, samples: Iterable[TrackWidthSample], threshold: Optional[float]) -> None:
        self._samples = [sample for sample in samples if sample.width is not None]
        self._threshold = threshold
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        rect = self.rect().adjusted(10, 10, -10, -20)
        painter.fillRect(self.rect(), self.palette().window())
        if not self._samples:
            painter.setPen(self.palette().text().color())
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No width data")
            return

        max_width = max(sample.width for sample in self._samples if sample.width is not None)
        min_width = min(sample.width for sample in self._samples if sample.width is not None)
        max_distance = max(sample.distance for sample in self._samples)

        if max_width <= 0 or max_distance <= 0:
            painter.setPen(self.palette().text().color())
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Width data unavailable")
            return

        painter.setPen(self.palette().mid().color())
        painter.drawRect(rect)

        def to_point(sample: TrackWidthSample) -> tuple[float, float]:
            x = rect.left() + (sample.distance / max_distance) * rect.width()
            width = sample.width or 0.0
            if max_width == min_width:
                y_ratio = 0.0
            else:
                y_ratio = (width - min_width) / (max_width - min_width)
            y = rect.bottom() - y_ratio * rect.height()
            return x, y

        # Threshold line
        if self._threshold and max_width != min_width:
            ratio = (self._threshold - min_width) / (max_width - min_width)
            y = rect.bottom() - ratio * rect.height()
            painter.setPen(QPen(Qt.GlobalColor.red, 1, Qt.PenStyle.DashLine))
            painter.drawLine(rect.left(), y, rect.right(), y)

        painter.setPen(QPen(self.palette().highlight().color(), 2))
        previous = None
        for sample in self._samples:
            point = to_point(sample)
            if previous is not None:
                painter.drawLine(previous[0], previous[1], point[0], point[1])
            previous = point


class TrackMetricsPanel(QWidget):
    """Displays track width statistics and controls."""

    autoScaleRequested = Signal()
    computeRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._profile: Optional[TrackWidthProfile] = None
        self._threshold: float = 2.2
        self._controls_enabled = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self._summary_label = QLabel("No width data", self)
        self._summary_label.setWordWrap(True)

        section = CollapsibleSection("Track Width", self, settings_key="metrics/track_width_section")
        content = section.content_layout()
        content.setSpacing(6)
        self._compute_button = QPushButton("Compute track metrics", self)
        self._compute_button.clicked.connect(self.computeRequested.emit)
        content.addWidget(self._compute_button)

        content.addWidget(self._summary_label)

        self._profile_view = WidthProfileView(self)
        content.addWidget(self._profile_view)

        self._auto_scale_button = QPushButton("Scale map to 2.20 m", self)
        self._auto_scale_button.clicked.connect(self.autoScaleRequested.emit)
        content.addWidget(self._auto_scale_button)

        root.addWidget(section)
        root.addStretch(1)
        self._update_state()

    def set_profile(self, profile: Optional[TrackWidthProfile], threshold: float) -> None:
        self._profile = profile
        self._threshold = threshold
        if profile and profile.valid_samples:
            avg = profile.average_width or 0.0
            min_width = profile.minimum_width or 0.0
            max_width = profile.maximum_width or 0.0
            self._summary_label.setText(
                f"Average width: {avg:.2f} m\n"
                f"Min width: {min_width:.2f} m\n"
                f"Max width: {max_width:.2f} m"
            )
            self._profile_view.set_profile(profile.samples, threshold)
        else:
            self._summary_label.setText("No width data")
            self._profile_view.set_profile([], threshold)
        self._update_state()

    def _update_state(self) -> None:
        self._compute_button.setEnabled(self._controls_enabled)
        can_scale = self._controls_enabled and bool(self._profile and self._profile.valid_samples)
        self._auto_scale_button.setEnabled(can_scale)

    def set_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable panel controls based on map availability."""
        self._controls_enabled = enabled
        self._update_state()


__all__ = ["TrackMetricsPanel"]
