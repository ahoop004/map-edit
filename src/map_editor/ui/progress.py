"""Utility helpers for showing modal progress while background tasks run."""

from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Callable, Generator, Optional, TypeVar, cast

from PySide6.QtCore import QEventLoop, QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

T = TypeVar("T")


class _TaskRunner(QObject):
    finished = Signal(object, object)

    def __init__(self, task: Callable[[], T]) -> None:
        super().__init__()
        self._task = task

    @Slot()
    def run(self) -> None:
        try:
            result = self._task()
        except BaseException as exc:
            self.finished.emit(None, exc)
            return
        self.finished.emit(result, None)


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

def run_in_thread(task: Callable[[], T], *, parent: Optional[QObject] = None) -> T:
    """Run a task in a worker thread while keeping the UI responsive."""
    if os.environ.get("MAP_EDITOR_BACKGROUND_TASKS") != "1":
        return task()

    thread = QThread(parent)
    runner = _TaskRunner(task)
    runner.moveToThread(thread)

    result: dict[str, object] = {"value": None, "error": None}

    def _capture(value: object, error: object) -> None:
        result["value"] = value
        result["error"] = error

    runner.finished.connect(_capture)
    runner.finished.connect(thread.quit)
    runner.finished.connect(runner.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.started.connect(runner.run)

    thread.start()
    loop = QEventLoop()
    runner.finished.connect(loop.quit)
    loop.exec()

    if thread.isRunning():
        thread.wait()

    error = cast(Optional[BaseException], result["error"])
    if error is not None:
        raise error
    return cast(T, result["value"])


__all__ = ["run_in_thread", "show_busy_dialog"]
