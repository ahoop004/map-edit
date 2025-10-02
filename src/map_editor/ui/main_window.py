"""Main window definition for the map editor."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QWidget,
)

from map_editor.ui.map_viewer import MapViewer


class MainWindow(QMainWindow):
    """Top-level window that hosts the map canvas and editor panels."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ROS Map Editor")
        self.resize(1280, 720)

        self._current_map: Optional[Path] = None
        self._map_viewer = MapViewer(self)

        self._init_status_bar()
        self._init_central_widget()
        self._create_actions()
        self._create_menus()
        self._create_docks()

    def _init_status_bar(self) -> None:
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

    def _init_central_widget(self) -> None:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._map_viewer)
        self.setCentralWidget(container)

    def _create_actions(self) -> None:
        self._action_open = QAction("&Open Map…", self)
        self._action_open.setShortcut("Ctrl+O")
        self._action_open.triggered.connect(self._select_map_bundle)

        self._action_save = QAction("&Save Map", self)
        self._action_save.setShortcut("Ctrl+S")
        self._action_save.triggered.connect(self._save_map_bundle)
        self._action_save.setEnabled(False)

        self._action_exit = QAction("E&xit", self)
        self._action_exit.setShortcut("Ctrl+Q")
        self._action_exit.triggered.connect(self.close)

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self._action_open)
        file_menu.addAction(self._action_save)
        file_menu.addSeparator()
        file_menu.addAction(self._action_exit)

    def _create_docks(self) -> None:
        metadata_dock = QDockWidget("Metadata", self)
        metadata_dock.setObjectName("metadataDock")
        metadata_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        placeholder = QLabel("Metadata panel coming soon", metadata_dock)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        metadata_dock.setWidget(placeholder)
        metadata_dock.setMinimumWidth(280)
        metadata_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, metadata_dock)

    def _select_map_bundle(self) -> None:
        start_dir = str(self._current_map.parent if self._current_map else Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open map YAML",
            start_dir,
            "ROS map YAML files (*.yaml);;All files (*)",
        )
        if not file_path:
            return

        self._current_map = Path(file_path)
        self.statusBar().showMessage(f"Loaded metadata: {self._current_map.name}")
        self._map_viewer.show_message("YAML parsing not implemented yet")
        self._action_save.setEnabled(True)

    def _save_map_bundle(self) -> None:
        if not self._current_map:
            QMessageBox.warning(self, "No map loaded", "Load a map before saving.")
            return

        # Placeholder save logic; will integrate with map persistence services.
        self.statusBar().showMessage(f"Saved (placeholder): {self._current_map.name}")
