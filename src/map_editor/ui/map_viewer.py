"""Map viewer widget for displaying track images and overlays."""

from __future__ import annotations

import math
from enum import Enum, auto
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QPen, QPainter, QPixmap, QWheelEvent, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from map_editor.models.annotations import MapAnnotations, Point2D, Pose2D
from map_editor.models.map_bundle import MapMetadata
from map_editor.models.spawn_stamp import SpawnStampSettings


class MapViewer(QGraphicsView):
    """Graphics view that renders the map image with support for overlays."""

    _CAR_LENGTH_M = 0.434  # F1TENTH F110 RC car nose-to-tail length
    _CAR_WIDTH_M = 0.1738  # F1TENTH F110 RC car side-to-side width
    _SPAWN_HEADING_LENGTH_M = 0.5

    class PlacementMode(Enum):
        IDLE = auto()
        SPAWN = auto()
        START_FINISH = auto()
        CENTERLINE = auto()

    spawnPlacementCompleted = Signal(float, float)
    spawnStampPlacementCompleted = Signal(object)
    startFinishPlacementCompleted = Signal(float, float, float, float)
    placementStatusChanged = Signal(str)
    placementCancelled = Signal()
    centerlinePlacementFinished = Signal(object)

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
        self._centerline_preview_items: list[QGraphicsItem] = []
        self._centerline_temp_points: list[Point2D] = []
        self._spawn_preview_polygons: list[QGraphicsPolygonItem] = []
        self._spawn_preview_headings: list[QGraphicsLineItem] = []
        self._spawn_preview_theta: float = 0.0
        self._spawn_stamp_settings = SpawnStampSettings()
        self._spawn_stamp_active: bool = False
        self._spawn_stamp_anchor: Optional[tuple[float, float]] = None
        self._spawn_stamp_dragging: bool = False
        self._spawn_stamp_preview_poses: list[Pose2D] = []
        self._annotations_cache = MapAnnotations()

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

    def set_spawn_stamp_settings(self, settings: SpawnStampSettings) -> None:
        """Update stamp placement configuration used during spawn placement."""
        self._spawn_stamp_settings = settings
        if self._placement_mode is MapViewer.PlacementMode.SPAWN:
            # Refresh preview using new settings.
            self._refresh_spawn_preview()

    def show_message(self, text: str) -> None:
        """Display a centered informational message instead of an image."""
        self._scene.clear()
        self._pixmap_item = None
        self._overlay_items.clear()
        self.cancel_placement()
        self._remove_spawn_preview_items()

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
        for item in self._centerline_preview_items:
            self._scene.removeItem(item)
        self._centerline_preview_items.clear()
        self._centerline_temp_points.clear()
        self._remove_spawn_preview_items()

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

        self._annotations_cache = annotations

        overlay_items: list[QGraphicsItem] = []
        marker_radius = self._marker_radius()

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
            car_polygon = self._spawn_vehicle_polygon(spawn.pose.x, spawn.pose.y, spawn.pose.theta)
            polygon_item = QGraphicsPolygonItem(QPolygonF(car_polygon))
            pen_width = max(1.2, marker_radius * 0.25)
            polygon_item.setPen(QPen(Qt.GlobalColor.green, pen_width))
            fill_color = QColor(Qt.GlobalColor.green)
            fill_color.setAlpha(64)
            polygon_item.setBrush(QBrush(fill_color))
            polygon_item.setZValue(9)
            overlay_items.append(polygon_item)

            heading_start_scene, heading_end_scene = self._spawn_heading_points(
                spawn.pose.x,
                spawn.pose.y,
                spawn.pose.theta,
            )
            heading = QGraphicsLineItem(
                heading_start_scene.x(),
                heading_start_scene.y(),
                heading_end_scene.x(),
                heading_end_scene.y(),
            )
            heading.setPen(QPen(Qt.GlobalColor.yellow, max(1.0, marker_radius * 0.2)))
            heading.setZValue(9.5)
            overlay_items.append(heading)

        if len(annotations.centerline) >= 2:
            pen = QPen(Qt.GlobalColor.cyan, max(1.5, marker_radius * 0.25))
            pen.setStyle(Qt.PenStyle.DashLine)
            prev_scene = self._world_to_scene(
                annotations.centerline[0].x, annotations.centerline[0].y
            )
            for point in annotations.centerline[1:]:
                curr_scene = self._world_to_scene(point.x, point.y)
                segment = QGraphicsLineItem(
                    prev_scene.x(),
                    prev_scene.y(),
                    curr_scene.x(),
                    curr_scene.y(),
                )
                segment.setPen(pen)
                segment.setZValue(8)
                overlay_items.append(segment)
                prev_scene = curr_scene

        self.set_overlay_items(overlay_items)
        # Refresh diagnostic overlay to ensure Z-order remains consistent.
        self._update_diagnostic_overlay(self._diagnostic_has_issues)

    # Placement workflow -------------------------------------------------

    def begin_spawn_placement(self, stamp_mode: bool = False) -> bool:
        if not self._is_transform_ready():
            self.placementStatusChanged.emit(
                "Load a map (with metadata) before placing spawn points."
            )
            return False

        self._spawn_stamp_active = stamp_mode and self._spawn_stamp_settings.enabled
        self._spawn_stamp_anchor = None
        self._spawn_stamp_dragging = False
        self._spawn_stamp_preview_poses = []
        self._spawn_preview_theta = 0.0
        self._set_placement_mode(MapViewer.PlacementMode.SPAWN)

        if self._spawn_stamp_active and self._spawn_stamp_settings.count > 1:
            self.placementStatusChanged.emit(
                "Stamp placement: click near the centerline to auto-align, or click and drag to orient."
            )
        else:
            self.placementStatusChanged.emit(
                "Click on the map to place a spawn point (Esc/right-click to cancel)."
            )
        return True

    def begin_start_finish_placement(self) -> bool:
        if not self._is_transform_ready():
            self.placementStatusChanged.emit("Load a map (with metadata) before placing the start/finish line.")
            return False
        self._set_placement_mode(MapViewer.PlacementMode.START_FINISH)
        self._pending_line_start = None
        self.placementStatusChanged.emit("Click to choose the start point, then the end point (Esc/right-click to cancel).")
        return True

    def begin_centerline_placement(self) -> bool:
        if not self._is_transform_ready():
            self.placementStatusChanged.emit("Load a map (with metadata) before placing the centerline.")
            return False
        self._set_placement_mode(MapViewer.PlacementMode.CENTERLINE)
        self._centerline_temp_points.clear()
        self._update_centerline_preview()
        self.placementStatusChanged.emit(
            "Left-click to add centerline points, Enter to finish, Esc/right-click to cancel."
        )
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
            if self._placement_mode is MapViewer.PlacementMode.CENTERLINE and self._centerline_temp_points:
                self._finish_centerline_placement()
            else:
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
            self._handle_spawn_press(world_x, world_y)
            event.accept()
            return
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
        elif self._placement_mode is MapViewer.PlacementMode.CENTERLINE:
            point = Point2D(world_x, world_y)
            self._centerline_temp_points.append(point)
            self._update_centerline_preview()
            self.placementStatusChanged.emit(
                f"Centerline points: {len(self._centerline_temp_points)} (Enter/right-click to finish, Esc to cancel)."
            )
        event.accept()

    def mouseMoveEvent(self, event):  # type: ignore[override]
        if self._placement_mode is MapViewer.PlacementMode.SPAWN and self.has_map:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._point_in_pixmap(scene_pos):
                world_point = self._scene_to_world(scene_pos)
                if world_point is not None:
                    self._handle_spawn_move(world_point[0], world_point[1])
                else:
                    self._set_spawn_preview_visible(0)
            else:
                self._set_spawn_preview_visible(0)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        if (
            self._placement_mode is MapViewer.PlacementMode.SPAWN
            and self.has_map
            and event.button() == Qt.MouseButton.LeftButton
        ):
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._point_in_pixmap(scene_pos):
                world_point = self._scene_to_world(scene_pos)
                if world_point is not None:
                    self._handle_spawn_release(world_point[0], world_point[1])
                else:
                    self._finalize_spawn_selection(self._spawn_stamp_preview_poses)
            else:
                self._finalize_spawn_selection(self._spawn_stamp_preview_poses)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape and self._placement_mode is not MapViewer.PlacementMode.IDLE:
            self.cancel_placement()
            event.accept()
            return
        if (
            self._placement_mode is MapViewer.PlacementMode.CENTERLINE
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            self._finish_centerline_placement()
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
        if mode is not MapViewer.PlacementMode.START_FINISH:
            self._pending_line_start = None
        if mode is not MapViewer.PlacementMode.CENTERLINE:
            self._centerline_temp_points.clear()
            self._update_centerline_preview()
        if mode is MapViewer.PlacementMode.SPAWN:
            self._spawn_stamp_anchor = None
            self._spawn_stamp_dragging = False
            self._spawn_stamp_preview_poses = []
            self._set_spawn_preview_visible(0)
        else:
            self._remove_spawn_preview_items()
            self._spawn_stamp_anchor = None
            self._spawn_stamp_dragging = False
            self._spawn_stamp_preview_poses = []

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

    def _spawn_vehicle_polygon(self, x: float, y: float, theta: float) -> list[QPointF]:
        """Return scene-space polygon corners for the car footprint."""

        if self._metadata:
            half_length_world = self._CAR_LENGTH_M / 2.0
            half_width_world = self._CAR_WIDTH_M / 2.0

            cos_theta = math.cos(theta)
            sin_theta = math.sin(theta)

            local_corners_world = (
                (half_length_world, half_width_world),
                (half_length_world, -half_width_world),
                (-half_length_world, -half_width_world),
                (-half_length_world, half_width_world),
            )

            scene_points = []
            for local_x, local_y in local_corners_world:
                world_x = x + local_x * cos_theta - local_y * sin_theta
                world_y = y + local_x * sin_theta + local_y * cos_theta
                scene_points.append(self._world_to_scene(world_x, world_y))
            return scene_points

        # Fallback: approximate footprint directly in scene space when metadata is missing.
        scene_center = self._world_to_scene(x, y)
        base_radius = self._marker_radius()
        half_length_scene = base_radius * 1.2
        half_width_scene = half_length_scene * (self._CAR_WIDTH_M / self._CAR_LENGTH_M)

        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)

        local_corners_scene = (
            (half_length_scene, half_width_scene),
            (half_length_scene, -half_width_scene),
            (-half_length_scene, -half_width_scene),
            (-half_length_scene, half_width_scene),
        )

        return [
            QPointF(
                scene_center.x() + local_x * cos_theta - local_y * sin_theta,
                scene_center.y() + local_x * sin_theta + local_y * cos_theta,
            )
            for local_x, local_y in local_corners_scene
        ]

    def _spawn_heading_points(self, x: float, y: float, theta: float) -> tuple[QPointF, QPointF]:
        start_scene = self._world_to_scene(x, y)
        length = self._SPAWN_HEADING_LENGTH_M
        end_scene = self._world_to_scene(
            x + math.cos(theta) * length,
            y + math.sin(theta) * length,
        )
        return start_scene, end_scene

    def _ensure_spawn_preview_capacity(self, count: int) -> None:
        while len(self._spawn_preview_polygons) < count:
            polygon_item = QGraphicsPolygonItem()
            polygon_item.setVisible(False)
            polygon_item.setZValue(9.2)
            self._scene.addItem(polygon_item)
            self._spawn_preview_polygons.append(polygon_item)
        while len(self._spawn_preview_headings) < count:
            heading_item = QGraphicsLineItem()
            heading_item.setVisible(False)
            heading_item.setZValue(9.6)
            self._scene.addItem(heading_item)
            self._spawn_preview_headings.append(heading_item)

    def _set_spawn_preview_visible(self, count: int) -> None:
        for index, item in enumerate(self._spawn_preview_polygons):
            item.setVisible(index < count)
        for index, item in enumerate(self._spawn_preview_headings):
            item.setVisible(index < count)

    def _remove_spawn_preview_items(self) -> None:
        for item in self._spawn_preview_polygons:
            self._scene.removeItem(item)
        for item in self._spawn_preview_headings:
            self._scene.removeItem(item)
        self._spawn_preview_polygons.clear()
        self._spawn_preview_headings.clear()
        self._spawn_stamp_preview_poses = []

    def _refresh_spawn_preview(self) -> None:
        if self._spawn_stamp_anchor is None:
            self._set_spawn_preview_visible(0)
            return
        poses = self._generate_stamp_poses(
            self._spawn_stamp_anchor[0],
            self._spawn_stamp_anchor[1],
            self._spawn_preview_theta,
        )
        self._update_spawn_preview(poses)

    def _generate_stamp_poses(self, anchor_x: float, anchor_y: float, theta: float) -> list[Pose2D]:
        settings = self._spawn_stamp_settings
        count = settings.count if self._spawn_stamp_active else 1
        count = max(1, count)

        if count == 1:
            return [Pose2D(anchor_x, anchor_y, theta)]

        forward_x = math.cos(theta)
        forward_y = math.sin(theta)
        left_x = -forward_y
        left_y = forward_x

        lane_offset = settings.lateral_spacing / 2.0
        poses: list[Pose2D] = []
        columns = (count + 1) // 2

        for column in range(columns):
            offset = settings.longitudinal_spacing * column
            base_x = anchor_x + forward_x * offset
            base_y = anchor_y + forward_y * offset

            left_pos = Pose2D(
                base_x + left_x * lane_offset,
                base_y + left_y * lane_offset,
                theta,
            )
            poses.append(left_pos)
            if len(poses) == count:
                break

            right_pos = Pose2D(
                base_x - left_x * lane_offset,
                base_y - left_y * lane_offset,
                theta,
            )
            poses.append(right_pos)

        return poses

    def _closest_centerline_frame(
        self, x: float, y: float
    ) -> Optional[tuple[float, float, float, float]]:
        points = self._annotations_cache.centerline
        if len(points) < 2:
            return None

        best_distance = float("inf")
        best_point: Optional[tuple[float, float]] = None
        best_theta = 0.0

        for start, end in zip(points[:-1], points[1:]):
            sx, sy = start.x, start.y
            ex, ey = end.x, end.y
            dx = ex - sx
            dy = ey - sy
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq == 0:
                continue
            t = ((x - sx) * dx + (y - sy) * dy) / seg_len_sq
            t_clamped = max(0.0, min(1.0, t))
            proj_x = sx + dx * t_clamped
            proj_y = sy + dy * t_clamped
            distance = math.hypot(x - proj_x, y - proj_y)
            if distance < best_distance:
                best_distance = distance
                best_point = (proj_x, proj_y)
                best_theta = math.atan2(dy, dx)

        if best_point is None:
            return None
        return best_point[0], best_point[1], best_theta, best_distance

    def _handle_spawn_press(self, world_x: float, world_y: float) -> None:
        alignment = self._closest_centerline_frame(world_x, world_y)
        auto_radius = self._spawn_stamp_settings.auto_align_radius
        if (
            alignment is not None
            and self._spawn_stamp_settings.auto_align_radius > 0
            and alignment[3] <= auto_radius
        ):
            anchor_x, anchor_y, theta, _ = alignment
            self._spawn_stamp_anchor = (anchor_x, anchor_y)
            self._spawn_preview_theta = theta
            self._spawn_stamp_dragging = False
            poses = self._generate_stamp_poses(anchor_x, anchor_y, theta)
            self._update_spawn_preview(poses)
            self.placementStatusChanged.emit(
                "Stamp aligned to centerline. Release to confirm or Esc/right-click to cancel."
            )
        else:
            self._spawn_stamp_anchor = (world_x, world_y)
            self._spawn_stamp_dragging = True
            if not self._spawn_stamp_preview_poses:
                self._spawn_preview_theta = 0.0
            poses = self._generate_stamp_poses(world_x, world_y, self._spawn_preview_theta)
            self._update_spawn_preview(poses)
            self.placementStatusChanged.emit("Drag to set heading, then release to confirm.")

    def _handle_spawn_move(self, world_x: float, world_y: float) -> None:
        if self._spawn_stamp_anchor is None:
            alignment = self._closest_centerline_frame(world_x, world_y)
            auto_radius = self._spawn_stamp_settings.auto_align_radius
            if (
                alignment is not None
                and self._spawn_stamp_settings.auto_align_radius > 0
                and alignment[3] <= auto_radius
            ):
                anchor_x, anchor_y, theta, _ = alignment
            else:
                anchor_x, anchor_y = world_x, world_y
                theta = self._spawn_preview_theta if self._spawn_stamp_preview_poses else 0.0
            poses = self._generate_stamp_poses(anchor_x, anchor_y, theta)
            self._spawn_preview_theta = theta
            self._update_spawn_preview(poses)
            return

        anchor_x, anchor_y = self._spawn_stamp_anchor
        if self._spawn_stamp_dragging:
            dx = world_x - anchor_x
            dy = world_y - anchor_y
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                self._spawn_preview_theta = math.atan2(dy, dx)
        poses = self._generate_stamp_poses(anchor_x, anchor_y, self._spawn_preview_theta)
        self._update_spawn_preview(poses)

    def _handle_spawn_release(self, world_x: float, world_y: float) -> None:
        if self._spawn_stamp_anchor is None:
            self._finalize_spawn_selection(self._spawn_stamp_preview_poses)
            return

        anchor_x, anchor_y = self._spawn_stamp_anchor
        if self._spawn_stamp_dragging:
            dx = world_x - anchor_x
            dy = world_y - anchor_y
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                self._spawn_preview_theta = math.atan2(dy, dx)
        poses = self._generate_stamp_poses(anchor_x, anchor_y, self._spawn_preview_theta)
        self._update_spawn_preview(poses)
        self._finalize_spawn_selection(poses)

    def _finalize_spawn_selection(self, poses: list[Pose2D]) -> None:
        count = len(poses)
        self._set_placement_mode(MapViewer.PlacementMode.IDLE)
        if count == 0:
            self.placementStatusChanged.emit("Spawn placement cancelled.")
            return

        if self._spawn_stamp_active and self._spawn_stamp_settings.count > 1 and count > 1:
            self.placementStatusChanged.emit(
                f"Stamp placed with {count} spawn point(s)."
            )
            self.spawnStampPlacementCompleted.emit(poses)
        else:
            pose = poses[0]
            self.placementStatusChanged.emit(
                f"Spawn point selected at ({pose.x:.2f}, {pose.y:.2f})."
            )
            self.spawnPlacementCompleted.emit(pose.x, pose.y)

    def _update_spawn_preview(self, poses: list[Pose2D]) -> None:
        count = len(poses)
        if count == 0:
            self._set_spawn_preview_visible(0)
            self._spawn_stamp_preview_poses = []
            return

        self._ensure_spawn_preview_capacity(count)
        marker_radius = self._marker_radius()
        pen_width = max(1.0, marker_radius * 0.25)
        heading_pen_width = max(0.8, marker_radius * 0.2)

        outline_pen = QPen(Qt.GlobalColor.green, pen_width)
        outline_pen.setStyle(Qt.PenStyle.DashLine)
        fill_color = QColor(Qt.GlobalColor.green)
        fill_color.setAlpha(32)
        heading_pen = QPen(Qt.GlobalColor.yellow, heading_pen_width)
        heading_pen.setStyle(Qt.PenStyle.DashLine)

        for index, pose in enumerate(poses):
            polygon_item = self._spawn_preview_polygons[index]
            polygon_item.setPen(outline_pen)
            polygon_item.setBrush(QBrush(fill_color))
            polygon_item.setPolygon(QPolygonF(self._spawn_vehicle_polygon(pose.x, pose.y, pose.theta)))
            polygon_item.setVisible(True)

            heading_item = self._spawn_preview_headings[index]
            start_scene, end_scene = self._spawn_heading_points(pose.x, pose.y, pose.theta)
            heading_item.setPen(heading_pen)
            heading_item.setLine(
                start_scene.x(),
                start_scene.y(),
                end_scene.x(),
                end_scene.y(),
            )
            heading_item.setVisible(True)

        for index in range(count, len(self._spawn_preview_polygons)):
            self._spawn_preview_polygons[index].setVisible(False)
        for index in range(count, len(self._spawn_preview_headings)):
            self._spawn_preview_headings[index].setVisible(False)

        self._spawn_preview_theta = poses[0].theta
        self._spawn_stamp_preview_poses = [
            Pose2D(pose.x, pose.y, pose.theta) for pose in poses
        ]

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

    def _update_centerline_preview(self) -> None:
        for item in self._centerline_preview_items:
            self._scene.removeItem(item)
        self._centerline_preview_items.clear()

        if self._placement_mode is not MapViewer.PlacementMode.CENTERLINE or len(self._centerline_temp_points) < 1:
            return

        pen = QPen(Qt.GlobalColor.cyan, 1.5)
        pen.setStyle(Qt.PenStyle.DotLine)
        prev_scene = self._world_to_scene(
            self._centerline_temp_points[0].x,
            self._centerline_temp_points[0].y,
        )
        marker_radius = self._marker_radius() * 0.5

        for point in self._centerline_temp_points[1:]:
            curr_scene = self._world_to_scene(point.x, point.y)
            segment = QGraphicsLineItem(
                prev_scene.x(),
                prev_scene.y(),
                curr_scene.x(),
                curr_scene.y(),
            )
            segment.setPen(pen)
            segment.setZValue(15)
            self._centerline_preview_items.append(segment)
            self._scene.addItem(segment)
            prev_scene = curr_scene

        # Draw markers on each point
        for pt in self._centerline_temp_points:
            scene_pt = self._world_to_scene(pt.x, pt.y)
            marker = QGraphicsEllipseItem(
                scene_pt.x() - marker_radius,
                scene_pt.y() - marker_radius,
                marker_radius * 2,
                marker_radius * 2,
            )
            marker.setBrush(Qt.GlobalColor.cyan)
            marker.setPen(QPen(Qt.GlobalColor.cyan))
            marker.setZValue(16)
            self._centerline_preview_items.append(marker)
            self._scene.addItem(marker)

    def _finish_centerline_placement(self) -> None:
        if len(self._centerline_temp_points) < 2:
            self.placementStatusChanged.emit("Centerline requires at least two points.")
            self.cancel_placement()
            return
        points = [Point2D(p.x, p.y) for p in self._centerline_temp_points]
        self._set_placement_mode(MapViewer.PlacementMode.IDLE)
        self.placementStatusChanged.emit(
            f"Centerline placement complete ({len(points)} point(s))."
        )
        self.centerlinePlacementFinished.emit(points)

    def complete_centerline_placement(self) -> None:
        if self._placement_mode is MapViewer.PlacementMode.CENTERLINE:
            self._finish_centerline_placement()
