"""Map viewer widget for displaying track images and overlays."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem, QGraphicsView


class MapViewer(QGraphicsView):
    """Simple graphics view that renders a map image and overlay placeholders."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item = None
        self._message_item: Optional[QGraphicsTextItem] = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)

        self.show_message("Load a map to begin")

    def show_message(self, text: str) -> None:
        """Display a centered informational message instead of an image."""
        self._scene.clear()
        self._pixmap_item = None

        message_item = self._scene.addText(text)
        message_item.setDefaultTextColor(Qt.GlobalColor.lightGray)
        bounding = message_item.boundingRect()
        message_item.setPos(-bounding.width() / 2, -bounding.height() / 2)
        self._scene.setSceneRect(message_item.sceneBoundingRect())
        self._message_item = message_item
        self.resetTransform()

    def set_map_image(self, image_path: Path) -> bool:
        """Load and display a map image from disk."""
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.show_message(f"Failed to load image: {image_path.name}")
            return False

        self._scene.clear()
        self._message_item = None

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.resetTransform()
        self.centerOn(self._pixmap_item)
        return True

    def clear_map(self) -> None:
        """Remove the current map display and show the default message."""
        self.show_message("Load a map to begin")

    @property
    def has_map(self) -> bool:
        """Return True when a pixmap is currently displayed."""
        return self._pixmap_item is not None
