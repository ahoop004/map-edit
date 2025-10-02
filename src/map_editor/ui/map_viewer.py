"""Map viewer widget for displaying track images and overlays."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)


class MapViewer(QGraphicsView):
    """Graphics view that renders the map image with support for overlays."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item = None
        self._message_item: Optional[QGraphicsTextItem] = None
        self._overlay_items: list[QGraphicsItem] = []

        self._zoom_factor = 1.25
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)

        self.show_message("Load a map to begin")

    def show_message(self, text: str) -> None:
        """Display a centered informational message instead of an image."""
        self._scene.clear()
        self._pixmap_item = None
        self._overlay_items.clear()

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
        self._overlay_items.clear()

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.resetTransform()
        self.fit_to_view()
        return True

    def clear_map(self) -> None:
        """Remove the current map display and show the default message."""
        self.show_message("Load a map to begin")

    def fit_to_view(self) -> None:
        """Fit the current pixmap into the viewport maintaining aspect ratio."""
        if self._pixmap_item:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    @property
    def has_map(self) -> bool:
        """Return True when a pixmap is currently displayed."""
        return self._pixmap_item is not None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (Qt naming)
        """Zoom the map in or out using the mouse wheel."""
        if not self.has_map:
            event.ignore()
            return

        zoom_in = event.angleDelta().y() > 0
        factor = self._zoom_factor if zoom_in else 1 / self._zoom_factor
        self.scale(factor, factor)

    def add_overlay_item(self, item: QGraphicsItem) -> None:
        """Add a pre-constructed overlay item to the scene."""
        self._overlay_items.append(item)
        self._scene.addItem(item)

    def set_overlay_items(self, items: Iterable[QGraphicsItem]) -> None:
        """Replace overlays with a new sequence of items."""
        self.clear_overlays()
        for item in items:
            self.add_overlay_item(item)

    def clear_overlays(self) -> None:
        """Remove all overlay items from the scene."""
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items.clear()
