"""Geometry, bundle compatibility and reproducibility checks for paper tracks."""

import csv
from dataclasses import replace
import math

import pytest
import yaml
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from map_editor.models.annotations import Point2D
from map_editor.services import paper_tracks
from map_editor.services.map_loader import MapBundleLoader
from map_editor.services.paper_tracks import build_paper_track_spec, generate_paper_collection, vary_paper_track
from map_editor.services.procedural_track import (
    TrackSpecError, _ensure_wall_constraints, _rasterize_walls, _world_to_pixel,
    generate_track_bundle, load_track_spec, prepare_track_geometry,
)
from map_editor.services.track_profile import build_track_profile
from map_editor.ui.track_generator import TrackGeneratorDialog


def test_reference_has_requested_dimensions_and_signed_turns():
    geometry = prepare_track_geometry(build_paper_track_spec())
    assert geometry.metrics["length_m"] == pytest.approx(17, abs=1e-8)
    assert geometry.metrics["minimum_width_m"] == pytest.approx(1)
    assert geometry.metrics["maximum_width_m"] == pytest.approx(1)
    assert geometry.metrics["minimum_radius_m"] >= 0.65
    assert any(row["curvature_inv_m"] < 0 for row in geometry.profile)
    assert any(row["curvature_inv_m"] > 0 for row in geometry.profile)
    assert geometry.profile[0]["s_m"] == 0
    assert all(a["s_m"] < b["s_m"] for a, b in zip(geometry.profile, geometry.profile[1:]))
    assert geometry.profile[-1]["s_m"] < 17


def test_profile_circle_curvature_and_seam():
    points = [Point2D(2 * math.cos(i * math.tau / 120), 2 * math.sin(i * math.tau / 120))
              for i in range(120)]
    walls = [[Point2D(p.x * factor, p.y * factor) for p in points] for factor in (0.75, 1.25)]
    for orientation, expected in [(points, 0.5), (list(reversed(points)), -0.5)]:
        profile = build_track_profile(orientation, walls)
        assert all(row["curvature_inv_m"] == pytest.approx(expected) for row in profile)
        assert all(row["width_m"] == pytest.approx(1) for row in profile)


def test_bundle_replays_and_loads_without_changing_csv_schemas(tmp_path):
    spec = build_paper_track_spec()
    first, replay = tmp_path / "first", tmp_path / "replay"
    path = generate_track_bundle(spec, first)
    recipe_path = first / f"{spec.stem}_generation.yaml"
    loaded = load_track_spec(recipe_path)
    assert loaded == spec
    generate_track_bundle(loaded, replay)
    for artifact in first.iterdir():
        assert artifact.read_bytes() == (replay / artifact.name).read_bytes()
    for suffix, header in [("centerline", ["x", "y", "theta", "velocity"]),
                           ("walls", ["wall_id", "vertex_id", "x", "y"])]:
        with (first / f"{spec.stem}_{suffix}.csv").open() as handle:
            assert next(csv.reader(handle)) == header
    bundle = MapBundleLoader().load_from_yaml(path).bundle
    assert len(bundle.annotations.centerline) == 340
    png = QImage(str(first / f"{spec.stem}.png"))
    pgm = QImage(str(first / f"{spec.stem}.pgm"))
    assert not png.isNull()
    assert png == pgm


def test_impossible_radius_reports_metrics_without_resizing_or_writing(tmp_path):
    spec = replace(build_paper_track_spec(), min_curvature_radius=3)
    output = tmp_path / "invalid"
    with pytest.raises(TrackSpecError) as error:
        generate_track_bundle(spec, output)
    assert error.value.metrics["length_m"] == pytest.approx(17)
    assert error.value.metrics["minimum_radius_m"] < 3
    assert not output.exists()


