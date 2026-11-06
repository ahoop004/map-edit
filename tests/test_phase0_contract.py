"""Regression coverage for the Phase 0 bundle and metadata contract."""
from dataclasses import replace
import math
from pathlib import Path

import pytest
import yaml
from PySide6.QtGui import QImage

from map_editor.models.annotations import LineSegment, MapAnnotations, Point2D, StartFinishLine
from map_editor.services.geometry_metadata import (
    build_geometry_metadata, load_geometry_metadata, validate_geometry_metadata,
)
from map_editor.services.paper_tracks import build_paper_track_spec
from map_editor.services.procedural_track import (
    TrackSpecError, _ensure_wall_constraints, _polyline_self_intersects,
    _rasterize_walls, _validate_centerline, _world_to_cell,
    build_finish_line, generate_track_bundle, load_track_spec, prepare_track_geometry,
)
from map_editor.services.yaml_serializer import MapYamlDocument, MapYamlError, dump_map_yaml, load_map_yaml
from map_editor.models.map_bundle import MapMetadata


def segment(kind="hairpin", start=15., end=2., length=4., wraps=True, direction="left", id="turn_1"):
    return dict(id=id, type=kind, direction=direction, s_start_m=start, s_end_m=end,
                length_m=length, wraps_seam=wraps, requested={}, measured={}, difficulty={})


@pytest.fixture(scope="module")
def geometry():
    return prepare_track_geometry(build_paper_track_spec())


@pytest.mark.parametrize("mode", ["walls", "corridor"])
@pytest.mark.parametrize("negate", [0, 1])
def test_modes_replay_every_artifact_and_preserve_images(tmp_path, mode, negate):
    spec = replace(build_paper_track_spec(), occupancy_mode=mode, negate=negate)
    path = generate_track_bundle(spec, tmp_path / "first")
    recipe = path.with_name(f"{spec.stem}_generation.yaml")
    assert load_track_spec(recipe) == spec
    generate_track_bundle(load_track_spec(recipe), tmp_path / "second")
    for artifact in path.parent.iterdir():
        assert artifact.read_bytes() == (tmp_path / "second" / artifact.name).read_bytes()
    png, pgm = (QImage(str(path.with_suffix(ext))) for ext in [".png", ".pgm"])
    assert png == pgm
    data = load_geometry_metadata(path.with_name(f"{spec.stem}_metadata.json"))
    assert data["occupancy_mode"] == mode
    assert data["generation_mode"] == "legacy"
    assert data["random_seed"] is None
    assert data["maneuvers"] == []
    assert all((path.parent / asset).is_file() for asset in data["artifacts"].values())


@pytest.mark.parametrize("reverse", [False, True])
def test_finish_spans_walls_and_follows_final_centerline(reverse):
    spec = build_paper_track_spec()
    if reverse:
        spec = replace(spec, control_points=list(reversed(spec.control_points)),
                       wall_smoothing_passes=2, min_wall_separation=.95)
    geom = prepare_track_geometry(spec)
    line = build_finish_line(geom)
    a, b = line.segment.start, line.segment.end
    p = geom.centerline[0]
    d = line.direction
    assert math.hypot(b.x - a.x, b.y - a.y) == pytest.approx(geom.profile[0]["width_m"])
    assert (b.x - a.x) * d.x + (b.y - a.y) * d.y == pytest.approx(0, abs=1e-9)
    assert d.x * (geom.centerline[1].x - p.x) + d.y * (geom.centerline[1].y - p.y) > 0
    assert a.x == pytest.approx(p.x - d.y * geom.profile[0]["left_width_m"])
    assert b.y == pytest.approx(p.y - d.x * geom.profile[0]["right_width_m"])


@pytest.mark.parametrize("alias", ["legacy", "nested", "top"])
def test_finish_alias_roundtrip_preserves_options_and_direction(tmp_path, alias):
    raw = dict(start=[0., -1.], end=[0., 1.], direction=[1., 0.], version=1,
               hysteresis=0.2, trigger_speed=0.1, padding=0.0)
    data = dict(image="map.png", resolution=0.1, origin=[0, 0, 0], custom={"unchanged": True})
    if alias == "top":
        data["finish_line"] = raw
    else:
        data["annotations"] = {"start_finish" if alias == "legacy" else "finish_line": raw}
    path = tmp_path / "map.yaml"
    path.write_text(yaml.safe_dump(data))
    doc = load_map_yaml(path)
    exported = yaml.safe_load(dump_map_yaml(doc, path))
    assert exported["annotations"]["finish_line"] == raw
    assert exported["annotations"]["start_finish"] == raw
    assert exported["custom"] == data["custom"]
    assert load_map_yaml(path).annotations == doc.annotations
    # Removing the line in the editor cannot leave a stale top-level alias.
    doc.annotations.start_finish_line = None
    assert "finish_line" not in yaml.safe_load(dump_map_yaml(doc))


