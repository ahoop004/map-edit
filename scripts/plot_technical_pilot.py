#!/usr/bin/env python3
"""Consistent metric geometry gallery and scale-explicit reference comparisons."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.technical_analysis import read_centerline,analyze_geometry,SCALES_M
from map_editor.services.composite_statistics import contains
from analyze_technical_geometry import collect
COLORS=dict(corner='#c44737',kink='#bb8d14',compound_corner='#9b458b',hairpin='#632870',
    straight='#24779e',chicane='#57793d',s_curve='#dd8c27',transition='#999999')
GROUPS=dict(reference='#222222',phase2='#8ca95f',phase3='#6795ba',phase3b='#b24939')


def draw_geometry(ax,xy,metadata=None):
    from matplotlib.collections import LineCollection
    extended=np.vstack([xy,xy[0]])
    s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(extended,axis=0),axis=1))]
    segments=np.stack([extended[:-1],extended[1:]],axis=1)
    if metadata:
        colors=[COLORS[next(a['type'] for a in metadata['maneuvers'] if contains(a,float(p)))] for p in s[:-1]]
    else:colors=['#222222']*len(xy)
    xy=xy-(xy.max(axis=0)+xy.min(axis=0))/2
    segments=segments-(extended.max(axis=0)+extended.min(axis=0))/2
    ax.add_collection(LineCollection(segments,colors=colors,linewidths=1.4))
    ax.set_aspect('equal');ax.set(xlabel='x [m], centered',ylabel='y [m], centered')
    ax.grid(alpha=.2)
    return float(np.ptp(xy,axis=0).max())


def plot(pilot,reference,analysis):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    matplotlib.rcParams['svg.hashsalt']='phase3b.technical.v1'
    plt.rcParams.update({'font.size':8})
    folder=pilot/'plots';folder.mkdir(exist_ok=True)
    report=json.loads(analysis.read_text());manifest=json.loads((pilot/'manifest.json').read_text())
    entries=collect(pilot,reference)
    paths={name:path for name,group,path,walls in entries}
    datasets=[]
    for entry in manifest['accepted']:
        metadata=json.loads((pilot/entry['metadata']).read_text());name=entry['variant']
        xy=read_centerline(paths[name]);datasets.append((name,xy,metadata))
    for name in ('Budapest','Hockenheim'):datasets.append((name,read_centerline(paths[name]),None))
    span=max(np.ptp(xy,axis=0).max() for _,xy,_ in datasets)*1.12
    fig,axes=plt.subplots(4,4,figsize=(17,17),constrained_layout=True)
    for ax,(name,xy,metadata) in zip(axes.flat,datasets):
        draw_geometry(ax,xy,metadata)
        ax.set(xlim=(-span/2,span/2),ylim=(-span/2,span/2),title=f'{name}\n{analyze_geometry(xy)["raw_lap_length_m"]:.1f} m')
    for ax in list(axes.flat)[len(datasets):]:ax.axis('off')
    fig.suptitle(f'Phase 3B and reference geometry — identical {span:.0f} m × {span:.0f} m axes; no resizing of geometry',fontsize=14)
    fig.legend(handles=[Patch(color=v,label=k) for k,v in COLORS.items()],loc='lower center',ncol=8)
    fig.savefig(folder/'overview.png',dpi=160);fig.savefig(folder/'overview.svg',metadata={'Date':None});plt.close(fig)
    for name,xy,metadata in datasets[:12]:
        item=next(e for e in manifest['accepted'] if e['variant']==name)
        fig,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
        draw_geometry(axes[0,0],xy,metadata);axes[0,0].set(xlim=(-span/2,span/2),ylim=(-span/2,span/2))
        axes[0,0].set_title('Same metric scale as overview and reference tracks')
        for sigma in (0.,.4,.8):
            metrics=analyze_geometry(xy,sigma_m=sigma,include_profile=True)
            axes[0,1].plot(metrics['profile']['s_m'],metrics['profile']['curvature_inv_m'],lw=.8,label=f'σ={sigma:g} m')
        axes[0,1].set(xlabel='raw resampled arc position [m]',ylabel='curvature [1/m]',title='Coordinate-derived periodic curvature');axes[0,1].legend()
        stats=item['statistics'];corners=stats['corners']
        x=np.arange(len(corners));axes[1,0].bar(x,[abs(c['signed_angle_deg']) for c in corners],
            color=['#c44737' if c['direction']=='left' else '#24779e' for c in corners])
        axes[1,0].set(xlabel='significant turning region (periodic)',ylabel='absolute angle [degrees]',title='σ=0.4 m; red=left, blue=right')
        family=stats['family_exposure_fractions'];labels=list(family)
        axes[1,1].bar(labels,[family[k]*100 for k in labels],color=[COLORS[k] for k in labels])
        axes[1,1].tick_params(axis='x',rotation=25)
        axes[1,1].set(ylabel='lap exposure [%]',title=f"Primary {stats['primary_coverage']:.1%}; supporting {stats['supporting_fraction']:.1%}")
        fig.suptitle(f"{name}: {stats['raw_lap_length_m']:.1f} m; {stats['corner_density_per_100m']:.2f} corners/100 m; geometric measurements only",fontsize=12)
        fig.savefig(folder/(name+'.png'),dpi=160);fig.savefig(folder/(name+'.svg'),metadata={'Date':None});plt.close(fig)
    tracks=report['tracks'];names=[t['name'] for t in tracks]
    base=[next(m for m in t['scales'] if m['sigma_m']==.4) for t in tracks]
    fields=[('raw_lap_length_m','Lap length [m]'),('p95_curvature_inv_m','95th percentile |κ| [1/m]'),
        ('minimum_sustained_radius_m','Minimum sustained radius [m], 1 m window'),
        ('corner_density_per_100m','Significant corners / 100 m'),('longest_straight_m','Longest near-straight [m]'),
        ('curvature_reversals_per_100m','Directional reversals / 100 m')]
    fig,axes=plt.subplots(2,3,figsize=(19,13),constrained_layout=True)
    for ax,(field,label) in zip(axes.flat,fields):
        ax.barh(names,[m[field] for m in base],color=[GROUPS[t['group']] for t in tracks])
        ax.invert_yaxis();ax.set_xlabel(label);ax.grid(axis='x',alpha=.2)
    fig.suptitle('Budapest / Hockenheim vs Phase 2, 3, 3B — all analyzed at σ=0.4 m',fontsize=15)
    fig.savefig(folder/'reference_comparison.png',dpi=160);fig.savefig(folder/'reference_comparison.svg',metadata={'Date':None});plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(16,9),constrained_layout=True)
    selected=[t for t in tracks if t['name'] in ('Budapest','Hockenheim','P3 five_asymmetric','compact_technical_1','high_speed_transitions_1')]
    fields=[('p95_curvature_inv_m','95th percentile |κ| [1/m]'),('maximum_curvature_inv_m','Peak |κ| [1/m]'),
        ('maximum_curvature_rate_inv_m2','Peak |dκ/ds| [1/m²]'),('minimum_sustained_radius_m','1 m sustained minimum radius [m]'),
        ('corner_count','Significant turning regions'),('longest_straight_m','Longest near-straight [m]')]
    for ax,(field,label) in zip(axes.flat,fields):
        for t in selected:ax.plot(SCALES_M,[s[field] for s in t['scales']],marker='o',ms=3,label=t['name'])
        ax.set(xlabel='Periodic Gaussian sigma [m]',ylabel=label);ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=7)
    fig.suptitle('Spatial-scale sensitivity: raw sampling spikes versus sustained geometric demand',fontsize=14)
    fig.savefig(folder/'scale_sensitivity.png',dpi=160);fig.savefig(folder/'scale_sensitivity.svg',metadata={'Date':None});plt.close(fig)
    # Direct curvature and corner-angle distributions for the two references and each pilot category.
    selected=[(name,group,path) for name,group,path,w in entries if name in ('Budapest','Hockenheim',
        'compact_technical_1','irregular_mixed_1','corner_dense_1','high_speed_transitions_1')]
    fig,axes=plt.subplots(2,1,figsize=(12,8),constrained_layout=True)
    for name,group,path in selected:
        m=analyze_geometry(read_centerline(path),sigma_m=.4,include_profile=True)
        values=np.sort(abs(np.array(m['profile']['curvature_inv_m'])))
        axes[0].plot(values,np.arange(len(values))/len(values),label=name)
        angles=np.sort(m['corner_angles_deg']['values'])
        axes[1].plot(angles,np.arange(1,len(angles)+1)/len(angles),marker='.',label=name)
    axes[0].set(xlabel='|curvature| [1/m]',ylabel='arc-sample cumulative fraction',title='σ=0.4 m coordinate geometry')
    axes[1].set(xlabel='significant corner angle [degrees]',ylabel='corner cumulative fraction')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(folder/'distributions.png',dpi=160);fig.savefig(folder/'distributions.svg',metadata={'Date':None});plt.close(fig)
    labels=['Budapest','Hockenheim']+[e['variant'] for e in manifest['accepted']]
    distances=np.zeros((len(labels),len(labels)))
    for pair in report['layout_shape_comparison']['pairs']:
        i,j=labels.index(pair['first']),labels.index(pair['second'])
        distances[i,j]=distances[j,i]=pair['normalized_rms_distance']
    fig,ax=plt.subplots(figsize=(11,10),constrained_layout=True)
    im=ax.imshow(distances,cmap='viridis',vmin=0)
    ax.set_xticks(range(len(labels)),labels,rotation=65,ha='right');ax.set_yticks(range(len(labels)),labels)
    ax.set_title('Normalized coordinate shape distances; rotation, scale, seam, reversal, reflection removed')
    fig.colorbar(im,ax=ax,label='minimum normalized coordinate RMS distance')
    fig.savefig(folder/'layout_diversity.png',dpi=160);fig.savefig(folder/'layout_diversity.svg',metadata={'Date':None});plt.close(fig)
    print(folder)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot',type=Path,default=ROOT/'examples/phase3b_pilot')
    p.add_argument('--marl-race-root',type=Path,default=ROOT.parent/'marl_race')
    p.add_argument('--analysis',type=Path,default=ROOT/'docs/phase3b_comparison.json')
    a=p.parse_args();plot(a.pilot,a.marl_race_root,a.analysis)
