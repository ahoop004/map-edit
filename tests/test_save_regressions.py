"""Saving must preserve map data and leave the original intact on failure."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from map_editor.models.annotations import MapAnnotations
from map_editor.models.map_bundle import MapBundle, MapMetadata
from map_editor.services.map_loader import MapBundleLoader
from map_editor.services.yaml_serializer import MapYamlError, load_map_yaml


@pytest.fixture
def saved_bundle(tmp_path):
    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "images" / "track.png"
    image_path.parent.mkdir()
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(image_path))
    bundle = MapBundle(image_path, tmp_path / "track.yaml", MapMetadata.default(), MapAnnotations(),
                       negate=1, extra_fields={"mode": "trinary", "custom": {"label": "test"}})
    MapBundleLoader().save_bundle(bundle)
    yield bundle
    assert app is not None


def test_save_preserves_image_path_negate_and_extra_fields(saved_bundle, tmp_path):
    loader = MapBundleLoader(search_image=False)
    loaded = loader.load_from_yaml(saved_bundle.yaml_path).bundle
    updated = loaded.with_metadata(replace(loaded.metadata, resolution=0.2))
    updated = updated.with_annotations(MapAnnotations()).with_yaml_path(tmp_path / "elsewhere" / "map.yaml")
    loader.save_bundle(updated)
    reloaded = loader.load_from_yaml(updated.yaml_path).bundle
    assert reloaded.image_path == saved_bundle.image_path
    assert reloaded.negate == 1
    assert reloaded.extra_fields == saved_bundle.extra_fields
    assert reloaded.metadata.resolution == 0.2


def test_failed_save_keeps_original_and_cleans_temporary_file(saved_bundle, monkeypatch):
    path = saved_bundle.yaml_path
    original = path.read_bytes()
    def fail_replace(*args):
        raise OSError("simulated write failure")
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated write failure"):
        MapBundleLoader().save_bundle(saved_bundle.with_metadata(replace(saved_bundle.metadata, resolution=0.1)))
    assert path.read_bytes() == original
    assert path.with_suffix(".yaml.bak").read_bytes() == original
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("updates", [
    {"resolution": 0}, {"resolution": -1}, {"resolution": float("nan")},
    {"origin": ["invalid", 0, 0]}, {"origin": [0, 0, float("inf")]}, {"negate": "bad"},
])
def test_invalid_metadata_raises_user_facing_error(tmp_path, updates):
    data = {"image": "map.png", "resolution": 0.05, "origin": [0, 0, 0]}
    data.update(updates)
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(MapYamlError):
        load_map_yaml(path)


def test_malformed_yaml_raises_user_facing_error(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("image: [broken")
    with pytest.raises(MapYamlError):
        load_map_yaml(path)
