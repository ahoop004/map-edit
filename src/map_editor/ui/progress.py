"""Utility helpers for showing modal progress while background tasks run."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from PySide6.QtWidgets import QProgressDialog, QWidget


@contextmanager
def show_busy_dialog(
    parent: Optional[QWidget], message: str, *, minimum_duration: int = 200
) -> Generator[QProgressDialog, None, None]:
    """Context manager that displays a busy indicator until the block exits."""

    dialog = QProgressDialog(parent)
    dialog.setLabelText(message)
    dialog.setCancelButton(None)
    dialog.setMinimumDuration(minimum_duration)
    dialog.setMinimum(0)
    dialog.setMaximum(0)  # Indeterminate
    dialog.setWindowTitle("Working…")
    dialog.setModal(True)
    dialog.show()
    try:
        yield dialog
    finally:
        dialog.cancel()


__all__ = ["show_busy_dialog"]