def test_legacy_line_infers_normal_from_centerline_without_mutating_model(tmp_path):
    line = StartFinishLine(LineSegment(Point2D(0, -1), Point2D(0, 1)))
    points = [Point2D(-2, 0), Point2D(0, 0), Point2D(2, 0), Point2D(2, 3)]
    doc = MapYamlDocument(tmp_path / "map.yaml", "map.png", MapMetadata.default(),
                          MapAnnotations(start_finish_line=line, centerline=points))
    raw = yaml.safe_load(dump_map_yaml(doc, doc.yaml_path))
    assert raw["annotations"]["finish_line"]["direction"] == [1, 0]
    assert load_map_yaml(doc.yaml_path).annotations.start_finish_line == line
    assert line.direction is None


@pytest.mark.parametrize("change", [dict(direction=[0, 0]), dict(direction=[0, 1]),
                                     dict(start=[0, 1]), dict(end=[float("nan"), 1])])
def test_bad_finish_configuration_is_rejected(tmp_path, change):
    raw = dict(start=[0, -1], end=[0, 1], direction=[1, 0])
    raw.update(change)
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(dict(image="map.png", resolution=0.1, origin=[0, 0, 0],
                                       annotations={"finish_line": raw})))
    with pytest.raises(MapYamlError):
        load_map_yaml(path)


def test_corridor_cells_are_free_only_between_boundaries():
    walls = [[Point2D(*p) for p in shape] for shape in [
        [(0, 0), (8, 0), (8, 8), (0, 8)], [(2, 2), (6, 2), (6, 6), (2, 6)]]]
    for mode in ["walls", "corridor"]:
        pixels, width, height, ox, oy = _rasterize_walls(
            walls, resolution=0.1, padding=1, thickness_px=1, occupancy_mode=mode)
        for point, expected in [(Point2D(1, 1), 255), (Point2D(0, 4), 0),
                                (Point2D(4, 4), 0 if mode == "corridor" else 255),
                                (Point2D(-.5, 4), 0 if mode == "corridor" else 255)]:
            x, y = _world_to_cell(point, ox, oy, .1, height)
            assert pixels[y * width + x] == expected
    # Ownership around cell edges must match the simulator's floor convention.
    assert _world_to_cell(Point2D(-.001, .001), 0, 0, .1, 10) == (-1, 9)
    assert _world_to_cell(Point2D(.101, .101), 0, 0, .1, 10) == (1, 8)


