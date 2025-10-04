"""Tests for wall CSV export helpers."""

from __future__ import annotations

from pathlib import Path

from map_editor.models.annotations import Point2D
from map_editor.services.wall_extraction import export_walls_csv


def test_export_walls_csv_closes_loops(tmp_path: Path) -> None:
    wall = [
        Point2D(0.0, 0.0),
        Point2D(1.0, 0.0),
        Point2D(1.0, 1.0),
    ]

    output = tmp_path / "walls.csv"
    export_walls_csv([wall], output)

    lines = output.read_text().strip().splitlines()
    assert lines[0] == "wall_id,vertex_id,x,y"
    first = lines[1].split(",")
    last = lines[-1].split(",")

    assert first[0] == "0" and last[0] == "0", "Should remain the same wall"
    assert first[2] == last[2]
    assert first[3] == last[3]

