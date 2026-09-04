"""Dialog for generating procedural track bundles."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from map_editor.constants import DEFAULT_TRACK_WIDTH_TARGET
from map_editor.models.annotations import Point2D
from map_editor.services.procedural_track import (
    TrackSpec,
    TrackSpecError,
    adjust_oval_parameters_for_min_radius,
    build_oval_control_points,
    generate_preview_image,
    load_track_spec,
)


class TrackGeneratorDialog(QDialog):
    """Collect parameters for procedural track generation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate Track")
        self.setModal(True)

        self._spec_path_edit = QLineEdit()
        self._output_dir_edit = QLineEdit()
        self._stem_edit = QLineEdit()

        self._source_combo = QComboBox()
        self._source_combo.addItems(["YAML", "Oval"])
        self._source_combo.currentTextChanged.connect(self._on_source_changed)

        browse_spec = QPushButton("Browse…")
        browse_spec.clicked.connect(self._browse_spec)
        create_spec = QPushButton("Create…")
        create_spec.clicked.connect(self._create_spec)
        browse_output = QPushButton("Browse…")
        browse_output.clicked.connect(self._browse_output)

        spec_row = QHBoxLayout()
        spec_row.addWidget(self._spec_path_edit)
        spec_row.addWidget(browse_spec)
        spec_row.addWidget(create_spec)

        output_row = QHBoxLayout()
        output_row.addWidget(self._output_dir_edit)
        output_row.addWidget(browse_output)

        self._oval_length_spin = self._make_spin(1.0, 200.0, 20.0, suffix=" m")
        self._oval_width_spin = self._make_spin(1.0, 200.0, 10.0, suffix=" m")
        self._curve_amp_spin = self._make_spin(0.0, 20.0, 0.0, suffix=" m")
        self._curve_freq_spin = QSpinBox()
        self._curve_freq_spin.setRange(1, 12)
        self._curve_freq_spin.setValue(2)

        self._width_spin = self._make_spin(0.1, 100.0, DEFAULT_TRACK_WIDTH_TARGET, suffix=" m")
        self._resolution_spin = self._make_spin(0.001, 1.0, 0.06, decimals=5, suffix=" m/px")
        self._padding_spin = self._make_spin(0.0, 100.0, 5.0, suffix=" m")

        form = QFormLayout()
        form.addRow("Source", self._source_combo)
        form.addRow("Track spec (YAML)", spec_row)
        form.addRow("Stem", self._stem_edit)
        form.addRow("Oval length", self._oval_length_spin)
        form.addRow("Oval width", self._oval_width_spin)
        form.addRow("Curve amplitude", self._curve_amp_spin)
        form.addRow("Curve frequency", self._curve_freq_spin)
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
        self._spec_override: TrackSpec | None = None
        self._output_dir: Path | None = None
        self._preview_image = None
        self._source_controls = (self._spec_path_edit, browse_spec, create_spec)
        self._stem_edit.textChanged.connect(self._sync_output_dir)
        self._on_source_changed(self._source_combo.currentText())

    @staticmethod
    def _make_spin(
        minimum: float,
        maximum: float,
        value: float,
        *,
        decimals: int = 2,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(0.1)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        return spin

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
        self._spec_override = None
        self._source_combo.setCurrentText("YAML")
        try:
            spec = load_track_spec(Path(path))
        except TrackSpecError as exc:
            QMessageBox.critical(self, "Invalid track spec", str(exc))
            return
        self._apply_spec_defaults(spec)

    def _create_spec(self) -> None:
        dialog = TrackSpecDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            spec = dialog.spec()
        except TrackSpecError as exc:
            QMessageBox.critical(self, "Invalid track spec", str(exc))
            return
        self._spec_override = spec
        self._spec_path_edit.setText("<inline>")
        self._source_combo.setCurrentText("YAML")
        self._apply_spec_defaults(spec)

    def _browse_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select output folder", str(Path.cwd()))
        if directory:
            self._output_dir_edit.setText(directory)

    def _apply_spec_defaults(self, spec: TrackSpec) -> None:
        self._width_spin.setValue(spec.track_width)
        self._resolution_spin.setValue(spec.resolution)
        self._padding_spin.setValue(spec.padding)
        self._stem_edit.setText(spec.stem)
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
        source = self._source_combo.currentText()
        if source == "Oval":
            return self._build_oval_spec()
        return self._build_yaml_spec()

    def _build_oval_spec(self) -> TrackSpec:
        stem = self._stem_edit.text().strip()
        if not stem:
            raise TrackSpecError("Stem is required for oval generation.")
        length = self._oval_length_spin.value()
        width = self._oval_width_spin.value()
        amplitude = self._curve_amp_spin.value()
        frequency = self._curve_freq_spin.value()
        min_radius = TrackSpec(stem=stem, control_points=[]).min_curvature_radius
        length, width, amplitude, scale = adjust_oval_parameters_for_min_radius(
            length,
            width,
            curve_amplitude=amplitude,
            curve_frequency=frequency,
            min_curvature_radius=min_radius,
            centerline_spacing=0.2,
        )
        if scale > 1.0 + 1e-3:
            self._oval_length_spin.setValue(length)
            self._oval_width_spin.setValue(width)
            self._curve_amp_spin.setValue(amplitude)
        control_points = build_oval_control_points(
            length,
            width,
            curve_amplitude=amplitude,
            curve_frequency=frequency,
        )
        return TrackSpec(
            stem=stem,
            control_points=control_points,
            track_width=self._width_spin.value(),
            centerline_spacing=0.2,
            resolution=self._resolution_spin.value(),
            padding=self._padding_spin.value(),
        )

    def _build_yaml_spec(self) -> TrackSpec:
        spec_path = self._spec_path_edit.text().strip()
        if spec_path and spec_path != "<inline>":
            spec = load_track_spec(Path(spec_path))
        elif self._spec_override is not None:
            spec = self._spec_override
        else:
            raise TrackSpecError("Track spec path is required.")
        return TrackSpec(
            stem=self._stem_edit.text().strip() or spec.stem,
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

    def _on_source_changed(self, text: str) -> None:
        using_yaml = text == "YAML"
        for widget in self._source_controls:
            widget.setEnabled(using_yaml)
        for widget in (
            self._oval_length_spin,
            self._oval_width_spin,
            self._curve_amp_spin,
            self._curve_freq_spin,
        ):
            widget.setEnabled(not using_yaml)
        if not using_yaml and not self._stem_edit.text().strip():
            self._stem_edit.setText("oval_track")

    def _sync_output_dir(self) -> None:
        if self._output_dir_edit.text().strip():
            return
        stem = self._stem_edit.text().strip()
        if stem:
            self._output_dir_edit.setText(str(Path("sample_maps") / f"{stem}_map"))

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


class TrackSpecDialog(QDialog):
    """Dialog to build a basic track spec without a YAML file."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Track Spec")

        self._stem_edit = QLineEdit()

        self._table = QTableWidget(0, 2, self)
        self._table.setHorizontalHeaderLabels(["X", "Y"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        add_button = QPushButton("Add Point")
        add_button.clicked.connect(self._add_row)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._remove_selected)

        button_row = QHBoxLayout()
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        button_row.addStretch(1)

        form = QFormLayout()
        form.addRow("Stem", self._stem_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._table)
        layout.addLayout(button_row)
        layout.addWidget(button_box)

        for _ in range(4):
            self._add_row()

    def spec(self) -> TrackSpec:
        stem = self._stem_edit.text().strip()
        if not stem:
            raise TrackSpecError("Stem is required.")
        points = self._read_points()
        if len(points) < 4:
            raise TrackSpecError("At least four control points are required.")
        return TrackSpec(stem=stem, control_points=points)

    def _add_row(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem("0.0"))
        self._table.setItem(row, 1, QTableWidgetItem("0.0"))

    def _remove_selected(self) -> None:
        selected = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for row in selected:
            self._table.removeRow(row)

    def _read_points(self) -> list[Point2D]:
        points: list[Point2D] = []
        for row in range(self._table.rowCount()):
            x_item = self._table.item(row, 0)
            y_item = self._table.item(row, 1)
            if x_item is None or y_item is None:
                raise TrackSpecError("All control points must have X and Y values.")
            try:
                x = float(x_item.text())
                y = float(y_item.text())
            except ValueError as exc:
                raise TrackSpecError("Control points must be numeric.") from exc
            points.append(Point2D(x, y))
        return points
