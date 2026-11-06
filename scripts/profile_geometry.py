#!/usr/bin/env python3
"""Profile existing geometric checks without changing their implementation."""
import argparse
import cProfile
from dataclasses import replace
import json
from pathlib import Path
import platform
import pstats
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from map_editor.services.paper_tracks import build_paper_track_spec
from map_editor.services.procedural_track import (
    build_oval_control_points, prepare_track_geometry, _rasterize_walls, _validate_corridor_raster,
)


def profile(spacings):
    results = []
    names = {"build_track_profile", "_polyline_self_intersects", "_ensure_wall_constraints",
             "_segments_intersect", "_ray_wall_distance", "_validate_centerline"}
    for spacing in spacings:
        # A smooth oval has enough source spline samples for dense resampling.
        spec = replace(build_paper_track_spec(), control_points=build_oval_control_points(10, 10),
                       centerline_spacing=spacing, occupancy_mode="corridor")
        # Wall time measured separately from instrumentation overhead.
        start = perf_counter()
        geometry = prepare_track_geometry(spec)
        elapsed = perf_counter() - start
        profiler = cProfile.Profile()
        profiler.runcall(prepare_track_geometry, spec)
        stats = pstats.Stats(profiler)
        functions = [{"function": key[2], "calls": value[1], "self_seconds": value[2],
                      "cumulative_seconds": value[3]}
                     for key, value in stats.stats.items() if key[2] in names]
        start = perf_counter()
        pixels, width, height, ox, oy = _rasterize_walls(geometry.walls, resolution=spec.resolution,
            padding=spec.padding, thickness_px=spec.wall_thickness_px, occupancy_mode=spec.occupancy_mode)
        raster_seconds = perf_counter() - start
        start = perf_counter()
        _validate_corridor_raster(geometry.centerline, pixels, width, height, ox, oy, spec.resolution)
        results.append({"family": "rounded_oval", "centerline_spacing_m": spacing,
                        "sample_count": len(geometry.samples), "wall_vertices_each": len(geometry.walls[0]),
                        "geometry_wall_seconds": elapsed, "raster_seconds": raster_seconds,
                        "raster_validation_seconds": perf_counter() - start,
                        "profiled_geometry_seconds": stats.total_tt,
                        "functions": sorted(functions, key=lambda x: -x["cumulative_seconds"])})
    return {"python": platform.python_version(), "platform": platform.platform(),
            "note": "One wall-time run and one cProfile run per case; cumulative timings overlap. Not a benchmark guarantee.",
            "cases": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacings", type=float, nargs="+", default=[.05, .02, .01])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(profile(args.spacings), indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end="")
