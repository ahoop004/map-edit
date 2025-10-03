"""Helpers for exporting map rasters in alternative formats."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage


def export_png_as_pgm(source: Path, destination: Path) -> None:
    """Convert a raster image (PNG/etc.) into an 8-bit grayscale PGM."""
    image = QImage(str(source))
    if image.isNull():
        raise ValueError(f"Unable to load image: {source}")

    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not gray.save(str(destination), "PGM"):
        raise ValueError(f"Failed to save PGM file: {destination}")
