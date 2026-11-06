#!/usr/bin/env python3
"""Create a small Phase 1 geometry demonstration, not a training collection."""
from dataclasses import asdict
import argparse
import csv
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from map_editor.geometry import GENERATOR_VERSION, GeometrySequence, straight, hairpin, sweeper, chicane, s_curve, transition
from map_editor.geometry.measurement import MeasurementTolerances, measure, validate_maneuver
from map_editor.geometry.validation import VehicleProfile, validate_geometry, feasibility_advisory
from map_editor.services.parametric_track import ParametricTrackSpec,generate_parametric_bundle
from map_editor.services.wall_extraction import export_walls_csv
from map_editor.exporters.centerline import CenterlineSample,export_centerline_csv


def demonstration_sequences():
    return {
        "hairpin_left":(hairpin(4),),
        "hairpin_right":(hairpin(4,direction="right"),),
        "long_straight":(straight(40),),
        "chicane_left_right":(chicane(4,3,separation_m=2),),
        "chicane_right_left":(chicane(4,3,separation_m=2,direction="right_left"),),
        "s_curve":(s_curve((5,7)),),
        "sustained_sweeper":(sweeper(6,math.radians(120),entry_transition_m=1.2,exit_transition_m=1.2,end_radius_m=9),),
        "smooth_connections":(straight(6),transition(3,0,.125),sweeper(8,.7),transition(3,.125,0),straight(6)),
        "closed_stadium":(straight(12),hairpin(4),straight(12),hairpin(4)),
    }


def demonstrate(output,vehicle,spacing=.1):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["svg.hashsalt"]=GENERATOR_VERSION
    output.mkdir(parents=True,exist_ok=True)
    overview,overview_axes=plt.subplots(3,3,figsize=(14,12),layout="constrained")
    report={"generator":GENERATOR_VERSION,"spacing_m":spacing,"vehicle":asdict(vehicle),"examples":{}}
    for gallery,(name,maneuvers) in zip(overview_axes.flat,demonstration_sequences().items()):
        closed=name=="closed_stadium"
        sampled=GeometrySequence(maneuvers).sample(spacing,closed=closed)
        walls,validation=validate_geometry(sampled,1.5,vehicle=vehicle)
        measured=[validate_maneuver(m,sampled.states[a:b+1],width_m=1.5) for m,(a,b) in zip(maneuvers,sampled.spans)]
        directory=output/name
        directory.mkdir(exist_ok=True)
        if closed:
            path=generate_parametric_bundle(ParametricTrackSpec(name,maneuvers,spacing_m=spacing,vehicle=vehicle),directory)
            artifacts={"map":path.name}
            validation=json.loads((directory/f"{name}_metadata.json").read_text())["provenance"]["validation"]
        else:
            export_centerline_csv([CenterlineSample(p.x,p.y,p.heading) for p in sampled.states],directory/f"{name}_centerline.csv")
            export_walls_csv(walls,directory/f"{name}_walls.csv",closed=False)
            # Open demonstrations are not simulator maps or closed-schema metadata.
            artifacts={"centerline":f"{name}_centerline.csv","walls":f"{name}_walls.csv"}
        with (directory/"differential_profile.csv").open("w",newline="") as handle:
            writer=csv.writer(handle)
            writer.writerow(["s_m","x_m","y_m","heading_rad","curvature_inv_m","curvature_rate_inv_m2"])
            writer.writerows((p.s,p.x,p.y,p.heading,p.curvature,p.curvature_rate) for p in sampled.states)
        data={"closed":closed,"is_simulator_bundle":closed,"artifacts":artifacts,
              "curve_length_m":sampled.length_m,"validation":validation,
              "aggregate_measurements":measure(sampled.states,width_m=1.5),
              "continuity":list(sampled.joints),"measurement_tolerances":asdict(MeasurementTolerances()),
              "advisory":feasibility_advisory(sampled,vehicle),
              "maneuvers":[dict(type=m.type,direction=m.direction,requested=m.requested,measured=value,difficulty={"label":"unrated"})
                           for m,value in zip(maneuvers,measured)]}
        (directory/"measurements.json").write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
        figure,(axis,curvature_axis)=plt.subplots(1,2,figsize=(12,4.5),layout="constrained")
        for plot in (axis,gallery):
            for wall in walls:
                xy=wall+[wall[0]] if closed else wall
                plot.plot([p.x for p in xy],[p.y for p in xy],color=".65",lw=.8)
            for i,(m,(a,b)) in enumerate(zip(maneuvers,sampled.spans)):
                states=sampled.states[a:b+1]
                plot.plot([p.x for p in states],[p.y for p in states],label=f"{i+1}: {m.type}")
                middle=states[len(states)//2]
                plot.annotate(str(i+1),(middle.x,middle.y),xytext=(3,5),textcoords="offset points",fontsize=8)
            plot.set_aspect("equal",adjustable="datalim")
            plot.set_title(name.replace("_"," "))
            plot.set_xlabel("x [m]")
            plot.set_ylabel("y [m]")
            plot.grid(alpha=.2)
        axis.legend(fontsize=8,loc="best")
        curvature_axis.plot([p.s for p in sampled.states],[p.curvature for p in sampled.states])
        for a,b in sampled.spans:
            curvature_axis.axvline(sampled.states[a].s,color=".7",lw=.6)
        curvature_axis.set(xlabel="physical arc length s [m]",ylabel="signed curvature [1/m]",title="Sampled curvature; positive = left")
        curvature_axis.grid(alpha=.2)
        figure.savefig(directory/"geometry.png",dpi=150)
        figure.savefig(directory/"geometry.svg",metadata={"Date":None,"Creator":"map-edit"})
        plt.close(figure)
        report["examples"][name]=data
    overview.savefig(output/"overview.png",dpi=160)
    plt.close(overview)
    (output/"demonstrations.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("examples/phase1"))
    parser.add_argument("--vehicle",type=Path,default=Path(__file__).resolve().parents[2]/"marl_race/configs/vehicle/combined_slip.yaml")
    parser.add_argument("--spacing",type=float,default=.1)
    args=parser.parse_args()
    demonstrate(args.output,VehicleProfile.from_yaml(args.vehicle),args.spacing)
    print(f"Generated nine geometry demonstrations in {args.output}")
