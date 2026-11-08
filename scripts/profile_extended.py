#!/usr/bin/env python3
"""Profile offline long geometry and compare exact raster/separation implementations."""
import argparse
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.extended_spec import load_extended_spec,load_vehicle_snapshot
from map_editor.services.extended_pilot import default_extended_specs
from map_editor.services.extended_tracks import prepare_extended
from map_editor.services.offline_export import rasterize_corridor
from map_editor.services.procedural_track import _rasterize_walls
from map_editor.geometry.corridor import vectorized_boundary_separation
from map_editor.geometry.spatial import minimum_boundary_separation


def profile(output,recipe=None):
    if output.exists():raise FileExistsError('Refusing to overwrite performance evidence')
    spec=load_extended_spec(recipe) if recipe else default_extended_specs(load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json'))[3]
    recorder=cProfile.Profile();phases={};recorder.enable();start=perf_counter()
    prepared=prepare_extended(spec,profile=phases);elapsed=perf_counter()-start;recorder.disable()
    stats=pstats.Stats(recorder)
    calls=[]
    for (file,line,name),(primitive,total,own,cumulative,callers) in sorted(stats.stats.items(),key=lambda v:v[1][3],reverse=True)[:35]:
        path=Path(file)
        calls.append(dict(file=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name,line=line,
            function=name,primitive_calls=primitive,total_calls=total,own_seconds=own,cumulative_seconds=cumulative))
    walls=prepared.geometry.walls
    start=perf_counter();legacy=_rasterize_walls(walls,resolution=spec.resolution_m_per_pixel,padding=spec.padding_m,thickness_px=1,occupancy_mode='corridor');legacy_seconds=perf_counter()-start
    start=perf_counter();active=rasterize_corridor(walls,resolution=spec.resolution_m_per_pixel,padding=spec.padding_m);active_seconds=perf_counter()-start
    assert legacy==active,'Active-edge raster differs from legacy conventions'
    start=perf_counter();old_distance=minimum_boundary_separation(*walls,closed=True);old_seconds=perf_counter()-start
    start=perf_counter();new_distance=vectorized_boundary_separation(*walls);new_seconds=perf_counter()-start
    assert abs(old_distance-new_distance)<1e-10
    report=dict(track_id=spec.track_id,variant=spec.variant,samples=len(prepared.geometry.samples),
        source_length_m=prepared.sampled.length_m,profiled_preparation_seconds=elapsed,phases=phases,top_calls=calls,
        raster_comparison=dict(byte_identical=True,pixels_sha256=hashlib.sha256(active[0]).hexdigest(),
            width=active[1],height=active[2],legacy_seconds=legacy_seconds,active_edge_seconds=active_seconds,
            speedup=legacy_seconds/active_seconds),
        opposing_distance_comparison=dict(absolute_difference_m=abs(old_distance-new_distance),distance_m=new_distance,
            legacy_seconds=old_seconds,vectorized_seconds=new_seconds,speedup=old_seconds/new_seconds),
        scope='local geometry only; no simulator imports, access, integration or rollouts')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n');print(output)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--recipe',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();profile(args.output,args.recipe)
