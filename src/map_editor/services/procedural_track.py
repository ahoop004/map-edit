"""Procedural track generation utilities."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable, Sequence

import yaml
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from map_editor.exporters.centerline import CenterlineSample, export_centerline_csv, resample_centerline
from map_editor.models.annotations import MapAnnotations, Point2D
from map_editor.services.wall_extraction import export_walls_csv
from map_editor.services.yaml_serializer import MapYamlDocument, dump_map_yaml


@dataclass(frozen=True)
class TrackSpec:
    stem: str
    control_points: list[Point2D]
    track_width: float = 2.2
    centerline_spacing: float = 0.2
    resolution: float = 0.06
    padding: float = 5.0
    wall_thickness_px: int = 2
    wall_smoothing_passes: int = 0
    min_curvature_radius: float = 3.0
    min_wall_separation: float = 1.5
    occupied_thresh: float = 0.45
    free_thresh: float = 0.196
    negate: int = 0


class TrackSpecError(ValueError):
    """Raised when the track spec is invalid."""


def load_track_spec(path: Path) -> TrackSpec:
    """Load a procedural track spec from YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TrackSpecError("Track spec must be a YAML mapping.")

    stem = data.get("stem")
    if not isinstance(stem, str) or not stem.strip():
        raise TrackSpecError("Track spec requires a non-empty 'stem' string.")

    raw_points = data.get("control_points")
    if not isinstance(raw_points, list) or len(raw_points) < 4:
        raise TrackSpecError("Track spec requires at least 4 control_points.")

    points: list[Point2D] = []
    for index, entry in enumerate(raw_points):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            raise TrackSpecError(f"control_points[{index}] must be [x, y].")
        try:
            x = float(entry[0])
            y = float(entry[1])
        except (TypeError, ValueError) as exc:
            raise TrackSpecError(f"control_points[{index}] must be numeric.") from exc
        points.append(Point2D(x, y))

    return TrackSpec(
        stem=stem.strip(),
        control_points=points,
        track_width=_read_float(data, "track_width", default=2.2, min_value=0.1),
        centerline_spacing=_read_float(data, "centerline_spacing", default=0.2, min_value=0.01),
        resolution=_read_float(data, "resolution", default=0.06, min_value=1e-4),
        padding=_read_float(data, "padding", default=5.0, min_value=0.0),
        wall_thickness_px=_read_int(data, "wall_thickness_px", default=2, min_value=1),
        wall_smoothing_passes=_read_int(data, "wall_smoothing_passes", default=0, min_value=0),
        min_curvature_radius=_read_float(data, "min_curvature_radius", default=3.0, min_value=0.1),
        min_wall_separation=_read_float(data, "min_wall_separation", default=1.5, min_value=0.1),
        occupied_thresh=_read_float(data, "occupied_thresh", default=0.45, min_value=0.0, max_value=1.0),
        free_thresh=_read_float(data, "free_thresh", default=0.196, min_value=0.0, max_value=1.0),
        negate=_read_int(data, "negate", default=0, min_value=0),
    )


def generate_track_bundle(spec: TrackSpec, output_dir: Path) -> Path:
    """Generate a full map bundle for the given track spec."""
    output_dir.mkdir(parents=True, exist_ok=True)

    polyline = _sample_closed_bspline(spec.control_points)
    samples = _resample_closed_polyline(polyline, spec.centerline_spacing)
    if len(samples) < 2:
        raise TrackSpecError("Generated centerline is too short.")

    centerline_points = [Point2D(sample.x, sample.y) for sample in samples]
    _validate_centerline(centerline_points, spec)
    walls = _build_walls(centerline_points, spec.track_width)
    if spec.wall_smoothing_passes > 0:
        walls = [_smooth_closed_polyline(wall, spec.wall_smoothing_passes) for wall in walls]
    _ensure_wall_constraints(centerline_points, walls, spec)
    walls = _scale_walls_to_width(centerline_points, walls, spec.track_width)

    image_bytes, width, height, origin_x, origin_y = _rasterize_walls(
        walls,
        resolution=spec.resolution,
        padding=spec.padding,
        thickness_px=spec.wall_thickness_px,
    )

    stem = spec.stem
    png_path = output_dir / f"{stem}.png"
    pgm_path = output_dir / f"{stem}.pgm"
    yaml_path = output_dir / f"{stem}.yaml"
    centerline_path = output_dir / f"{stem}_centerline.csv"
    walls_path = output_dir / f"{stem}_walls.csv"

    _write_png(image_bytes, width, height, png_path)
    _write_pgm(image_bytes, width, height, pgm_path)
    export_centerline_csv(samples, centerline_path)
    export_walls_csv(walls, walls_path)
    _write_preview_overlay(
        centerline_points,
        walls,
        preview_path=output_dir / f"{stem}_preview.png",
        resolution=spec.resolution,
        padding=spec.padding,
        thickness_px=spec.wall_thickness_px,
    )

    annotations = MapAnnotations(centerline=centerline_points)
    document = MapYamlDocument(
        yaml_path=yaml_path,
        image=png_path.name,
        metadata=_build_metadata(spec, origin_x, origin_y),
        annotations=annotations,
        negate=spec.negate,
    )
    dump_map_yaml(document, destination=yaml_path)
    return yaml_path


