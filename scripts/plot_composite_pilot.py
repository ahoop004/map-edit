#!/usr/bin/env python3
"""Plot final composite assets: geometry, sequence, curvature, exposure and transitions."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from map_editor.services.composite_spec import GENERATOR_VERSION
from map_editor.services.composite_statistics import MATRIX_LABELS

COLORS={"straight":"#2274a5","hairpin":"#ca3c36","sweeper":"#2e8b57","chicane":"#7a4bb7","s_curve":"#de8a20","connector":"#777777"}
ABBREVIATIONS={"straight":"St","hairpin":"Hp","sweeper":"Sw","chicane":"Ch","s_curve":"S","connector":"Co"}


def parts(window,lap):
    return [(window["s_start_m"],lap),(0.,window["s_end_m"])] if window["wraps_seam"] else [(window["s_start_m"],window["s_end_m"])]


def load_assets(root,entry):
    metadata=json.loads((root/entry["metadata"]).read_text())
    folder=(root/entry["map"]).parent
    points=np.loadtxt(folder/metadata["artifacts"]["centerline"],delimiter=",",skiprows=1,usecols=(0,1,2))
    profile=np.genfromtxt(folder/metadata["artifacts"]["track_profile"],delimiter=",",names=True)
    walls={}
    with (folder/metadata["artifacts"]["walls"]).open() as handle:
        for row in csv.DictReader(handle):
            x,y=float(row["x"]),float(row["y"])
            if math.isfinite(x) and math.isfinite(y):
                walls.setdefault(row["wall_id"],[]).append([x,y])
    return metadata,points,profile,walls


def plot_geometry(axis,entry,metadata,points,profile,walls):
    lap=metadata["measured"]["length_m"]
    for wall in walls.values():
        p=np.array(wall)
        axis.plot(p[:,0],p[:,1],color=".7",lw=.65)
    for window in metadata["maneuvers"]:
        label=window["type"] if window["requested"]["composition_role"]=="primary" else "connector"
        for start,end in parts(window,lap):
            if end-start<1e-10:
                continue
            indices=np.flatnonzero((profile["s_m"]>=start-1e-8)&(profile["s_m"]<=end+1e-8))
            if len(indices):
                path=points[indices,:2]
                if end==lap:
                    path=np.vstack([path,points[0,:2]])
                axis.plot(path[:,0],path[:,1],color=COLORS[label],lw=1.6 if label!="connector" else 1.)
    normal=np.array([-math.sin(points[0,2]),math.cos(points[0,2])])*metadata["requested"]["track_width_m"]/2
    ends=np.array([points[0,:2]-normal,points[0,:2]+normal])
    axis.plot(ends[:,0],ends[:,1],color="black",lw=2)
    axis.set_aspect("equal",adjustable="datalim")
    axis.set(xlabel="x [m]",ylabel="y [m]",title=f"{entry['variant']} — {entry['statistics']['length_m']:.1f} m")
    axis.grid(alpha=.2)


def plot_pilot(root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    matplotlib.rcParams["svg.hashsalt"]=GENERATOR_VERSION
    root=Path(root)
    manifest=json.loads((root/"manifest.json").read_text())
    folder=root/"plots"
    folder.mkdir(exist_ok=True)
    gallery,gallery_axes=plt.subplots(4,2,figsize=(16,19),layout="constrained")
    for gallery_axis,entry in zip(gallery_axes.flat,manifest["accepted"]):
        metadata,points,profile,walls=load_assets(root,entry)
        stats=metadata["provenance"]["composite_statistics"]
        lap=metadata["measured"]["length_m"]
        figure,axes=plt.subplots(2,3,figsize=(18,10),layout="constrained")
        plot_geometry(axes[0,0],entry,metadata,points,profile,walls)
        plot_geometry(gallery_axis,entry,metadata,points,profile,walls)
        axes[0,1].plot(profile["s_m"],profile["curvature_inv_m"],lw=1,color="#234a7d")
        axes[0,1].set(xlabel="exported arc length [m]",ylabel="signed curvature [1/m]",title="Curvature; positive = left")
        axes[0,1].grid(alpha=.2)
        sequence=axes[0,2]
        for a in metadata["maneuvers"]:
            label=a["type"] if a["requested"]["composition_role"]=="primary" else "connector"
            for start,end in parts(a,lap):
                if end-start<1e-10:
                    continue
                sequence.barh(0,end-start,left=start,color=COLORS[label],height=.6,edgecolor="white",lw=.3)
                if end-start>2:
                    sequence.text((start+end)/2,0,ABBREVIATIONS[label],ha="center",va="center",fontsize=7,color="white")
        sequence.set(xlim=(0,lap),yticks=[],xlabel="entry/exit arc positions [m]",title="Ordered windows (Co includes connectors)")
        sequence.set_ylim(-.7,.7)
        families=[*MATRIX_LABELS[:-1],"transition"]
        exposures=[stats["family_exposure_fractions"][f]*100 for f in families]
        axes[1,0].bar(range(6),exposures,color=[COLORS[f] for f in MATRIX_LABELS])
        axes[1,0].set(xticks=range(6),xticklabels=[ABBREVIATIONS[f] for f in MATRIX_LABELS],ylabel="lap exposure [%]",title="Family coverage; nested demand regions do not add exposure")
        for i,value in enumerate(exposures):
            axes[1,0].text(i,value+.5,f"{value:.1f}",ha="center",fontsize=8)
        matrix=np.array([[stats["transition_count_matrix"][a][b] for b in MATRIX_LABELS] for a in MATRIX_LABELS])
        axes[1,1].imshow(matrix,cmap="Blues",vmin=0)
        for i in range(6):
            for j in range(6):
                axes[1,1].text(j,i,str(matrix[i,j]),ha="center",va="center",fontsize=8)
        axes[1,1].set(xticks=range(6),yticks=range(6),xticklabels=[ABBREVIATIONS[f] for f in MATRIX_LABELS],
                      yticklabels=[ABBREVIATIONS[f] for f in MATRIX_LABELS],xlabel="to",ylabel="from",title="Cyclic transition counts; connector state explicit")
        primary_labels=MATRIX_LABELS[:-1]
        projected=np.array([[stats["projected_primary_order_matrix"][a][b] for b in primary_labels] for a in primary_labels])
        axes[1,2].imshow(projected,cmap="Greens",vmin=0)
        for i in range(5):
            for j in range(5):
                axes[1,2].text(j,i,str(projected[i,j]),ha="center",va="center",fontsize=8)
        axes[1,2].set(xticks=range(5),yticks=range(5),xticklabels=[ABBREVIATIONS[f] for f in primary_labels],
                      yticklabels=[ABBREVIATIONS[f] for f in primary_labels],xlabel="next primary family",ylabel="from primary family",
                      title="Projected order across explicitly recorded connector bridges")
        figure.suptitle(f"{entry['variant']}: {stats['primary_switch_density_per_100m']:.2f} primary switches / 100 m; "
                        f"{stats['minimum_primary_window_m']:.2f}–{stats['maximum_primary_window_m']:.2f} m primary windows; evaluation only")
        figure.legend(handles=[Patch(color=COLORS[f],label=f) for f in MATRIX_LABELS],loc="outside lower center",ncol=6)
        figure.savefig(folder/f"{entry['variant']}.png",dpi=145)
        figure.savefig(folder/f"{entry['variant']}.svg",metadata={"Date":None,"Creator":"map-edit"})
        plt.close(figure)
    gallery.legend(handles=[Patch(color=COLORS[f],label=f) for f in MATRIX_LABELS],loc="outside lower center",ncol=6)
    gallery.savefig(folder/"overview.png",dpi=145)
    plt.close(gallery)
    return folder


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot",type=Path)
    args=parser.parse_args()
    print(plot_pilot(args.pilot))
