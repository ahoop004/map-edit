"""Utility helpers for showing modal progress while background tasks run."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Callable, Generator, TypeVar, cast

from PySide6.QtCore import QEventLoop, QObject, Qt, QThread
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

T = TypeVar("T")


class _TaskThread(QThread):
    def __init__(self, task: Callable[[], T], parent: QObject | None) -> None:
        super().__init__(parent)
        self._task = task
        self.value: T | None = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.value = self._task()
        except BaseException as exc:
            self.error = exc


@contextmanager
def show_busy_dialog(
    parent: QWidget | None, message: str, *, minimum_duration: int = 200
) -> Generator[QProgressDialog, None, None]:
    """Context manager that displays a busy indicator until the block exits."""

    dialog = QProgressDialog(parent)
    dialog.setLabelText(message)
    dialog.setCancelButton(None)
    dialog.setMinimumDuration(minimum_duration)
    dialog.setMinimum(0)
    dialog.setMaximum(0)  # Indeterminate
    dialog.setWindowTitle("Working…")
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.show()
    try:
        yield dialog
    finally:
        dialog.close()
        dialog.deleteLater()
        if parent is not None:
            parent.repaint()
        QApplication.processEvents()

def run_in_thread(task: Callable[[], T], *, parent: QObject | None = None) -> T:
    """Run a task in a worker thread while keeping the UI responsive."""
    if os.environ.get("MAP_EDITOR_BACKGROUND_TASKS") == "0":
        return task()

    thread = _TaskThread(task, parent)
    loop = QEventLoop()
    # Connect before starting: even an immediately completed task must wake the loop.
    thread.finished.connect(loop.quit)
    thread.start()
    loop.exec()
    thread.wait()
    thread.deleteLater()
    if thread.error is not None:
        raise thread.error
    return cast(T, thread.value)


__all__ = ["run_in_thread", "show_busy_dialog"]
