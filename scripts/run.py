"""CLI launcher for the ROS map editor application."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from map_editor.app import main


def run() -> int:
    """Invoke the GUI entry point."""
    return main(sys.argv)


if __name__ == "__main__":
    raise SystemExit(run())
