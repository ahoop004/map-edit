#!/usr/bin/env python3
"""Bounded failures with unchanged constraints and complete decision journals."""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from map_editor.geometry.validation import VehicleProfile,GeometryLimits
from map_editor.services.technical_pilot import default_technical_specs
from map_editor.services.technical_tracks import prepare_technical,TechnicalGenerationError


def audit(reference,output):
    if output.exists():raise FileExistsError('Refusing to overwrite rejection evidence')
    defaults=default_technical_specs(VehicleProfile.from_yaml(reference/'configs/vehicle/combined_slip.yaml'))
    base=defaults[0]
    first=base.inventory[0]
    bad=replace(first,parameters=dict(first.parameters,turn_angle_deg=80))
    cases=[('impossible_connector_bounds',replace(base,connector_bounds_m=(.4,.5),candidate_budget=2)),
        ('fixed_primary_heading_mismatch',replace(base,inventory=(bad,*base.inventory[1:]),candidate_budget=2)),
        ('excess_supporting_geometry',replace(base,maximum_supporting_fraction=.01,candidate_budget=2)),
        ('unachievable_complexity_target',replace(base,objectives={'p95_curvature_inv_m':(2.,3.)},candidate_budget=2)),
        ('minimum_radius_violation',replace(base,limits=GeometryLimits(minimum_radius_m=4.),candidate_budget=2))]
    # Reproduce the explicitly abandoned preliminary long-straight placement.
    exploratory=defaults[10]
    inventory=list(exploratory.inventory)
    for index,length in ((0,50.),(1,6.),(3,35.),(5,7.)):
        inventory[index]=replace(inventory[index],straight_after_m=length)
    target=sum(r.build().length_m+r.straight_after_m for r in inventory)+52.
    cases.append(('exploratory_long_straight_placement',replace(exploratory,inventory=tuple(inventory),
        target_lap_length_m=target,lap_length_range_m=(target-.5,target+.5))))
    records=[]
    for name,spec in cases:
        try:
            prepare_technical(spec)
            raise AssertionError('Rejection audit unexpectedly accepted '+name)
        except TechnicalGenerationError as exc:
            records.append(dict(case=name,status='rejected',recipe=spec.recipe(),reason=str(exc),attempts=exc.attempts))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(scope='bounded feasibility observations; not universal infeasibility proofs',cases=records),indent=2)+'\n')
    print(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--marl-race-root',type=Path,default=ROOT.parent/'marl_race')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.marl_race_root,a.output)