def generate_preview_image(spec: TrackSpec) -> QImage:
    """Build a preview overlay image without writing files."""
    polyline = _sample_closed_bspline(spec.control_points)
    samples = _resample_closed_polyline(polyline, spec.centerline_spacing)
    if len(samples) < 2:
        raise TrackSpecError("Generated centerline is too short.")
    centerline_points = [Point2D(sample.x, sample.y) for sample in samples]
    _validate_centerline(centerline_points, spec)
    walls = _build_walls(centerline_points, spec.track_width)
    if spec.wall_smoothing_passes > 0:
        walls = [_smooth_closed_polyline(wall, spec.wall_smoothing_passes) for wall in walls]
    _ensure_wall_constraints(centerline_points, walls, spec)
    walls = _scale_walls_to_width(centerline_points, walls, spec.track_width)

    width, height, origin_x, origin_y = _compute_raster_bounds(
        walls,
        resolution=spec.resolution,
        padding=spec.padding,
    )
    return _render_preview_overlay(
        centerline_points,
        walls,
        width=width,
        height=height,
        origin_x=origin_x,
        origin_y=origin_y,
        resolution=spec.resolution,
        thickness_px=spec.wall_thickness_px,
    )


def _sample_closed_bspline(points: Sequence[Point2D], samples_per_segment: int = 24) -> list[Point2D]:
    if len(points) < 4:
        return list(points)
    result: list[Point2D] = []
    count = len(points)
    step = 1.0 / samples_per_segment
    for i in range(count):
        p0 = points[(i - 1) % count]
        p1 = points[i % count]
        p2 = points[(i + 1) % count]
        p3 = points[(i + 2) % count]
        u = 0.0
        while u < 1.0:
            x, y = _bspline_point(p0, p1, p2, p3, u)
            result.append(Point2D(x, y))
            u += step
    if result:
        result.append(Point2D(result[0].x, result[0].y))
    return result


def _bspline_point(p0: Point2D, p1: Point2D, p2: Point2D, p3: Point2D, u: float) -> tuple[float, float]:
    u2 = u * u
    u3 = u2 * u
    b0 = (1 - u) ** 3 / 6.0
    b1 = (3 * u3 - 6 * u2 + 4) / 6.0
    b2 = (-3 * u3 + 3 * u2 + 3 * u + 1) / 6.0
    b3 = u3 / 6.0
    x = p0.x * b0 + p1.x * b1 + p2.x * b2 + p3.x * b3
    y = p0.y * b0 + p1.y * b1 + p2.y * b2 + p3.y * b3
    return x, y


def _resample_closed_polyline(points: Sequence[Point2D], spacing: float) -> list[CenterlineSample]:
    if len(points) < 2:
        return []
    closed = list(points)
    if closed[0].x != closed[-1].x or closed[0].y != closed[-1].y:
        closed.append(Point2D(closed[0].x, closed[0].y))
    samples = resample_centerline(closed, spacing)
    if len(samples) > 1:
        first = samples[0]
        last = samples[-1]
        if math.hypot(first.x - last.x, first.y - last.y) < spacing * 0.5:
            samples.pop()
    return samples


