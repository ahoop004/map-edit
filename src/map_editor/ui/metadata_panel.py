"""Metadata editor panel for map settings."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from map_editor.models.map_bundle import MapMetadata


class MapMetadataPanel(QWidget):
    """Form for displaying and editing map metadata values."""

    metadataChanged = Signal(MapMetadata)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._current_metadata = MapMetadata.default()

        self._resolution = self._create_spinbox(0.001, 10.0, 0.001)
        self._origin_x = self._create_spinbox(-1000.0, 1000.0, 0.001)
        self._origin_y = self._create_spinbox(-1000.0, 1000.0, 0.001)
        self._occupied_thresh = self._create_spinbox(0.0, 1.0, 0.01)
        self._free_thresh = self._create_spinbox(0.0, 1.0, 0.01)

        self._status_label = QLabel("No map loaded", self)
        self._status_label.setProperty("cssClass", "metadata-status")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._status_label)
        self._group_box = self._build_metadata_group()
        root_layout.addWidget(self._group_box)
        root_layout.addStretch(1)

        self._connect_signals()
        self._group_box.setEnabled(False)
        self.set_metadata(None)

    def _build_metadata_group(self) -> QWidget:
        group = QGroupBox("Map Metadata", self)
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Resolution (m/pixel)", self._resolution)
        form.addRow("Origin X (m)", self._origin_x)
        form.addRow("Origin Y (m)", self._origin_y)
        form.addRow("Occupied threshold", self._occupied_thresh)
        form.addRow("Free threshold", self._free_thresh)
        return group

    def _connect_signals(self) -> None:
        for spinbox in (
            self._resolution,
            self._origin_x,
            self._origin_y,
            self._occupied_thresh,
            self._free_thresh,
        ):
            spinbox.valueChanged.connect(self._emit_metadata_changed)

    @staticmethod
    def _create_spinbox(minimum: float, maximum: float, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(4)
        spin.setKeyboardTracking(False)
        return spin

    def set_metadata(self, metadata: Optional[MapMetadata]) -> None:
        """Populate the form and enable interaction."""
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self._resolution,
                self._origin_x,
                self._origin_y,
                self._occupied_thresh,
                self._free_thresh,
            )
        ]
        if metadata is None:
            defaults = MapMetadata.default()
            self._current_metadata = defaults
            self._resolution.setValue(defaults.resolution)
            self._origin_x.setValue(defaults.origin_x)
            self._origin_y.setValue(defaults.origin_y)
            self._occupied_thresh.setValue(defaults.occupied_thresh)
            self._free_thresh.setValue(defaults.free_thresh)
            self._group_box.setEnabled(False)
            self._status_label.setText("No map loaded")
        else:
            self._current_metadata = metadata
            self._resolution.setValue(metadata.resolution)
            self._origin_x.setValue(metadata.origin_x)
            self._origin_y.setValue(metadata.origin_y)
            self._occupied_thresh.setValue(metadata.occupied_thresh)
            self._free_thresh.setValue(metadata.free_thresh)
            self._group_box.setEnabled(True)
            self._status_label.setText("Editing metadata")
        del blockers

    def metadata(self) -> MapMetadata:
        """Return the current metadata values from the form."""
        return MapMetadata(
            resolution=self._resolution.value(),
            origin_x=self._origin_x.value(),
            origin_y=self._origin_y.value(),
            origin_theta=self._current_metadata.origin_theta,
            occupied_thresh=self._occupied_thresh.value(),
            free_thresh=self._free_thresh.value(),
        )

    def _emit_metadata_changed(self) -> None:
        updated = self.metadata()
        self._current_metadata = updated
        self.metadataChanged.emit(updated)


__all__ = ["MapMetadataPanel"]
