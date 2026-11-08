#!/usr/bin/env python3
"""Offline scientific geometry, curvature, diversity and matched width figures."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.technical_analysis import analyze_geometry,SCALES_M
from map_editor.services.composite_statistics import contains
COLORS=dict(corner='#bd4738',kink='#b68d26',compound_corner='#91468c',hairpin='#632b77',
    straight='#24769c',sweeper='#56793e',chicane='#6b6f9e',s_curve='#d48529',transition='#999999')


def assets(root,entry):
    metadata=json.loads((root/entry['metadata']).read_text());folder=(root/entry['map']).parent
    xy=np.loadtxt(folder/metadata['artifacts']['centerline'],delimiter=',',skiprows=1,usecols=(0,1))
    profile=np.genfromtxt(folder/metadata['artifacts']['track_profile'],delimiter=',',names=True)
    walls={}
    with (folder/metadata['artifacts']['walls']).open() as handle:
        for r in csv.DictReader(handle):
            x,y=float(r['x']),float(r['y'])
            if math.isfinite(x) and math.isfinite(y):walls.setdefault(r['wall_id'],[]).append((x,y))
    return metadata,xy,profile,[np.array(p) for p in walls.values()]


def geometry(ax,metadata,xy,profile,walls,span):
    from matplotlib.collections import LineCollection
    center=(xy.max(axis=0)+xy.min(axis=0))/2
    for wall in walls:
        p=np.vstack([wall,wall[0]])-center;ax.plot(p[:,0],p[:,1],color='.67',lw=.65)
    p=np.vstack([xy,xy[0]])-center
    colors=[COLORS[next(a['type'] for a in metadata['maneuvers'] if contains(a,float(s)))] for s in profile['s_m']]
    ax.add_collection(LineCollection(np.stack([p[:-1],p[1:]],axis=1),colors=colors,linewidths=1.1))
    row=profile[0];n=np.array([-math.sin(row['heading_rad']),math.cos(row['heading_rad'])])
    finish=np.array([xy[0]+row['left_width_m']*n,xy[0]-row['right_width_m']*n])-center
    ax.plot(finish[:,0],finish[:,1],color='black',lw=1.5)
    ax.set(xlim=(-span/2,span/2),ylim=(-span/2,span/2),xlabel='x [m], centered',ylabel='y [m], centered')
    ax.set_aspect('equal');ax.grid(alpha=.18)


def save(fig,folder,name):
    fig.savefig(folder/(name+'.png'),dpi=155)
    fig.savefig(folder/(name+'.svg'),metadata={'Date':None})


def plot(root,analysis):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    matplotlib.rcParams['svg.hashsalt']='phase4b.extended_geometry.v1'
    plt.rcParams['font.size']=8
    root=Path(root);report=json.loads((root/'manifest.json').read_text());comparison=json.loads(Path(analysis).read_text())
    entries=report['accepted'];loaded={e['track_id']:assets(root,e) for e in entries}
    span=max(np.ptp(loaded[e['track_id']][1],axis=0).max() for e in entries)*1.13
    folder=root/'plots';folder.mkdir(exist_ok=True)
    fig,axes=plt.subplots(4,3,figsize=(16,20),constrained_layout=True)
    for ax,e in zip(axes.flat,entries):
        metadata,xy,profile,walls=loaded[e['track_id']];geometry(ax,metadata,xy,profile,walls,span)
        ax.set_title(f"{e['variant']}\n{e['statistics']['raw_lap_length_m']:.1f} m; {e['statistics']['corner_count']} significant turns")
    fig.suptitle(f'Phase 4B offline geometry — shared {span:.0f} m × {span:.0f} m axes; width pairs share centerlines',fontsize=14)
    fig.legend(handles=[Patch(color=v,label=k) for k,v in COLORS.items() if k in ('corner','kink','compound_corner','straight','transition')],loc='lower center',ncol=5)
    save(fig,folder,'overview');plt.close(fig)
    for e in entries:
        metadata,xy,profile,walls=loaded[e['track_id']];stats=e['statistics']
        fig,axes=plt.subplots(2,2,figsize=(13,10),constrained_layout=True)
        geometry(axes[0,0],metadata,xy,profile,walls,span)
        axes[0,0].set_title('Same metric scale across the pilot')
        for sigma in (0.,.4,.8):
            measured=analyze_geometry(xy,sigma_m=sigma,include_profile=True)
            axes[0,1].plot(measured['profile']['s_m'],measured['profile']['curvature_inv_m'],lw=.8,label=f'σ={sigma:g} m')
        axes[0,1].set(xlabel='source-resampled arc position [m]',ylabel='curvature [1/m]',title='Periodic coordinate geometry');axes[0,1].legend()
        axes[1,0].plot(profile['s_m'],profile['width_m'],label='total normal width')
        axes[1,0].plot(profile['s_m'],profile['left_width_m'],label='left offset',lw=.8)
        axes[1,0].plot(profile['s_m'],profile['right_width_m'],label='right offset',lw=.8)
        axes[1,0].axhline(stats['minimum_raster_width_m'],color='black',ls='--',lw=.7,label='minimum raster normal width')
        axes[1,0].set(xlabel='exported arc position [m]',ylabel='width / side offset [m]',title='Widths measured from final vector and raster geometry');axes[1,0].legend(fontsize=7)
        exposure=stats['family_exposure_fractions'];labels=list(exposure)
        axes[1,1].bar(labels,[100*exposure[k] for k in labels],color=[COLORS[k] for k in labels]);axes[1,1].tick_params(axis='x',rotation=25)
        axes[1,1].set(ylabel='lap exposure [%]',title=f"Primary {stats['primary_coverage']:.1%}; supporting {stats['supporting_fraction']:.1%}")
        fig.suptitle(f"{e['variant']}: {stats['raw_lap_length_m']:.1f} m; geometric acceptance only; no physical drivability rating",fontsize=12)
        save(fig,folder,e['variant']);plt.close(fig)
    for pair in report['matched_pairs']:
        a,b=pair['tracks'];ma,xa,pa,wa=loaded[a];mb,xb,pb,wb=loaded[b]
        fig,axes=plt.subplots(2,3,figsize=(16,10),constrained_layout=True)
        geometry(axes[0,0],ma,xa,pa,wa,span);axes[0,0].set_title('Uniform corridor')
        geometry(axes[0,1],mb,xb,pb,wb,span);axes[0,1].set_title('Variable independent side offsets')
        k=int(np.argmin(pb['width_m']));center=xb[k]
        for walls,color,label in ((wa,'#24769c','uniform walls'),(wb,'#bd4738','variable walls')):
            for j,wall in enumerate(walls):
                p=np.vstack([wall,wall[0]]);axes[0,2].plot(p[:,0],p[:,1],color=color,lw=1.2,label=label if j==0 else None)
        axes[0,2].plot(xa[:,0],xa[:,1],color='black',lw=.7,label='identical centerline')
        axes[0,2].set(xlim=(center[0]-6,center[0]+6),ylim=(center[1]-6,center[1]+6),xlabel='x [m]',ylabel='y [m]',title='12 m × 12 m bottleneck detail')
        axes[0,2].set_aspect('equal');axes[0,2].legend(fontsize=7)
        axes[1,0].plot(pa['s_m'],pa['curvature_inv_m'],label='uniform κ',lw=1.4)
        axes[1,0].plot(pb['s_m'],pb['curvature_inv_m'],label='variable κ',lw=.8,ls='--')
        axes[1,0].set(xlabel='arc position [m]',ylabel='curvature [1/m]',title='Same centerline and primary radii');axes[1,0].legend()
        axes[1,1].plot(pa['s_m'],pa['width_m'],label='uniform total')
        axes[1,1].plot(pb['s_m'],pb['width_m'],label='variable total')
        axes[1,1].plot(pb['s_m'],pb['left_width_m'],label='variable left',lw=.8)
        axes[1,1].plot(pb['s_m'],pb['right_width_m'],label='variable right',lw=.8)
        axes[1,1].set(xlabel='arc position [m]',ylabel='width / offset [m]');axes[1,1].legend(fontsize=7)
        fields=['minimum_width_m','mean_width_m','maximum_width_m','minimum_raster_width_m']
        sa=ma['provenance']['extended_statistics'];sb=mb['provenance']['extended_statistics'];x=np.arange(4)
        axes[1,2].bar(x-.18,[sa[k] for k in fields],.36,label='uniform');axes[1,2].bar(x+.18,[sb[k] for k in fields],.36,label='variable')
        axes[1,2].set_xticks(x,['min vector','mean vector','max vector','min raster'],rotation=25)
        axes[1,2].set(ylabel='meters',title='Both corridors independently validated');axes[1,2].legend()
        fig.suptitle(f"{pair['group']}: centerline CSV is byte-identical; supporting geometry unchanged",fontsize=13)
        save(fig,folder,pair['group']);plt.close(fig)
    fig,axes=plt.subplots(2,4,figsize=(20,12),constrained_layout=True)
    fields=[('raw_lap_length_m','Lap length [m]'),('corner_count','Significant turns'),('p95_curvature_inv_m','95th percentile |κ| [1/m]'),
        ('curvature_reversals_per_100m','Reversals / 100 m'),('supporting_fraction','Supporting exposure fraction'),
        ('symmetry_error_m','Halfturn residual [m]'),('minimum_raster_width_m','Minimum raster normal width [m]'),('longest_straight_m','Longest near-straight [m]')]
    for ax,(field,label) in zip(axes.flat,fields):
        ax.barh([e['variant'] for e in entries],[e['statistics'][field] for e in entries],color=['#b84b3a' if e['category']=='long_technical' else '#347b9c' if e['category']=='long_irregular_mixed' else '#69854d' for e in entries])
        ax.invert_yaxis();ax.set_xlabel(label);ax.grid(axis='x',alpha=.2)
    fig.suptitle('Phase 4B measured diversity; geometry and width are separate dimensions',fontsize=14)
    save(fig,folder,'diversity_statistics');plt.close(fig)
    names=[e['variant'] for e in entries];distances=np.zeros((len(names),len(names)))
    for pair in comparison['shape_pairs']:
        i,j=names.index(pair['first']),names.index(pair['second']);distances[i,j]=distances[j,i]=pair['normalized_shape_distance']
    fig,ax=plt.subplots(figsize=(11,9),constrained_layout=True);im=ax.imshow(distances,cmap='viridis',vmin=0)
    ax.set_xticks(range(len(names)),names,rotation=65,ha='right');ax.set_yticks(range(len(names)),names)
    ax.set_title('Normalized shape distance: expected zeros within matched width pairs')
    fig.colorbar(im,ax=ax,label='coordinate RMS after translation, scale, rotation, seam, reflection and reversal removal')
    save(fig,folder,'layout_diversity');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    selected=comparison['tracks'][::3]
    for ax,(field,label) in zip(axes.flat,[('p95_curvature_inv_m','p95 |κ| [1/m]'),('maximum_curvature_rate_inv_m2','peak |dκ/ds| [1/m²]'),('corner_count','significant turns'),('minimum_sustained_radius_m','sustained minimum radius [m]')]):
        for track in selected:ax.plot(SCALES_M,[m[field] for m in track['scales']],marker='.',label=track['variant'])
        ax.set(xlabel='Periodic Gaussian sigma [m]',ylabel=label);ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=7);fig.suptitle('Spatial-scale sensitivity of local geometry; all analysis remains offline',fontsize=13)
    save(fig,folder,'scale_sensitivity');plt.close(fig)
    print(folder)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot',type=Path,default=ROOT/'examples/phase4b_pilot')
    parser.add_argument('--analysis',type=Path,default=ROOT/'docs/phase4b_analysis.json')
    args=parser.parse_args();plot(args.pilot,args.analysis)