def _build_walls(centerline: Sequence[Point2D], track_width: float) -> list[list[Point2D]]:
    if len(centerline) < 2:
        return []
    half_width = track_width * 0.5
    normals = _compute_normals(centerline)
    left: list[Point2D] = []
    right: list[Point2D] = []
    for point, normal in zip(centerline, normals):
        nx, ny = normal
        left.append(Point2D(point.x + nx * half_width, point.y + ny * half_width))
        right.append(Point2D(point.x - nx * half_width, point.y - ny * half_width))
    return [left, right]


def _compute_normals(points: Sequence[Point2D]) -> list[tuple[float, float]]:
    normals: list[tuple[float, float]] = []
    count = len(points)
    for index in range(count):
        prev_pt = points[index - 1]
        next_pt = points[(index + 1) % count]
        dx = next_pt.x - prev_pt.x
        dy = next_pt.y - prev_pt.y
        length = math.hypot(dx, dy)
        if length == 0:
            normals.append((0.0, 0.0))
        else:
            normals.append((-dy / length, dx / length))
    return normals


def _rasterize_walls(
    walls: Iterable[Sequence[Point2D]],
    *,
    resolution: float,
    padding: float,
    thickness_px: int,
) -> tuple[bytes, int, int, float, float]:
    width, height, origin_x, origin_y = _compute_raster_bounds(
        walls,
        resolution=resolution,
        padding=padding,
    )

    pixels = bytearray([255] * (width * height))

    for wall in walls:
        if len(wall) < 2:
            continue
        for start, end in zip(wall[:-1], wall[1:]):
            x0, y0 = _world_to_pixel(start, origin_x, origin_y, resolution, height)
            x1, y1 = _world_to_pixel(end, origin_x, origin_y, resolution, height)
            _draw_line(pixels, width, height, x0, y0, x1, y1, thickness_px)

    return bytes(pixels), width, height, origin_x, origin_y


def _world_to_pixel(
    point: Point2D,
    origin_x: float,
    origin_y: float,
    resolution: float,
    height: int,
) -> tuple[int, int]:
    px = int(round((point.x - origin_x) / resolution))
    py = int(round((height - 1) - (point.y - origin_y) / resolution))
    return px, py


