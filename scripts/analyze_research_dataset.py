#!/usr/bin/env python3
"""Audit and summarize the offline formal dataset without simulator inputs."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.dataset_analysis import analyze_dataset
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze_dataset(a.dataset,a.output);print('Analyzed',r['count'],'tracks')
