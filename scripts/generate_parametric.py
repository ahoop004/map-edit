#!/usr/bin/env python3
"""Replay a parametric-curvature closed-track recipe; no legacy fitting."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from map_editor.services.parametric_track import load_parametric_spec, generate_parametric_bundle

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        print(generate_parametric_bundle(load_parametric_spec(args.recipe),args.output))
    except (ValueError,OSError) as exc:
        parser.exit(1,f"Generation failed: {exc}\n")
