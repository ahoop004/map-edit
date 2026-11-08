#!/usr/bin/env python3
"""Scientific galleries and physical/joint/split distributions for the formal dataset."""
import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from plot_extended_pilot import assets,geometry,COLORS
SPLIT_COLORS={'train':'#277aa5','validation':'#c37b24','test':'#b34349'}


def plot(root,analysis,output=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    plt.rcParams.update({'font.size':7,'svg.hashsalt':'phase5.research_dataset.v1'})
    root=Path(root);report=json.loads((root/'manifest.json').read_text());stats=json.loads(Path(analysis).read_text())
    entries=report['accepted'];loaded={e['slot_id']:assets(root,e) for e in entries}
    folder=Path(output) if output is not None else root/'plots';folder.mkdir(parents=True,exist_ok=False)
    span=max(np.ptp(loaded[e['slot_id']][1],axis=0).max() for e in entries)*1.12
    def save(fig,name):
        fig.savefig(folder/(name+'.png'),dpi=150);fig.savefig(folder/(name+'.svg'),metadata={'Date':None});plt.close(fig)
    def gallery(selected,name,title,cols=6):
        rows=math.ceil(len(selected)/cols);fig,axes=plt.subplots(rows,cols,figsize=(cols*3.1,rows*3.15),squeeze=False,constrained_layout=True)
        for ax,e in zip(axes.flat,selected):
            m,xy,p,w=loaded[e['slot_id']];geometry(ax,m,xy,p,w,span)
            ax.set_title(f"{e['slot_id'].replace('specialist_','').replace('composite_','C')}\n{e['statistics']['raw_lap_length_m']:.1f} m; {e['scale']}; "+(e['target_family'] or f"{e['complexity']} families"),fontsize=7)
            ax.set_xlabel('x [m]',fontsize=6);ax.set_ylabel('y [m]',fontsize=6);ax.tick_params(labelsize=5)
            for spine in ax.spines.values():spine.set_edgecolor(SPLIT_COLORS[e['split']])
        for ax in list(axes.flat)[len(selected):]:ax.axis('off')
        fig.suptitle(f'{title}\nIdentical {span:.0f} m × {span:.0f} m axes in every gallery; centered, never size-normalized',fontsize=12)
        fig.legend(handles=[Patch(color=color,label=split) for split,color in SPLIT_COLORS.items()],loc='lower center',ncol=3)
        save(fig,name)
    gallery(entries,'overview','Formal 60 independent centerline layouts',6)
    for family in ('straight','hairpin','sweeper','chicane','s_curve'):
        selected=sorted((e for e in entries if e['target_family']==family),key=lambda e:e['statistics']['raw_lap_length_m'])
        gallery(selected,'specialist_'+family,f'{family} specialists — measured target-family dominance',3)
    composites=sorted((e for e in entries if e['generation_mode']=='composite'),key=lambda e:(e['complexity'],e['statistics']['raw_lap_length_m']))
    gallery(composites,'composites','Composites ordered by measured family complexity, then physical length',5)
    for scale in ('short','medium','long'):
        gallery([e for e in entries if e['scale']==scale],'scale_'+scale,scale.title()+' circuits — physical scale retained',5)
    for split in SPLIT_COLORS:gallery([e for e in entries if e['split']==split],'split_'+split,split.title()+' split',5)
    fig,axes=plt.subplots(2,3,figsize=(15,9),constrained_layout=True)
    fields=[('raw_lap_length_m','Lap length [m]'),('p95_curvature_inv_m','p95 |κ| [1/m]'),('corner_density_per_100m','Significant turns / 100 m'),
        ('minimum_sustained_radius_m','Minimum sustained radius [m]'),('longest_straight_m','Longest near-straight [m]'),('curvature_reversals','Cyclic curvature reversals')]
    for ax,(field,label) in zip(axes.flat,fields):
        groups=[[e['statistics'][field] for e in entries if e['split']==split] for split in SPLIT_COLORS]
        lo=min(min(g) for g in groups);hi=max(max(g) for g in groups);bins=np.linspace(lo,hi,13)
        for split,g in zip(SPLIT_COLORS,groups):ax.hist(g,bins=bins,histtype='step',lw=1.5,label=split,color=SPLIT_COLORS[split],density=True)
        ax.set(xlabel=label,ylabel='density');ax.grid(alpha=.2)
    axes[0,0].legend();fig.suptitle('Physical geometric distributions by split; no driving-difficulty labels',fontsize=13);save(fig,'geometric_distributions')
    fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    for ax,(field,label) in zip(axes.flat,[('mean_width_m','Mean corridor width [m]'),('minimum_width_m','Minimum vector normal width [m]'),('width_std_m','Width standard deviation [m]'),('minimum_raster_width_m','Minimum raster normal width [m]')]):
        ax.boxplot([[e['statistics'][field] for e in entries if e['split']==split] for split in SPLIT_COLORS],tick_labels=list(SPLIT_COLORS))
        for x,split in enumerate(SPLIT_COLORS,1):
            selected=[e['statistics'][field] for e in entries if e['split']==split]
            ax.scatter(np.full(len(selected),x)+np.linspace(-.12,.12,len(selected)),selected,color=SPLIT_COLORS[split],s=10,alpha=.7)
        ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Track-width distributions — geometry independently validated after rasterization',fontsize=12);save(fig,'width_distributions')
    fields=['straight','hairpin','sweeper','chicane','s_curve','corner','kink','compound_corner','transition']
    exposures=np.array([[e['statistics']['family_exposure_fractions'].get(f,0) for f in fields] for e in entries])
    fig,ax=plt.subplots(figsize=(12,20),constrained_layout=True);im=ax.imshow(exposures,aspect='auto',vmin=0,vmax=1,cmap='YlGnBu')
    ax.set_xticks(range(len(fields)),fields,rotation=30,ha='right');ax.set_yticks(range(len(entries)),[e['slot_id'] for e in entries],fontsize=6)
    ax.axhline(39.5,color='black');ax.axhline(47.5,color='black');ax.set_title('Arc-length family exposure; transition includes explicit supporting geometry')
    fig.colorbar(im,ax=ax,label='fraction of lap');save(fig,'maneuver_exposure')
    names=[e['slot_id'] for e in entries];matrix=np.zeros((60,60))
    for pair in stats['pairwise_similarity']:
        i,j=names.index(pair['first']),names.index(pair['second']);matrix[i,j]=matrix[j,i]=pair['normalized_shape_distance']
    fig,ax=plt.subplots(figsize=(12,11),constrained_layout=True);im=ax.imshow(matrix,cmap='viridis',vmin=0)
    ticks=np.arange(0,60,2);ax.set_xticks(ticks,[names[i] for i in ticks],rotation=90,fontsize=5);ax.set_yticks(ticks,[names[i] for i in ticks],fontsize=5)
    for v in (39.5,47.5):ax.axhline(v,color='white',lw=.8);ax.axvline(v,color='white',lw=.8)
    ax.set_title('Normalized shape distance; low values alone do not imply physical near-duplication')
    fig.colorbar(im,ax=ax,label='RMS distance after rigid motion, reflection, reversal, seam and scale removal');save(fig,'similarity_matrix')
    fig,axes=plt.subplots(1,3,figsize=(16,5),constrained_layout=True)
    for split in SPLIT_COLORS:
        selected=[e for e in entries if e['split']==split];color=SPLIT_COLORS[split]
        axes[0].scatter([e['statistics']['raw_lap_length_m'] for e in selected],[e['statistics']['corner_count'] for e in selected],c=color,label=split,s=25)
        axes[1].scatter([e['statistics']['minimum_sustained_radius_m'] for e in selected],[e['statistics']['mean_width_m'] for e in selected],c=color,label=split,s=25)
    axes[0].set(xlabel='Lap length [m]',ylabel='Significant turn count');axes[0].legend();axes[1].set(xlabel='Minimum sustained radius [m]',ylabel='Mean width [m]')
    families=['straight','hairpin','sweeper','chicane','s_curve','composite']
    for i,f in enumerate(families):
        selected=[e for e in entries if (e['target_family'] or 'composite')==f]
        axes[2].scatter(np.full(len(selected),i)+np.linspace(-.15,.15,len(selected)),[e['statistics']['p95_curvature_inv_m'] for e in selected],c=[SPLIT_COLORS[e['split']] for e in selected],s=20)
    axes[2].set_xticks(range(len(families)),families,rotation=25);axes[2].set_ylabel('p95 |κ| [1/m]')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Important joint relationships: length/corners, radius/width, family/geometric demand',fontsize=12);save(fig,'joint_relationships')
    fig,axes=plt.subplots(2,3,figsize=(14,8),constrained_layout=True)
    for ax,(field,label) in zip(axes.flat,[('primary_coverage','Primary exposure'),('active_curvature_fraction','Active-curvature fraction'),('left_turn_fraction','Left fraction of absolute turning'),('symmetry_error_m','Halfturn asymmetry [m]'),('p95_curvature_inv_m','p95 |κ| [1/m]'),('raw_lap_length_m','Lap length [m]')]):
        ax.boxplot([[e['statistics'][field] for e in entries if e['split']==s] for s in SPLIT_COLORS],tick_labels=list(SPLIT_COLORS))
        ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Train / validation / test marginal comparisons; finite samples and fixed quotas',fontsize=12);save(fig,'split_comparisons')
    fig,axes=plt.subplots(3,4,figsize=(16,10),constrained_layout=True)
    for row,scale in enumerate(('short','medium','long')):
        for col,family in enumerate(('straight','hairpin','sweeper',None)):
            e=next(e for e in entries if e['scale']==scale and e['target_family']==family)
            profile=loaded[e['slot_id']][2];axes[row,col].plot(profile['s_m'],profile['curvature_inv_m'],lw=.8)
            axes[row,col].set(xlim=(0,450),ylim=(-.8,.8),xlabel='physical arc position [m]',ylabel='κ [1/m]',title=f'{scale}: {family or "composite"}\n{e["slot_id"]}',)
            axes[row,col].grid(alpha=.2)
    fig.suptitle('Representative signed curvature profiles — same physical axes in every panel',fontsize=13);save(fig,'curvature_examples')
    if 'selection_plan_id' in report:
        fig,axes=plt.subplots(2,2,figsize=(16,12),constrained_layout=True)
        repetitions=[e['statistics']['repetition_fraction'] for e in composites]
        active=[e['statistics']['active_curvature_fraction'] for e in composites]
        axes[0,0].hist(repetitions,bins=np.linspace(0,1,16),color='#56793e')
        axes[0,0].axvline(.65,color='black',ls='--',label='low-repetition target .65');axes[0,0].axvline(.95,color='#b34349',ls=':',label='high-repetition .95')
        axes[0,0].set(xlabel='Periodic curvature repetition',ylabel='Composite tracks');axes[0,0].legend()
        axes[0,1].hist(active,bins=np.linspace(0,1,16),color='#24769c')
        axes[0,1].axvline(.25,color='#b34349',ls='--',label='review threshold .25');axes[0,1].legend()
        axes[0,1].set(xlabel='Active-curvature fraction',ylabel='Composite tracks')
        axes[1,0].scatter([e['statistics']['primary_coverage'] for e in composites],active,c=repetitions,cmap='viridis',vmin=0,vmax=1)
        axes[1,0].set(xlabel='Primary maneuver annotation coverage',ylabel='Active-curvature exposure',xlim=(0,1),ylim=(0,1))
        y=np.arange(len(composites));axes[1,1].barh(y-.18,active,.36,label='active curvature',color='#24769c')
        axes[1,1].barh(y+.18,repetitions,.36,label='repetition',color='#d48529')
        axes[1,1].set_yticks(y,[e['slot_id'] for e in composites],fontsize=5);axes[1,1].set_xlim(0,1);axes[1,1].legend()
        fig.suptitle('V2 composites: repetition and active curvature are separate from primary annotation coverage',fontsize=13)
        save(fig,'repetition_active_curvature')
    print(folder)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('--analysis',type=Path,default=ROOT/'docs/phase5_analysis.json')
    p.add_argument('--output',type=Path,help='Fresh plot directory (default: DATASET/plots)')
    a=p.parse_args();plot(a.dataset,a.analysis,a.output)
