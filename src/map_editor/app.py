"""Application bootstrap for the ROS map editor."""

from __future__ import annotations

import sys
from typing import Iterable

from PySide6.QtWidgets import QApplication


def create_application(argv: Iterable[str] | None = None) -> QApplication:
    """Create and configure the QApplication instance."""
    args = list(argv) if argv is not None else sys.argv
    app = QApplication(args)
    QApplication.setApplicationName("ROS Map Editor")
    QApplication.setOrganizationName("MapEdit")
    QApplication.setOrganizationDomain("mapedit.local")
    return app


def main(argv: Iterable[str] | None = None) -> int:
    """Entry point that boots the GUI event loop."""
    app = create_application(argv)

    from map_editor.ui.main_window import MainWindow  # Lazy import to avoid cycles during bootstrap

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
