"""Integration test for map bundle save/load round trip."""

from __future__ import annotations

from pathlib import Path

import os
from dataclasses import replace

import pytest
import yaml

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor

from map_editor.models.annotations import LineSegment, MapAnnotations, Point2D, Pose2D, SpawnPoint, StartFinishLine
from map_editor.models.map_bundle import MapBundle, MapMetadata
from map_editor.services.map_loader import MapBundleLoader

# Ensure Qt can run headless during tests
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
app = QApplication.instance() or QApplication([])

def _write_png(path: Path) -> None:
    image = QImage(1, 1, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    image.save(str(path), "PNG")


def test_save_then_load_preserves_annotations(tmp_path: Path):
    image_path = tmp_path / "track.png"
    _write_png(image_path)

    metadata = MapMetadata(
        resolution=0.05,
        origin_x=1.0,
        origin_y=2.0,
        origin_theta=0.0,
        occupied_thresh=0.65,
        free_thresh=0.196,
    )
    annotations = MapAnnotations(
        start_finish_line=StartFinishLine(
            segment=LineSegment(start=Point2D(2.0, 3.0), end=Point2D(4.0, 5.0))
        ),
        spawn_points=[
            SpawnPoint(name="spawn_1", pose=Pose2D(3.0, 4.0, 0.1)),
        ],
        centerline=[Point2D(0.0, 0.0), Point2D(1.0, 0.0), Point2D(2.0, 1.0)],
    )
    bundle = MapBundle(image_path=image_path, yaml_path=None, metadata=metadata, annotations=annotations)

    yaml_path = tmp_path / "track.yaml"
    loader = MapBundleLoader(search_image=False)
    loader.save_bundle(bundle, destination=yaml_path, create_backup=False)

    result = loader.load_from_yaml(yaml_path)
    loaded = result.bundle

    assert loaded.metadata == metadata
    assert loaded.annotations.start_finish_line == annotations.start_finish_line
    assert loaded.annotations.spawn_points == annotations.spawn_points
    assert loaded.annotations.centerline == annotations.centerline


def test_edit_and_save_preserves_yaml_settings(tmp_path: Path):
    image_path = tmp_path / "track.png"
    _write_png(image_path)
    yaml_path = tmp_path / "track.yaml"
    yaml_path.write_text(yaml.safe_dump({
        "image": "track.png", "resolution": 0.05, "origin": [0, 0, 0],
        "negate": 1, "mode": "scale", "custom": {"labels": ["a", "b"]},
    }))
    loader = MapBundleLoader(search_image=False)
    bundle = loader.load_from_yaml(yaml_path).bundle
    bundle = bundle.with_metadata(replace(bundle.metadata, resolution=0.1))
    bundle = bundle.with_annotations(MapAnnotations(centerline=[Point2D(1, 2), Point2D(3, 4)]))
    bundle = bundle.with_yaml_path(tmp_path / "edited.yaml")
    loader.save_bundle(bundle)
    loaded = loader.load_from_yaml(bundle.yaml_path).bundle
    assert loaded.negate == 1
    assert loaded.extra_fields == {"mode": "scale", "custom": {"labels": ["a", "b"]}}
    assert loaded.metadata.resolution == 0.1
    assert loaded.annotations == bundle.annotations


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("relocate", [False, True])
def test_save_keeps_image_reference_resolvable(tmp_path: Path, absolute: bool, relocate: bool):
    image_path = tmp_path / "images" / "track.png"
    image_path.parent.mkdir()
    _write_png(image_path)
    yaml_path = tmp_path / "track.yaml"
    yaml_path.write_text(yaml.safe_dump({
        "image": str(image_path) if absolute else "images/track.png",
        "resolution": 0.05, "origin": [0, 0, 0],
    }))
    loader = MapBundleLoader(search_image=False)
    bundle = loader.load_from_yaml(yaml_path).bundle
    target = tmp_path / "elsewhere" / "saved.yaml" if relocate else yaml_path
    loader.save_bundle(bundle, destination=target)
    assert loader.load_from_yaml(target).bundle.image_path == image_path
