"""Dialog for generating procedural track bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from map_editor.services.procedural_track import TrackSpec, TrackSpecError, generate_preview_image, load_track_spec


class TrackGeneratorDialog(QDialog):
    """Collect parameters for procedural track generation."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate Track")
        self.setModal(True)

        self._spec_path_edit = QLineEdit()
        self._output_dir_edit = QLineEdit()

        browse_spec = QPushButton("Browse…")
        browse_spec.clicked.connect(self._browse_spec)
        browse_output = QPushButton("Browse…")
        browse_output.clicked.connect(self._browse_output)

        spec_row = QHBoxLayout()
        spec_row.addWidget(self._spec_path_edit)
        spec_row.addWidget(browse_spec)

        output_row = QHBoxLayout()
        output_row.addWidget(self._output_dir_edit)
        output_row.addWidget(browse_output)

        self._width_spin = self._make_spin(0.1, 100.0, 2.2, suffix=" m")
        self._resolution_spin = self._make_spin(0.001, 1.0, 0.06, decimals=5, suffix=" m/px")
        self._padding_spin = self._make_spin(0.0, 100.0, 5.0, suffix=" m")

        form = QFormLayout()
        form.addRow("Track spec (YAML)", spec_row)
        form.addRow("Output folder", output_row)
        form.addRow("Track width", self._width_spin)
        form.addRow("Resolution", self._resolution_spin)
        form.addRow("Padding", self._padding_spin)

        self._preview_label = QLabel("Preview not generated")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumSize(360, 240)
        self._preview_label.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)

        preview_button = QPushButton("Preview")
        preview_button.clicked.connect(self._refresh_preview)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        generate_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if generate_button:
            generate_button.setText("Generate")
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._preview_label)
        layout.addWidget(preview_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(button_box)

        self._spec: TrackSpec | None = None
        self._output_dir: Path | None = None
        self._preview_image = None

    def spec(self) -> TrackSpec:
        if self._spec is None:
            raise TrackSpecError("No track spec loaded.")
        return self._spec

    def output_dir(self) -> Path:
        if self._output_dir is None:
            raise TrackSpecError("No output directory selected.")
        return self._output_dir

    def _browse_spec(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select track YAML",
            str(Path.cwd()),
            "YAML files (*.yaml *.yml);;All files (*)",
        )
        if not path:
            return
        self._spec_path_edit.setText(path)
        try:
            spec = load_track_spec(Path(path))
        except TrackSpecError as exc:
            QMessageBox.critical(self, "Invalid track spec", str(exc))
            return
        self._apply_spec_defaults(spec)

    def _browse_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select output folder", str(Path.cwd()))
        if directory:
            self._output_dir_edit.setText(directory)

    def _apply_spec_defaults(self, spec: TrackSpec) -> None:
        self._width_spin.setValue(spec.track_width)
        self._resolution_spin.setValue(spec.resolution)
        self._padding_spin.setValue(spec.padding)
        if not self._output_dir_edit.text().strip():
            default_dir = Path("sample_maps") / f"{spec.stem}_map"
            self._output_dir_edit.setText(str(default_dir))

    def _refresh_preview(self) -> None:
        try:
            spec = self._build_spec()
        except TrackSpecError as exc:
            QMessageBox.critical(self, "Preview failed", str(exc))
            return
        try:
            image = generate_preview_image(spec)
        except TrackSpecError as exc:
            QMessageBox.critical(self, "Preview failed", str(exc))
            return
        self._preview_image = image
        self._update_preview_pixmap()

    def _update_preview_pixmap(self) -> None:
        if self._preview_image is None:
            return
        pixmap = QPixmap.fromImage(self._preview_image)
        self._preview_label.setPixmap(
            pixmap.scaled(
                self._preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_preview_pixmap()

    def _build_spec(self) -> TrackSpec:
        spec_path = self._spec_path_edit.text().strip()
        if not spec_path:
            raise TrackSpecError("Track spec path is required.")
        spec = load_track_spec(Path(spec_path))
        return TrackSpec(
            stem=spec.stem,
            control_points=spec.control_points,
            track_width=self._width_spin.value(),
            centerline_spacing=spec.centerline_spacing,
            resolution=self._resolution_spin.value(),
            padding=self._padding_spin.value(),
            wall_thickness_px=spec.wall_thickness_px,
            wall_smoothing_passes=spec.wall_smoothing_passes,
            min_curvature_radius=spec.min_curvature_radius,
            min_wall_separation=spec.min_wall_separation,
            occupied_thresh=spec.occupied_thresh,
            free_thresh=spec.free_thresh,
            negate=spec.negate,
        )

    def _accept(self) -> None:
        try:
            self._spec = self._build_spec()
        except TrackSpecError as exc:
            QMessageBox.critical(self, "Generate failed", str(exc))
            return
        output_text = self._output_dir_edit.text().strip()
        if output_text:
            self._output_dir = Path(output_text)
        else:
            self._output_dir = Path("sample_maps") / f"{self._spec.stem}_map"
        self.accept()
