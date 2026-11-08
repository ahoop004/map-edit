"""Versioned, simulator-independent geometry and maneuver sidecars."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

GENERATOR_VERSION = "map_editor.closed_bspline.v1"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "track-metadata-v1.schema.json"


@lru_cache(maxsize=2)
def _validator(version="1.0.0"):
    if version not in {"1.0.0", "2.0.0"}:
        raise ValueError("Unsupported geometry metadata schema version")
    path = SCHEMA_PATH if version == "1.0.0" else SCHEMA_PATH.with_name("track-metadata-v2.schema.json")
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_geometry_metadata(data: dict) -> None:
    """Validate structure, finite JSON, periodic intervals and artifact paths."""
    try:
        json.dumps(data, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("Metadata must contain finite JSON values") from exc
    error = next(iter(_validator(data.get("schema_version")).iter_errors(data)), None)
    if error:
        location = ".".join(str(key) for key in error.absolute_path)
        raise ValueError(f"{location}: {error.message}")
    length = data["measured"]["length_m"]
    measured = data["measured"]
    if not measured["minimum_width_m"] <= measured["mean_width_m"] <= measured["maximum_width_m"]:
        raise ValueError("Measured widths must satisfy minimum <= mean <= maximum")
    intervals = []
    ids = set()
    for segment in data["maneuvers"]:
        if segment["id"] in ids:
            raise ValueError("Maneuver ids must be unique")
        ids.add(segment["id"])
        start, end = segment["s_start_m"], segment["s_end_m"]
        wraps = segment["wraps_seam"]
        if not (0 <= start < length and 0 <= end < length):
            raise ValueError("Maneuver positions must lie in [0, lap length)")
        if wraps != (end <= start):
            raise ValueError("wraps_seam must agree with the periodic interval")
        expected = end - start + (length if wraps else 0)
        if not math.isclose(segment["length_m"], expected, rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError("Maneuver length_m disagrees with periodic endpoints")
        kind, direction = segment["type"], segment["direction"]
        allowed = {"straight": {"none"}, "hairpin": {"left", "right"},
                   "sweeper": {"left", "right"}, "chicane": {"left_right", "right_left"},
                   "s_curve": {"left_right", "right_left"},
                   "transition": {"none", "left", "right", "left_right", "right_left"}}
        if data["schema_version"] == "2.0.0":
            allowed.update(corner={"left", "right"}, kink={"left", "right"}, compound_corner={"left", "right"})
        if direction not in allowed[kind]:
            raise ValueError(f"Invalid direction for maneuver {kind}")
        intervals.extend([(start, length), (0, end)] if wraps else [(start, end)])
    intervals.sort()
    if any(b[0] < a[1] - 1e-8 for a, b in zip(intervals, intervals[1:])):
        raise ValueError("Primary maneuver intervals must not overlap")
    if data["generation_mode"] == "specialist" and not data["maneuvers"]:
        raise ValueError("Specialist metadata requires a maneuver annotation")
    if data["generation_mode"] == "composite" and len({m["type"] for m in data["maneuvers"]}) < 2:
        raise ValueError("Composite metadata requires multiple maneuver families")
    for value in data["artifacts"].values():
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("Artifact paths must be relative POSIX paths within the bundle")


def build_geometry_metadata(spec, metrics: dict) -> dict:
    """Describe existing geometry without inventing maneuver labels or seeds."""
    supplied = deepcopy(spec.track_metadata)
    allowed = {"dataset_id", "track_id", "generation_mode", "geometry_family", "random_seed",
               "requested", "difficulty", "split", "provenance", "maneuvers"}
    if not isinstance(supplied, dict) or set(supplied) - allowed:
        raise ValueError("Unknown track_metadata fields")
    stem = spec.stem
    data = {
        "schema_version": "1.0.0",
        "dataset_id": None,
        "track_id": stem,
        "generation_mode": "legacy",
        "geometry_family": spec.provenance.get("family", "closed_bspline"),
        "random_seed": spec.provenance.get("seed"),
        "generator_version": GENERATOR_VERSION,
        "geometry": {"coordinate_frame": "map", "closed": True,
                     "arc_length_origin": "centerline_first_vertex", "positive_curvature": "left"},
        "requested": {"track_width_m": spec.track_width, "length_m": spec.target_length,
                      "minimum_radius_m": spec.min_curvature_radius,
                      "minimum_wall_separation_m": spec.min_wall_separation,
                      "centerline_spacing_m": spec.centerline_spacing,
                      "resolution_m_per_pixel": spec.resolution},
        "measured": deepcopy(metrics),
        "difficulty": {},
        "split": "unspecified",
        "provenance": deepcopy(spec.provenance),
        "occupancy_mode": spec.occupancy_mode,
        "maneuvers": [],
        "artifacts": {"map": f"{stem}.yaml", "image": f"{stem}.png", "pgm": f"{stem}.pgm",
                      "centerline": f"{stem}_centerline.csv", "walls": f"{stem}_walls.csv",
                      "track_profile": f"{stem}_track_profile.csv", "preview": f"{stem}_preview.png",
                      "recipe": f"{stem}_generation.yaml", "metadata": f"{stem}_metadata.json"},
    }
    for key, value in supplied.items():
        if key in {"requested", "provenance"}:
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be a mapping")
            # Actual generator settings and original provenance stay authoritative.
            data[key] = dict(value, **data[key])
        else:
            data[key] = value
    validate_geometry_metadata(data)
    return data


def write_geometry_metadata(data: dict, destination: Path) -> None:
    validate_geometry_metadata(data)
    destination.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_geometry_metadata(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_geometry_metadata(data)
    return data