def _compute_raster_bounds(
    walls: Iterable[Sequence[Point2D]],
    *,
    resolution: float,
    padding: float,
) -> tuple[int, int, float, float]:
    points = [pt for wall in walls for pt in wall]
    if not points:
        raise TrackSpecError("Walls are empty; cannot rasterize.")
    min_x = min(p.x for p in points) - padding
    max_x = max(p.x for p in points) + padding
    min_y = min(p.y for p in points) - padding
    max_y = max(p.y for p in points) + padding
    width = max(1, math.ceil((max_x - min_x) / resolution))
    height = max(1, math.ceil((max_y - min_y) / resolution))
    return width, height, min_x, min_y


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    thickness_px: int,
) -> None:
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    radius = max(0, thickness_px // 2)

    while True:
        _draw_point(pixels, width, height, x0, y0, radius)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def _draw_point(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    radius: int,
) -> None:
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            px = x + dx
            py = y + dy
            if 0 <= px < width and 0 <= py < height:
                pixels[py * width + px] = 0


def _write_png(pixels: bytes, width: int, height: int, path: Path) -> None:
    image = QImage(pixels, width, height, width, QImage.Format_Grayscale8)
    if image.isNull():
        raise TrackSpecError("Failed to allocate PNG image.")
    if not image.save(str(path), "PNG"):
        raise TrackSpecError(f"Failed to save PNG: {path}")


def _write_preview_overlay(
    centerline: Sequence[Point2D],
    walls: Sequence[Sequence[Point2D]],
    *,
    preview_path: Path,
    resolution: float,
    padding: float,
    thickness_px: int,
) -> None:
    width, height, origin_x, origin_y = _compute_raster_bounds(
        walls,
        resolution=resolution,
        padding=padding,
    )
    image = _render_preview_overlay(
        centerline,
        walls,
        width=width,
        height=height,
        origin_x=origin_x,
        origin_y=origin_y,
        resolution=resolution,
        thickness_px=thickness_px,
    )
    if not image.save(str(preview_path), "PNG"):
        raise TrackSpecError(f"Failed to save preview PNG: {preview_path}")


def _render_preview_overlay(
    centerline: Sequence[Point2D],
    walls: Sequence[Sequence[Point2D]],
    *,
    width: int,
    height: int,
    origin_x: float,
    origin_y: float,
    resolution: float,
    thickness_px: int,
) -> QImage:
    image = QImage(width, height, QImage.Format_RGB888)
    image.fill(QColor(230, 230, 230))
    painter = QPainter(image)
    try:
        wall_pen = QPen(QColor(0, 0, 0), max(1, thickness_px))
        painter.setPen(wall_pen)
        for wall in walls:
            _draw_polyline(painter, wall, origin_x, origin_y, resolution, height)
        center_pen = QPen(QColor(0, 200, 200), max(1, thickness_px))
        painter.setPen(center_pen)
        _draw_polyline(painter, centerline, origin_x, origin_y, resolution, height, close=True)
    finally:
        painter.end()
    return image


def _draw_polyline(
    painter: QPainter,
    points: Sequence[Point2D],
    origin_x: float,
    origin_y: float,
    resolution: float,
    height: int,
    *,
    close: bool = False,
) -> None:
    if len(points) < 2:
        return
    coords = [
        _world_to_pixel(point, origin_x, origin_y, resolution, height)
        for point in points
    ]
    for (x0, y0), (x1, y1) in zip(coords[:-1], coords[1:]):
        painter.drawLine(x0, y0, x1, y1)
    if close:
        x0, y0 = coords[-1]
        x1, y1 = coords[0]
        painter.drawLine(x0, y0, x1, y1)


def _write_pgm(pixels: bytes, width: int, height: int, path: Path) -> None:
    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    path.write_bytes(header + pixels)


def _build_metadata(spec: TrackSpec, origin_x: float, origin_y: float):
    from map_editor.models.map_bundle import MapMetadata

    return MapMetadata(
        resolution=spec.resolution,
        origin_x=origin_x,
        origin_y=origin_y,
        origin_theta=0.0,
        occupied_thresh=spec.occupied_thresh,
        free_thresh=spec.free_thresh,
    )


def _read_float(
    data: dict,
    key: str,
    *,
    default: float,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    raw = data.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise TrackSpecError(f"'{key}' must be a number.") from exc
    if min_value is not None and value < min_value:
        raise TrackSpecError(f"'{key}' must be >= {min_value}.")
    if max_value is not None and value > max_value:
        raise TrackSpecError(f"'{key}' must be <= {max_value}.")
    return value


def _read_int(
    data: dict,
    key: str,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = data.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise TrackSpecError(f"'{key}' must be an integer.") from exc
    if min_value is not None and value < min_value:
        raise TrackSpecError(f"'{key}' must be >= {min_value}.")
    if max_value is not None and value > max_value:
        raise TrackSpecError(f"'{key}' must be <= {max_value}.")
    return value


__all__ = [
    "TrackSpec",
    "TrackSpecError",
    "generate_track_bundle",
    "generate_preview_image",
    "load_track_spec",
]
def _validate_centerline(points: Sequence[Point2D], spec: TrackSpec) -> None:
    if spec.track_width < spec.min_wall_separation:
        raise TrackSpecError(
            f"track_width {spec.track_width:.2f} < min_wall_separation {spec.min_wall_separation:.2f}."
        )
    if len(points) < 3:
        return
    for index in range(len(points)):
        prev_pt = points[index - 1]
        cur_pt = points[index]
        next_pt = points[(index + 1) % len(points)]
        radius = _curvature_radius(prev_pt, cur_pt, next_pt)
        if radius is not None and radius < spec.min_curvature_radius:
            raise TrackSpecError(
                f"Curvature radius {radius:.2f} m below minimum {spec.min_curvature_radius:.2f} m."
            )


def _curvature_radius(a: Point2D, b: Point2D, c: Point2D) -> float | None:
    ab = math.hypot(b.x - a.x, b.y - a.y)
    bc = math.hypot(c.x - b.x, c.y - b.y)
    ca = math.hypot(a.x - c.x, a.y - c.y)
    if ab <= 1e-9 or bc <= 1e-9 or ca <= 1e-9:
        return None
    area = abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) * 0.5
    if area <= 1e-9:
        return None
    return (ab * bc * ca) / (4.0 * area)


def _ensure_wall_constraints(
    centerline: Sequence[Point2D],
    walls: Sequence[Sequence[Point2D]],
    spec: TrackSpec,
) -> None:
    if len(walls) < 2:
        raise TrackSpecError("Expected two walls for track generation.")
    for wall in walls:
        if _polyline_self_intersects(wall):
            raise TrackSpecError("Wall polyline self-intersects; adjust control points or width.")
    _ = centerline


def _polyline_self_intersects(points: Sequence[Point2D]) -> bool:
    if len(points) < 4:
        return False
    closed = list(points)
    if closed[0].x != closed[-1].x or closed[0].y != closed[-1].y:
        closed.append(Point2D(closed[0].x, closed[0].y))
    seg_count = len(closed) - 1
    for i in range(seg_count):
        a1 = closed[i]
        a2 = closed[i + 1]
        for j in range(i + 1, seg_count):
            if j in (i, i - 1, i + 1):
                continue
            if i == 0 and j == seg_count - 1:
                continue
            b1 = closed[j]
            b2 = closed[j + 1]
            if _segments_intersect(a1, a2, b1, b2):
                return True
    return False


def _segments_intersect(a1: Point2D, a2: Point2D, b1: Point2D, b2: Point2D) -> bool:
    def orientation(p: Point2D, q: Point2D, r: Point2D) -> int:
        val = (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)
        if abs(val) < 1e-9:
            return 0
        return 1 if val > 0 else 2

    def on_segment(p: Point2D, q: Point2D, r: Point2D) -> bool:
        return min(p.x, r.x) <= q.x <= max(p.x, r.x) and min(p.y, r.y) <= q.y <= max(p.y, r.y)

    o1 = orientation(a1, a2, b1)
    o2 = orientation(a1, a2, b2)
    o3 = orientation(b1, b2, a1)
    o4 = orientation(b1, b2, a2)

    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and on_segment(a1, b1, a2):
        return True
    if o2 == 0 and on_segment(a1, b2, a2):
        return True
    if o3 == 0 and on_segment(b1, a1, b2):
        return True
    if o4 == 0 and on_segment(b1, a2, b2):
        return True
    return False


def _smooth_closed_polyline(points: Sequence[Point2D], passes: int) -> list[Point2D]:
    if passes <= 0 or len(points) < 3:
        return list(points)
    smoothed = list(points)
    count = len(smoothed)
    for _ in range(passes):
        new_points: list[Point2D] = []
        for i in range(count):
            prev_pt = smoothed[i - 1]
            cur_pt = smoothed[i]
            next_pt = smoothed[(i + 1) % count]
            new_points.append(
                Point2D(
                    (prev_pt.x + cur_pt.x + next_pt.x) / 3.0,
                    (prev_pt.y + cur_pt.y + next_pt.y) / 3.0,
                )
            )
        smoothed = new_points
    return smoothed


def _scale_walls_to_width(
    centerline: Sequence[Point2D],
    walls: Sequence[Sequence[Point2D]],
    target_width: float,
) -> list[list[Point2D]]:
    if len(walls) < 2:
        return [list(wall) for wall in walls]
    half_width = target_width * 0.5
    left, right = walls[0], walls[1]
    if len(left) != len(centerline) or len(right) != len(centerline):
        return [list(left), list(right)]
    scaled_left: list[Point2D] = []
    scaled_right: list[Point2D] = []
    for idx, point in enumerate(centerline):
        left_vec = Point2D(left[idx].x - point.x, left[idx].y - point.y)
        right_vec = Point2D(right[idx].x - point.x, right[idx].y - point.y)
        scaled_left.append(_scale_vector(point, left_vec, half_width))
        scaled_right.append(_scale_vector(point, right_vec, half_width))
    return [scaled_left, scaled_right]


def _scale_vector(origin: Point2D, vector: Point2D, target_length: float) -> Point2D:
    length = math.hypot(vector.x, vector.y)
    if length <= 1e-9:
        return Point2D(origin.x, origin.y)
    scale = target_length / length
    return Point2D(origin.x + vector.x * scale, origin.y + vector.y * scale)