def test_coarse_corridor_rejected_before_any_files_are_written(tmp_path):
    spec = replace(build_paper_track_spec(), occupancy_mode="corridor", resolution=1., wall_thickness_px=3)
    with pytest.raises(TrackSpecError, match="Rasterization blocks"):
        generate_track_bundle(spec, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("change", [dict(occupancy_mode="unknown"), dict(free_thresh=.7, occupied_thresh=.6),
                                    dict(free_thresh=0), dict(occupied_thresh=1)])
def test_invalid_occupancy_options_are_rejected(tmp_path, change):
    with pytest.raises(TrackSpecError):
        generate_track_bundle(replace(build_paper_track_spec(), **change), tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_metadata_supports_specialists_composites_and_seam_intervals(geometry):
    spec = build_paper_track_spec()
    specialist = replace(spec, track_metadata=dict(dataset_id="phase0", generation_mode="specialist",
                          split="train", random_seed=42, maneuvers=[segment()],
                          difficulty={"label": "hard", "indicators": {"curvature_variation_inv_m": 1.2}}))
    metadata = build_geometry_metadata(specialist, geometry.metrics)
    assert metadata["maneuvers"][0]["length_m"] == 4
    assert metadata["measured"]["length_m"] == pytest.approx(17)
    metadata["generation_mode"] = "composite"
    metadata["maneuvers"].append(segment("straight", 2, 15, 13, False, "none", "straight_1"))
    validate_geometry_metadata(metadata)
    metadata["generation_mode"] = "specialist"
    metadata["maneuvers"] = [segment(start=0, end=0, length=17)]
    validate_geometry_metadata(metadata)


@pytest.mark.parametrize("change", [
    {"schema_version": "2.0.0"}, {"random_seed": -1}, {"split": "eval"},
    {"maneuvers": [segment(start=17)]}, {"maneuvers": [segment(length=3)]},
    {"maneuvers": [segment(wraps=False)]}, {"maneuvers": [segment(direction="none")]},
    {"maneuvers": [segment(kind="u_turn")]}, {"maneuvers": [segment(), segment(id="other")]},
    {"generation_mode": "specialist"}, {"generation_mode": "composite"},
    {"difficulty": {"score": float("nan")}},
])
def test_invalid_metadata_is_rejected(geometry, change):
    metadata = build_geometry_metadata(build_paper_track_spec(), geometry.metrics)
    metadata.update(change)
    with pytest.raises(ValueError):
        validate_geometry_metadata(metadata)


def test_metadata_cannot_escape_bundle_or_override_measurements(geometry, tmp_path):
    spec = replace(build_paper_track_spec(), track_metadata={"measured": {"length_m": 2}})
    with pytest.raises(ValueError, match="Unknown"):
        build_geometry_metadata(spec, geometry.metrics)
    metadata = build_geometry_metadata(build_paper_track_spec(), geometry.metrics)
    metadata["artifacts"]["map"] = "../escape.yaml"
    with pytest.raises(ValueError, match="relative"):
        validate_geometry_metadata(metadata)
    spec = replace(spec, track_metadata={"generation_mode": "specialist"})
    with pytest.raises(TrackSpecError, match="metadata"):
        generate_track_bundle(spec, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_legacy_recipes_default_without_contract_fields(tmp_path):
    spec = build_paper_track_spec()
    generate_track_bundle(spec, tmp_path / "first")
    path = tmp_path / "first" / f"{spec.stem}_generation.yaml"
    raw = yaml.safe_load(path.read_text())
    for field in ["occupancy_mode", "track_metadata"]:
        raw.pop(field)
    path.write_text(yaml.safe_dump(raw))
    assert load_track_spec(path) == spec
    raw["generator"] = "future.v2"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(TrackSpecError, match="Unsupported"):
        load_track_spec(path)


def test_invalid_geometry_checks_include_seam_and_degenerate_edges():
    bowtie = [Point2D(*p) for p in [(0, 0), (2, 2), (0, 2), (2, 0)]]
    assert _polyline_self_intersects(bowtie)
    # Last segment crosses a nonadjacent edge.
    seam_crossing = [Point2D(*p) for p in [(0, 0), (2, 0), (2, 2), (0, 2), (3, 1)]]
    assert _polyline_self_intersects(seam_crossing)
    spec = build_paper_track_spec()
    with pytest.raises(TrackSpecError, match="self-intersects"):
        _ensure_wall_constraints([bowtie, [Point2D(p.x + 10, p.y) for p in bowtie]], spec)
    with pytest.raises(TrackSpecError, match="zero-length"):
        _validate_centerline([Point2D(0, 0), Point2D(0, 0), Point2D(2, 0)], spec)
    with pytest.raises(TrackSpecError, match="track_width"):
        prepare_track_geometry(replace(spec, min_wall_separation=2))


def test_gui_exposes_occupancy_without_changing_default(qapp):
    from map_editor.ui.track_generator import TrackGeneratorDialog
    dialog = TrackGeneratorDialog()
    dialog._source_combo.setCurrentText("Paper L (approximation)")
    assert dialog._build_spec().occupancy_mode == "walls"
    dialog._occupancy_combo.setCurrentText("corridor")
    assert dialog._build_spec().occupancy_mode == "corridor"
    dialog.close()


@pytest.mark.parametrize("path", sorted((Path(__file__).resolve().parents[1] / "sample_maps").glob("*_map/*.yaml"))
                         + [Path(__file__).resolve().parents[1] / "sample_maps" / "line2" / "line2.yaml"])
def test_existing_map_yaml_formats_still_roundtrip(path, tmp_path):
    document = load_map_yaml(path)
    target = tmp_path / path.name
    dump_map_yaml(document, target)
    loaded = load_map_yaml(target)
    assert loaded.metadata == document.metadata
    assert loaded.annotations == document.annotations
    assert loaded.extra_fields == document.extra_fields
    assert loaded.negate == document.negate
