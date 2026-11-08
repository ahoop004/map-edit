#!/usr/bin/env python3
"""Offline bounded failure evidence; requests and constraints stay unchanged."""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from map_editor.geometry.width_profile import WidthProfile
from map_editor.geometry.validation import GeometryLimits
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.extended_pilot import default_extended_specs
from map_editor.services.extended_tracks import prepare_extended,ExtendedGenerationError


def audit(output):
    if output.exists():raise FileExistsError('Refusing to overwrite extended rejection evidence')
    specs=default_extended_specs(load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json'))
    base=specs[0];topology=base.topologies[0]
    impossible=replace(topology,turns=tuple(replace(s,angle_bounds_deg=(12.,13.)) for s in topology.turns))
    width_base=replace(specs[8],candidate_budget=1)
    sharp=WidthProfile(((0.,.75),(.01,1.3),(.02,.75),(1.,.75)),((0.,.75),(1.,.75)))
    cases=[('heading_deficit_outside_supporting_bounds',replace(base,topologies=(impossible,),candidate_budget=2)),
        ('joint_solver_budget_exhausted',replace(base,optimization_iterations=1,candidate_budget=1)),
        ('insufficient_corridor_width',replace(width_base,width=WidthProfile.constant(.5))),
        ('offset_curvature_singularity',replace(width_base,width=WidthProfile.constant(6.))),
        ('abrupt_width_gradient',replace(width_base,width=sharp)),
        ('unachievable_corner_count',replace(base,objectives={'corner_count':(100,120)},candidate_budget=1)),
        ('configured_radius_violation',replace(base,limits=GeometryLimits(minimum_radius_m=4.),candidate_budget=1))]
    records=[]
    for name,spec in cases:
        try:prepare_extended(spec)
        except ExtendedGenerationError as exc:
            records.append(dict(case=name,status='rejected',recipe=spec.recipe(),reason=str(exc),attempts=exc.attempts))
        else:raise AssertionError('Failure audit unexpectedly accepted '+name)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(generator=base.recipe()['generator'],scope='offline bounded observations; no global infeasibility claim',cases=records),indent=2,allow_nan=False)+'\n')
    print(output)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();audit(args.output)
