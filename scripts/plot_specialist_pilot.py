#!/usr/bin/env python3
"""Plot accepted specialist geometry and curvature using final exported assets."""
import argparse
import csv
import json
from pathlib import Path
import sys
import math
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from map_editor.services.specialist_templates import FAMILIES, GENERATOR_VERSION


def load_assets(root, entry):
    metadata = json.loads((root/entry["metadata"]).read_text())
    directory = (root/entry["map"]).parent
    points = np.loadtxt(directory/metadata["artifacts"]["centerline"], delimiter=",", skiprows=1, usecols=(0, 1, 2))
    profile = np.genfromtxt(directory/metadata["artifacts"]["track_profile"], delimiter=",", names=True)
    walls = {}
    with (directory/metadata["artifacts"]["walls"]).open() as handle:
        for row in csv.DictReader(handle):
            x, y = float(row["x"]), float(row["y"])
            if math.isfinite(x) and math.isfinite(y):
                walls.setdefault(row["wall_id"], []).append((x, y))
    return metadata, points, profile, walls


def plot_pilot(root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["svg.hashsalt"] = GENERATOR_VERSION
    root = Path(root)
    manifest = json.loads((root/"manifest.json").read_text())
    plot_dir = root/"plots"
    plot_dir.mkdir(exist_ok=True)
    overview, gallery = plt.subplots(5, 2, figsize=(15, 18), layout="constrained")
    def geometry(axis, entry, metadata, points, profile, walls):
        for wall in walls.values():
            array = np.array(wall)
            axis.plot(array[:, 0], array[:, 1], color=".65", lw=.6)
        for i, maneuver in enumerate(metadata["maneuvers"]):
            start, end = maneuver["s_start_m"], maneuver["s_end_m"]
            mask = ((profile["s_m"] >= start) | (profile["s_m"] < end) if maneuver["wraps_seam"]
                    else (profile["s_m"] >= start) & (profile["s_m"] <= end))
            color = "#1666a8" if maneuver["type"] == entry["family"] else "#cc6b23"
            indices = np.flatnonzero(mask)
            if len(indices):
                axis.plot(points[indices, 0], points[indices, 1], color=color, lw=1.3)
                midpoint = points[indices[len(indices)//2]]
                axis.annotate(str(i+1), midpoint[:2], xytext=(3, 4), textcoords="offset points", fontsize=6)
        normal = np.array([-math.sin(points[0, 2]), math.cos(points[0, 2])])
        ends = np.array([points[0, :2]-normal*metadata["requested"]["track_width_m"]/2,
                         points[0, :2]+normal*metadata["requested"]["track_width_m"]/2])
        axis.plot(ends[:, 0], ends[:, 1], color="#20812b", lw=1.5)
        axis.set_aspect("equal", adjustable="datalim")
        axis.set(xlabel="x [m]", ylabel="y [m]", title=f"{entry['family']} {entry['variant']} — {entry['statistics']['target_exposure_fraction']:.1%} exposure")
        axis.grid(alpha=.2)
    for row, family in enumerate(FAMILIES):
        entries = [e for e in manifest["accepted"] if e["family"] == family]
        figure, axes = plt.subplots(2, 2, figsize=(14, 8), layout="constrained")
        for index in range(2):
            if index >= len(entries):
                axes[index, 0].set_title("No accepted candidate")
                gallery[row, index].set_title(f"{family}: incomplete")
                continue
            entry = entries[index]
            metadata, points, profile, walls = load_assets(root, entry)
            geometry(axes[index, 0], entry, metadata, points, profile, walls)
            geometry(gallery[row, index], entry, metadata, points, profile, walls)
            axis = axes[index, 1]
            axis.plot(profile["s_m"], profile["curvature_inv_m"], color="#1666a8", lw=1.)
            for maneuver in metadata["maneuvers"]:
                if maneuver["type"] == family:
                    if maneuver["wraps_seam"]:
                        axis.axvspan(maneuver["s_start_m"], metadata["measured"]["length_m"], alpha=.09, color="#1666a8")
                        if maneuver["s_end_m"]:
                            axis.axvspan(0, maneuver["s_end_m"], alpha=.09, color="#1666a8")
                    else:
                        axis.axvspan(maneuver["s_start_m"], maneuver["s_end_m"], alpha=.09, color="#1666a8")
            axis.set(xlabel="exported lap arc length [m]", ylabel="signed curvature [1/m]",
                     title=f"{'CW' if metadata['requested']['clockwise'] else 'CCW'}; target intervals shaded; support in orange on geometry")
            axis.grid(alpha=.2)
        figure.savefig(plot_dir/f"{family}_comparison.png", dpi=150)
        figure.savefig(plot_dir/f"{family}_comparison.svg", metadata={"Date": None, "Creator": "map-edit"})
        plt.close(figure)
    overview.savefig(plot_dir/"overview.png", dpi=150)
    plt.close(overview)
    return plot_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    args = parser.parse_args()
    print(plot_pilot(args.pilot))