def test_raster_closes_last_wall_segment():
    wall = [Point2D(0, 0), Point2D(2, 0), Point2D(2, 2), Point2D(0, 2)]
    pixels, width, height, ox, oy = _rasterize_walls([wall], resolution=0.1, padding=0.5, thickness_px=1)
    x, y = _world_to_pixel(Point2D(0, 1), ox, oy, 0.1, height)
    assert pixels[y * width + x] == 0
    x, y = _world_to_pixel(Point2D(1, 1), ox, oy, 0.1, height)
    assert pixels[y * width + x] == 255


def test_crossing_boundaries_are_rejected():
    walls = [[Point2D(*p) for p in shape] for shape in [
        [(0, 0), (2, 0), (2, 2), (0, 2)],
        [(1, -1), (3, -1), (3, 1), (1, 1)],
    ]]
    with pytest.raises(TrackSpecError, match="boundaries intersect"):
        _ensure_wall_constraints(walls, build_paper_track_spec())


def test_collection_is_reproducible_and_wont_overwrite(tmp_path):
    reference = build_paper_track_spec()
    first = generate_paper_collection(reference, tmp_path / "a", count=2, seed=123)
    second = generate_paper_collection(reference, tmp_path / "b", count=2, seed=123)
    assert first == second
    assert first["complete"]
    for entry in first["accepted"]:
        assert entry["achieved"]["length_m"] == pytest.approx(17)
        path = entry["map"]
        assert (tmp_path / "a" / path).read_bytes() == (tmp_path / "b" / path).read_bytes()
    a = vary_paper_track(reference, stem="variant", seed=123, variation=0.2)
    b = vary_paper_track(reference, stem="variant", seed=124, variation=0.2)
    assert a.control_points != b.control_points
    with pytest.raises(TrackSpecError, match="empty output directory"):
        generate_paper_collection(reference, tmp_path / "a", count=1)


def test_collection_records_rejected_geometry_and_stops_at_budget(tmp_path, monkeypatch):
    original = paper_tracks.vary_paper_track
    monkeypatch.setattr(paper_tracks, "vary_paper_track",
                        lambda *a, **kw: replace(original(*a, **kw), min_curvature_radius=10))
    report = generate_paper_collection(build_paper_track_spec(), tmp_path / "limited",
                                       count=1, max_attempts=2)
    assert not report["complete"]
    assert not report["accepted"]
    assert len(report["rejected"]) == 2
    assert all(entry["achieved"]["length_m"] == pytest.approx(17) for entry in report["rejected"])
    assert all("radius" in entry["reason"] for entry in report["rejected"])
    assert all(entry["recipe"]["target_length"] == 17 for entry in report["rejected"])
    assert yaml.safe_load((tmp_path / "limited" / "collection.yaml").read_text()) == report
    assert not (tmp_path / "limited" / "paper_l_001").exists()


@pytest.mark.parametrize("changes", [{"resolution": float("nan")}, {"target_length": -1},
                                    {"centerline_spacing": 0}, {"stem": "../escape"}])
def test_invalid_specs_fail_before_export(tmp_path, changes):
    with pytest.raises(TrackSpecError):
        generate_track_bundle(replace(build_paper_track_spec(), **changes), tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_dialog_paper_preset_and_recipe_preserve_dimensions(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = TrackGeneratorDialog()
    dialog._source_combo.setCurrentText("Paper L (approximation)")
    spec = dialog._build_spec()
    assert spec.track_width == 1
    assert spec.target_length == 17
    assert dialog.collection_options() is None
    dialog._variant_count_spin.setValue(3)
    assert dialog.collection_options() == dict(count=3, seed=42, variation=0.2)
    assert not dialog._oval_length_spin.isEnabled()
    generate_track_bundle(spec, tmp_path)
    dialog._source_combo.setCurrentText("YAML")
    dialog._spec_path_edit.setText(str(tmp_path / f"{spec.stem}_generation.yaml"))
    assert dialog._build_spec() == spec
    assert dialog.collection_options() is None
    dialog.close()
    app.processEvents()
