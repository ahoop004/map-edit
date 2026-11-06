"""Regression coverage for generated wall closure and occupancy transforms."""

import math
from dataclasses import replace

import pytest
from PySide6.QtGui import QImage

from map_editor.models.annotations import Point2D
from map_editor.models.map_bundle import MapMetadata
from map_editor.services.procedural_track import (
    TrackSpec, build_oval_control_points, generate_track_bundle, _build_walls, _world_to_pixel,
)
from map_editor.services.wall_extraction import extract_walls
from map_editor.services.yaml_serializer import load_map_yaml


def test_generated_walls_close_in_rasters_and_preview(tmp_path):
    spec = TrackSpec(stem="oval", control_points=build_oval_control_points(40, 30),
                     centerline_spacing=1, wall_thickness_px=1)
    path = generate_track_bundle(spec, tmp_path)
    document = load_map_yaml(path)
    walls = _build_walls(document.annotations.centerline, spec.track_width)
    for filename in ["oval.png", "oval.pgm", "oval_preview.png"]:
        image = QImage(str(tmp_path / filename))
        assert not image.isNull()
        for wall in walls:
            midpoint = Point2D((wall[-1].x + wall[0].x) / 2, (wall[-1].y + wall[0].y) / 2)
            x, y = _world_to_pixel(midpoint, document.metadata.origin_x,
                                   document.metadata.origin_y, spec.resolution, image.height())
            # Rounding can put the geometric midpoint next to the one-pixel line.
            assert any(image.pixelColor(x + dx, y + dy).value() == 0
                       for dx in [-1, 0, 1] for dy in [-1, 0, 1])


def test_wall_extraction_applies_rotation_and_negate(tmp_path):
    image = QImage(20, 20, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    for y in range(5, 10):
        for x in range(5, 10):
            image.setPixel(x, y, 0xFF000000)
    path = tmp_path / "wall.png"
    assert image.save(str(path))
    metadata = replace(MapMetadata.default(), resolution=0.5)
    original = extract_walls(path, metadata).walls
    assert len(original) == 1
    rotated = extract_walls(path, replace(metadata, origin_x=3, origin_y=-2, origin_theta=math.pi / 2)).walls
    assert len(rotated) == 1
    for point, transformed in zip(original[0], rotated[0]):
        assert (transformed.x, transformed.y) == pytest.approx((3 - point.y, -2 + point.x))
    image.invertPixels()
    assert image.save(str(path))
    assert extract_walls(path, metadata, negate=1).walls == original
