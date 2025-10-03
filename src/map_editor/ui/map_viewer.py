"""Map viewer widget for displaying track images and overlays."""

from __future__ import annotations

import math
from enum import Enum, auto
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QCursor, QPen, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from map_editor.models.annotations import MapAnnotations
from map_editor.models.map_bundle import MapMetadata


class MapViewer(QGraphicsView):
    """Graphics view that renders the map image with support for overlays."""

    class PlacementMode(Enum):
        IDLE = auto()
        SPAWN = auto()
        START_FINISH = auto()

    spawnPlacementCompleted = Signal(float, float)
    startFinishPlacementCompleted = Signal(float, float, float, float)
    placementStatusChanged = Signal(str)
    placementCancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item = None
        self._message_item: Optional[QGraphicsTextItem] = None
        self._overlay_items: list[QGraphicsItem] = []
        self._placement_mode = MapViewer.PlacementMode.IDLE
        self._pending_line_start: Optional[QPointF] = None
        self._metadata: Optional[MapMetadata] = None
        self._pixmap_width: float = 0.0
        self._pixmap_height: float = 0.0
        self._diagnostic_overlay: Optional[QGraphicsItem] = None
        self._diagnostic_highlight_enabled: bool = True
        self._diagnostic_has_issues: bool = False

        self._zoom_factor = 1.25
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)

        self.show_message("Load a map to begin")

    # Public API ---------------------------------------------------------

    def set_metadata(self, metadata: Optional[MapMetadata]) -> None:
        self._metadata = metadata

    def show_message(self, text: str) -> None:
        """Display a centered informational message instead of an image."""
        self._scene.clear()
        self._pixmap_item = None
        self._overlay_items.clear()
        self.cancel_placement()

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
        self.cancel_placement()
        self._diagnostic_overlay = None

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_width = float(pixmap.width())
        self._pixmap_height = float(pixmap.height())
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

    # Overlay management -------------------------------------------------

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

    def set_diagnostic_highlight(self, enabled: bool, has_issues: bool) -> None:
        self._diagnostic_highlight_enabled = enabled
        self._update_diagnostic_overlay(has_issues)

    def update_annotations(self, annotations: MapAnnotations) -> None:
        """Refresh overlay items based on the current annotations."""
        if not self.has_map:
            return

        overlay_items: list[QGraphicsItem] = []
        marker_radius = self._marker_radius()
        heading_length_m = 0.5

        if annotations.start_finish_line is not None:
            line = annotations.start_finish_line.segment
            start_scene = self._world_to_scene(line.start.x, line.start.y)
            end_scene = self._world_to_scene(line.end.x, line.end.y)
            item = QGraphicsLineItem(start_scene.x(), start_scene.y(), end_scene.x(), end_scene.y())
            pen = QPen(Qt.GlobalColor.red, max(2.0, marker_radius * 0.3))
            item.setPen(pen)
            item.setZValue(10)
            overlay_items.append(item)

        for spawn in annotations.spawn_points:
            scene_center = self._world_to_scene(spawn.pose.x, spawn.pose.y)
            marker = QGraphicsEllipseItem(
                scene_center.x() - marker_radius,
                scene_center.y() - marker_radius,
                marker_radius * 2,
                marker_radius * 2,
            )
            marker.setPen(QPen(Qt.GlobalColor.green, max(1.5, marker_radius * 0.25)))
            marker.setZValue(9)
            overlay_items.append(marker)

            heading_end_world_x = spawn.pose.x + math.cos(spawn.pose.theta) * heading_length_m
            heading_end_world_y = spawn.pose.y + math.sin(spawn.pose.theta) * heading_length_m
            heading_end_scene = self._world_to_scene(heading_end_world_x, heading_end_world_y)
            heading = QGraphicsLineItem(
                scene_center.x(),
                scene_center.y(),
                heading_end_scene.x(),
                heading_end_scene.y(),
            )
            heading.setPen(QPen(Qt.GlobalColor.yellow, max(1.0, marker_radius * 0.2)))
            heading.setZValue(9.5)
            overlay_items.append(heading)

        self.set_overlay_items(overlay_items)
        # Refresh diagnostic overlay to ensure Z-order remains consistent.
        self._update_diagnostic_overlay(self._diagnostic_has_issues)

    # Placement workflow -------------------------------------------------

    def begin_spawn_placement(self) -> bool:
        if not self._is_transform_ready():
            self.placementStatusChanged.emit("Load a map (with metadata) before placing spawn points.")
            return False
        self._set_placement_mode(MapViewer.PlacementMode.SPAWN)
        self._pending_line_start = None
        self.placementStatusChanged.emit("Click on the map to place a spawn point (Esc/right-click to cancel).")
        return True

    def begin_start_finish_placement(self) -> bool:
        if not self._is_transform_ready():
            self.placementStatusChanged.emit("Load a map (with metadata) before placing the start/finish line.")
            return False
        self._set_placement_mode(MapViewer.PlacementMode.START_FINISH)
        self._pending_line_start = None
        self.placementStatusChanged.emit("Click to choose the start point, then the end point (Esc/right-click to cancel).")
        return True

    def cancel_placement(self) -> None:
        if self._placement_mode is MapViewer.PlacementMode.IDLE:
            return
        self._set_placement_mode(MapViewer.PlacementMode.IDLE)
        self._pending_line_start = None
        self.placementStatusChanged.emit("Placement cancelled.")
        self.placementCancelled.emit()

    def placement_mode(self) -> PlacementMode:
        return self._placement_mode

    # Event overrides ----------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (Qt naming)
        """Zoom the map in or out using the mouse wheel or trackpad."""
        if not self.has_map:
            event.ignore()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        zoom_in = delta > 0
        factor = self._zoom_factor if zoom_in else 1 / self._zoom_factor
        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):  # type: ignore[override]
        if self._placement_mode is MapViewer.PlacementMode.IDLE or not self.has_map:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.RightButton:
            self.cancel_placement()
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        if not self._point_in_pixmap(scene_pos):
            event.ignore()
            return

        world_point = self._scene_to_world(scene_pos)
        if world_point is None:
            event.ignore()
            return
        world_x, world_y = world_point

        if self._placement_mode is MapViewer.PlacementMode.SPAWN:
            self._set_placement_mode(MapViewer.PlacementMode.IDLE)
            self.placementStatusChanged.emit(
                f"Spawn point selected at ({world_x:.2f}, {world_y:.2f})."
            )
            self.spawnPlacementCompleted.emit(world_x, world_y)
        elif self._placement_mode is MapViewer.PlacementMode.START_FINISH:
            if self._pending_line_start is None:
                self._pending_line_start = QPointF(world_x, world_y)
                self.placementStatusChanged.emit(
                    f"Start point set at ({world_x:.2f}, {world_y:.2f}). Click to set the finish point."
                )
            else:
                start = self._pending_line_start
                self._pending_line_start = None
                self._set_placement_mode(MapViewer.PlacementMode.IDLE)
                self.placementStatusChanged.emit("Start/finish line points selected.")
                self.startFinishPlacementCompleted.emit(
                    start.x(),
                    start.y(),
                    world_x,
                    world_y,
                )
        event.accept()

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape and self._placement_mode is not MapViewer.PlacementMode.IDLE:
            self.cancel_placement()
            event.accept()
            return
        super().keyPressEvent(event)

    # Internal helpers ---------------------------------------------------

    def _set_placement_mode(self, mode: PlacementMode) -> None:
        self._placement_mode = mode
        if mode is MapViewer.PlacementMode.IDLE:
            self.unsetCursor()
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _is_transform_ready(self) -> bool:
        return self.has_map and self._metadata is not None and self._pixmap_height > 0

    def _point_in_pixmap(self, scene_pos: QPointF) -> bool:
        if not self._pixmap_item:
            return False
        item_point = self._pixmap_item.mapFromScene(scene_pos)
        return self._pixmap_item.contains(item_point)

    def _world_to_scene(self, x: float, y: float) -> QPointF:
        if not self._metadata or self._pixmap_height == 0:
            return QPointF(x, -y)
        pixel_x = (x - self._metadata.origin_x) / self._metadata.resolution
        pixel_y_from_origin = (y - self._metadata.origin_y) / self._metadata.resolution
        scene_x = pixel_x
        scene_y = self._pixmap_height - pixel_y_from_origin
        return QPointF(scene_x, scene_y)

    def _scene_to_world(self, scene_pos: QPointF) -> Optional[tuple[float, float]]:
        if not self._metadata or self._pixmap_height == 0:
            return None
        pixel_x = scene_pos.x()
        pixel_y_top = scene_pos.y()
        pixel_y_from_origin = self._pixmap_height - pixel_y_top
        world_x = self._metadata.origin_x + pixel_x * self._metadata.resolution
        world_y = self._metadata.origin_y + pixel_y_from_origin * self._metadata.resolution
        return world_x, world_y

    def _marker_radius(self) -> float:
        if not self._metadata:
            return 8.0
        pixels_per_meter = 1.0 / self._metadata.resolution
        return max(4.0, pixels_per_meter * 0.15)

    def _update_diagnostic_overlay(self, has_issues: bool) -> None:
        if not self._pixmap_item:
            return
        if self._diagnostic_overlay is not None:
            self._scene.removeItem(self._diagnostic_overlay)
            self._diagnostic_overlay = None

        self._diagnostic_has_issues = has_issues

        if self._diagnostic_highlight_enabled and self._diagnostic_has_issues:
            rect = self._pixmap_item.boundingRect()
            overlay = self._scene.addRect(rect, pen=QPen(Qt.GlobalColor.red, 2))
            overlay.setBrush(Qt.GlobalColor.transparent)
            overlay.setZValue(20)
            self._diagnostic_overlay = overlay
