#!/usr/bin/env python3
"""Generate a procedural track bundle from a YAML spec."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from map_editor.services.procedural_track import (
    TrackSpecError,
    generate_track_bundle,
    load_track_spec,
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a procedural track bundle.")
    parser.add_argument("input", type=Path, help="YAML track spec path.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: sample_maps/<stem>_map).",
    )
    parser.add_argument(
        "--preset",
        default="sample_default",
        choices=["sample_default"],
        help="Preset name for default settings.",
    )
    args = parser.parse_args(argv)

    _ = args.preset
    spec = load_track_spec(args.input)
    output_dir = args.output or Path("sample_maps") / f"{spec.stem}_map"

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        yaml_path = generate_track_bundle(spec, output_dir)
    except TrackSpecError as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Generated bundle: {yaml_path}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    raise SystemExit(main(sys.argv[1:]))
