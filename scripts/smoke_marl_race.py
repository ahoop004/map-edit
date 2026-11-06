#!/usr/bin/env python3
"""Read-only smoke test against a local physics-correctness marl_race checkout."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile


def smoke(bundle: Path, reference: Path) -> dict:
    sys.dont_write_bytecode = True
    os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "map-edit-numba-cache"))
    sys.path.insert(0, str(reference / "src"))
    import numpy as np
    import yaml
    from PIL import Image
    from core.map_selection import discover_map_bundles, resolve_bundle_yaml
    from env.map_config import resolve_map_runtime_config
    from env.centerline_state import LapTracker, resolve_finish_line_config, validate_finish_line
    from env.collision_state import RaceLifecycle
    from env.spawn import extract_spawn_points, load_spawn_points_from_map, sample_random_centerline_spawn
    from physics.collision_models import swept_map_contact
    from physics.laser_models import ScanSimulator2D, distance_transform, xy_2_rc
    from utils.centerline import prepare_centerline_geometry
    from utils.map_loader import MapLoader
    from agents.mpc.racing import _map_distance_field, _distance

    bundle = bundle.resolve()
    metadata = yaml.safe_load(bundle.read_text())
    inverted = bool(metadata.get("negate", 0))
    cfg = {"map_dir": str(bundle.parent), "map_yaml": bundle.name, "track_inverted": inverted}
    data = MapLoader().load(cfg)
    assert data.centerline is not None and len(data.centerline) >= 4
    assert data.walls is not None and len(data.walls) == 2
    assert all(len(wall) >= 4 and np.isfinite(wall).all() for wall in data.walls.values())
    assert data.centerline.shape[1] == 3 and np.isfinite(data.centerline).all()
    assert resolve_bundle_yaml(bundle.parent, bundle.stem) == bundle
    assert bundle.parent.name in discover_map_bundles({"map_dir": str(bundle.parent.parent)})
    runtime = resolve_map_runtime_config(cfg, data)
    assert runtime.image_path == data.image_path and runtime.image_size == data.image_size
    geometry = prepare_centerline_geometry(data.centerline)
    assert geometry.closed
    with Image.open(bundle.with_suffix(".png")) as png, Image.open(bundle.with_suffix(".pgm")) as pgm:
        assert np.array_equal(np.asarray(png.convert("L")), np.asarray(pgm.convert("L")))
    points = extract_spawn_points(data, data.metadata)
    if points:
        poses = load_spawn_points_from_map(str(bundle), list(points))
        assert np.allclose(poses, np.asarray(list(points.values())))
    random_spawn = sample_random_centerline_spawn(centerline=data.centerline, agent_ids=["car"],
                         rng=np.random.default_rng(42), config={"min_distance": 1.0})
    assert np.isfinite(random_spawn.poses).all()

    finish = validate_finish_line(resolve_finish_line_config(None, data.metadata), centerline=data.centerline)
    midpoint = (finish["start"] + finish["end"]) * .5
    direction = finish["direction"]
    assert np.dot(direction, data.centerline[1, :2] - data.centerline[0, :2]) > 0
    results = {}
    for name, start, end, expected in [
        ("forward", midpoint - direction, midpoint + direction, True),
        ("reverse", midpoint + direction, midpoint - direction, False),
        ("beyond_endpoint", midpoint - direction + finish["segment"] * 3,
         midpoint + direction + finish["segment"] * 3, False),
    ]:
        lifecycle = RaceLifecycle(["car"], 2)
        tracker = LapTracker(["car"], finish, lifecycle)
        tracker.reset(np.array([start[0]]), np.array([start[1]]))
        accepted = tracker.update(np.array([end[0]]), np.array([end[1]]),
                                  np.array([1.]), np.array([0.]), step=1)["car"]
        assert accepted == expected, (name, accepted)
        results[name] = bool(accepted)

    scanner = ScanSimulator2D(181, math.pi, max_range=30.)
    scanner.set_map(str(bundle), ".png", map_data=data)
    field = _map_distance_field(data.image_path, data.metadata)
    assert np.array_equal(field > 0, scanner.map_img)
    resolution = float(metadata["resolution"])
    origin = metadata["origin"]
    # The generated map has zero yaw; all physics coordinates below are local.
    assert origin[2] == 0
    for x, y in data.centerline[:, :2]:
        row, col = xy_2_rc(float(x), float(y), scanner.orig_x, scanner.orig_y,
                          scanner.orig_c, scanner.orig_s, scanner.map_height, scanner.map_width, resolution)
        assert scanner.map_img[row, col]
    clearance = distance_transform(*data.centerline[0, :2], scanner.orig_x, scanner.orig_y,
        scanner.orig_c, scanner.orig_s, scanner.map_height, scanner.map_width, resolution, scanner.dt)
    assert clearance > 0
    scans = scanner.scan(data.centerline[0].astype(float), None, std_dev=0.)
    assert np.isfinite(scans).all() and np.min(scans) > 0
    assert distance_transform(origin[0] - .1, origin[1], scanner.orig_x, scanner.orig_y,
        scanner.orig_c, scanner.orig_s, scanner.map_height, scanner.map_width, resolution, scanner.dt) == 0
    assert _distance(field, origin[0] - .1, origin[1], np.asarray(origin), resolution) == -1

    def contact_at(world):
        trace = np.zeros((1, 4, 3))
        trace[0, 0, :2] = np.asarray(world) - origin[:2]
        return swept_map_contact(trace, np.array([.29, .29, .155, .155]), scanner.map_img, resolution)

    assert not np.isfinite(contact_at(data.centerline[0, :2]))
    boundary = next(iter(data.walls.values()))[0]
    assert contact_at(boundary) == 0
    assert contact_at(np.array(origin[:2]) - [1, 1]) == 0
    outside = np.array(origin[:2]) + [.35, .35]
    mode = metadata.get("occupancy", {}).get("mode", "walls")
    if mode == "corridor":
        assert contact_at(outside) == 0
        assert scanner.dt[0, 0] == 0
    else:
        assert not np.isfinite(contact_at(outside))
    return {"bundle": str(bundle), "occupancy_mode": mode,
            "environment_overrides": {"track_inverted": inverted},
            "image_size": data.image_size, "centerline_samples": len(data.centerline),
            "wall_count": len(data.walls), "closed": geometry.closed,
            "length_m": geometry.total_length, "named_spawns": list(points),
            "random_centerline_spawn": "passed", "finish_crossings": results,
            "clearance_m_at_start": float(clearance), "lidar_collision_coordinates": "passed",
            "mpc_clearance_mask_agreement": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--marl-race-root", type=Path, default=Path(__file__).resolve().parents[2] / "marl_race")
    args = parser.parse_args()
    print(json.dumps(smoke(args.bundle, args.marl_race_root), indent=2))


if __name__ == "__main__":
    main()
