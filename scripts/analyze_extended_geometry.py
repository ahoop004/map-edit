#!/usr/bin/env python3
"""Analyze only local Phase 4B bundles; no simulator/reference inputs."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.extended_analysis import analyze_extended_pilot
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot',type=Path,default=ROOT/'examples/phase4b_pilot')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();analyze_extended_pilot(args.pilot,args.output);print(args.output)
