"""Optional real-consumer integration, without changes to the reference repo."""
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from map_editor.models.annotations import Pose2D, SpawnPoint
from map_editor.services.paper_tracks import build_paper_track_spec
from map_editor.services.procedural_track import generate_track_bundle
from map_editor.services.yaml_serializer import load_map_yaml, dump_map_yaml

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(os.environ.get("MARL_RACE_ROOT", ROOT.parent / "marl_race"))


@pytest.mark.parametrize("mode,negate,reverse", [("walls", 0, False), ("corridor", 0, False),
                                                  ("corridor", 1, True)])
def test_actual_map_loading_finish_lidar_and_collisions(tmp_path, mode, negate, reverse):
    if not (REFERENCE / "src" / "utils" / "map_loader.py").is_file():
        pytest.skip("Set MARL_RACE_ROOT to a physics-correctness checkout for the actual consumer smoke test")
    for name in ["numpy", "numba", "scipy", "PIL"]:
        if importlib.util.find_spec(name) is None:
            pytest.skip(f"marl_race smoke test requires {name}")
    spec = replace(build_paper_track_spec(), occupancy_mode=mode, negate=negate)
    if reverse:
        spec = replace(spec, control_points=list(reversed(spec.control_points)))
    path = generate_track_bundle(spec, tmp_path / spec.stem)
    doc = load_map_yaml(path)
    a, b = doc.annotations.centerline[10:12]
    import math
    doc.annotations.spawn_points = [SpawnPoint("grid_1", Pose2D(a.x, a.y, math.atan2(b.y - a.y, b.x - a.x)))]
    dump_map_yaml(doc, path)
    process = subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_marl_race.py"),
                              str(path), "--marl-race-root", str(REFERENCE)],
                             capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads(process.stdout)
    assert report["occupancy_mode"] == mode
    assert report["named_spawns"] == ["grid_1"]
    assert report["environment_overrides"]["track_inverted"] == bool(negate)
    assert report["finish_crossings"] == {"forward": True, "reverse": False, "beyond_endpoint": False}
