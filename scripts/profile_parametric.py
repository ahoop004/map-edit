#!/usr/bin/env python3
"""Profile the new backend against the recorded Phase 0 validation costs."""
import argparse
import cProfile
from dataclasses import asdict
import json
import math
from pathlib import Path
import platform
import pstats
import sys
from time import perf_counter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from map_editor.geometry import sweeper
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.parametric_track import ParametricTrackSpec,prepare_parametric_track


def profile(vehicle):
    records=[]
    prepare_parametric_track(ParametricTrackSpec("warmup",(sweeper(17/math.tau,math.tau),),spacing_m=.2,width_m=1.,vehicle=vehicle))
    names={"self_intersects","minimum_boundary_separation","_segments_intersect","segment_distance",
           "validate_geometry","validate_raster_footprint","validate_maneuver","sample","at"}
    for spacing in [.05,.02,.01]:
        spec=ParametricTrackSpec("profile",(sweeper(17/math.tau,math.tau),),spacing_m=spacing,width_m=1.,vehicle=vehicle)
        start=perf_counter()
        _,geometry,_,_=prepare_parametric_track(spec)
        elapsed=perf_counter()-start
        profiler=cProfile.Profile()
        profiler.runcall(prepare_parametric_track,spec)
        stats=pstats.Stats(profiler)
        functions=[dict(function=key[2],calls=value[1],self_seconds=value[2],cumulative_seconds=value[3])
                   for key,value in stats.stats.items() if key[2] in names]
        records.append(dict(spacing_m=spacing,sample_count=len(geometry.samples),
                            prepare_wall_seconds=elapsed,profiled_prepare_seconds=stats.total_tt,
                            functions=sorted(functions,key=lambda f:-f["cumulative_seconds"])))
    return dict(python=platform.python_version(),platform=platform.platform(),vehicle=asdict(vehicle),
        note="Phase 0 uses a 17 m rounded oval; Phase 1 uses an analytic 17 m circle. Both width 1 m. New preparation also includes raster, vehicle footprint, classification and metadata. Timings are single runs, with separate cProfile instrumentation.",
        phase0_baseline=json.loads((Path(__file__).resolve().parents[1]/"docs/phase0_profile.json").read_text()),
        cases=records)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicle",type=Path,default=Path(__file__).resolve().parents[2]/"marl_race/configs/vehicle/combined_slip.yaml")
    parser.add_argument("--output",type=Path,default=Path("docs/phase1_profile.json"))
    args=parser.parse_args()
    args.output.write_text(json.dumps(profile(VehicleProfile.from_yaml(args.vehicle)),indent=2)+"\n")
    print(args.output)
