#!/usr/bin/env python3
"""Small opt-in Phase 5.1 geometry pilot; existing offline validation and replay."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from map_editor.geometry import GeometryError
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.research_design import experimental_spec
from map_editor.services.research_tracks import prepare_research,publish_research
from plot_extended_pilot import assets,geometry,COLORS

CASES=[('hairpin','short',0),('hairpin','medium',1),('hairpin','long',2),
       ('sweeper','medium',0),('sweeper','long',1),('chicane','short',0),
       ('s_curve','medium',0),('composite','medium',0),('composite','medium',1),('composite','long',2)]


def measured(entry,metadata):
    s=entry['statistics'];target=entry['target_family']
    primary=[a for a in metadata['maneuvers'] if a['requested']['composition_role']=='primary']
    practice=[a for a in primary if a['type']==target] if target else primary
    radii=[a['measured']['minimum_radius_m'] for a in practice if a['type']!='straight']
    counts=dict(Counter(a['type'] for a in primary))
    return dict(name=entry['name'],family=target or 'composite',length_m=s['raw_lap_length_m'],
        maneuver_counts=counts,target_count=len(practice),target_frequency_per_100m=100*len(practice)/s['raw_lap_length_m'],
        target_radius_min_m=min(radii) if radii else None,target_radius_max_m=max(radii) if radii else None,
        target_window_minimum_radii_m=radii,
        minimum_sustained_radius_m=s['minimum_sustained_radius_m'],p50_curvature_inv_m=s['curvature_abs_percentiles_inv_m']['50'],
        p95_curvature_inv_m=s['p95_curvature_inv_m'],maximum_curvature_inv_m=s['maximum_curvature_inv_m'],
        target_exposure=s['target_exposure_fraction'],primary_family_exposure=s['primary_family_exposure_fractions'],
        active_curvature_exposure=s['active_curvature_fraction'],target_active_exposure=s['primary_active_curvature_exposure'].get(target) if target else None,
        supporting_fraction=s['supporting_fraction'],significant_turn_count=s['corner_count'],
        closure='passed',clearance='passed_at_sampled_poses',physical_drivability='unassessed')


def plots(root,manifest,originals):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import numpy as np
    plt.rcParams.update({'font.size':8,'svg.hashsalt':'phase5_1.tuning'})
    loaded={e['name']:assets(root,e) for e in manifest['accepted']}
    old={e['slot_id']:assets(ROOT/'datasets/phase5_v1',e) for e in originals}
    span=max(np.ptp(a[1],axis=0).max() for a in [*loaded.values(),*old.values()])*1.12
    folder=root/'plots';folder.mkdir()
    def save(fig,name):
        fig.savefig(folder/(name+'.png'),dpi=145);fig.savefig(folder/(name+'.svg'),metadata={'Date':None});plt.close(fig)
    fig,axes=plt.subplots(2,5,figsize=(22,10),constrained_layout=True)
    by_name={e['name']:e for e in manifest['accepted']}
    for ax,(family,scale,variant) in zip(axes.flat,CASES):
        name=f'{family}_{variant+1:02d}';e=by_name.get(name)
        if e:
            geometry(ax,*loaded[name],span);s=e['statistics'];count=e['comparison']['target_count']
            ax.set_title(f"{name} · {s['raw_lap_length_m']:.0f} m\n{count} primary target windows; {s['corner_count']} significant turns")
        else:ax.text(.5,.5,name+'\nNo accepted candidate\nBounded geometry/clearance failure',ha='center',va='center',transform=ax.transAxes);ax.set_axis_off()
    fig.suptitle(f"Phase 5.1: {len(manifest['accepted'])}/10 accepted · all panels use {span:.0f} m × {span:.0f} m axes",fontsize=15)
    fig.legend(handles=[Patch(color=c,label=f) for f,c in COLORS.items() if f in ('hairpin','sweeper','chicane','s_curve','corner','straight','transition')],loc='lower center',ncol=7)
    save(fig,'overview')
    for e in manifest['accepted']:
        fig,ax=plt.subplots(figsize=(7,7),constrained_layout=True);geometry(ax,*loaded[e['name']],span)
        ax.set_title(e['name']+' · measured geometry; physical drivability unassessed');save(fig,e['name'])
    fig,axes=plt.subplots(2,len(originals),figsize=(4*len(originals),9),squeeze=False,constrained_layout=True)
    for j,original in enumerate(originals):
        family=original['target_family'] or 'composite'
        geometry(axes[0,j],*old[original['slot_id']],span);axes[0,j].set_title('Phase 5 '+family+'\n'+f"{original['statistics']['raw_lap_length_m']:.0f} m")
        candidates=[e for e in manifest['accepted'] if (e['target_family'] or 'composite')==family]
        if candidates:
            e=min(candidates,key=lambda e:abs(e['statistics']['raw_lap_length_m']-original['statistics']['raw_lap_length_m']))
            geometry(axes[1,j],*loaded[e['name']],span);axes[1,j].set_title('Pilot '+e['name']+'\n'+f"{e['statistics']['raw_lap_length_m']:.0f} m")
        else:axes[1,j].text(.5,.5,'No valid replacement\nOriginal preserved',ha='center',transform=axes[1,j].transAxes);axes[1,j].set_axis_off()
    fig.suptitle(f'Original vs pilot · identical {span:.0f} m metric axes; lengths shown, not matched experiments',fontsize=14);save(fig,'original_comparison')


def generate(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json')
    manifest=dict(dataset_id='phase5_1_pilot',requested=10,complete=False,accepted=[],rejected=[],missing=[],scope='offline experimental parameter tuning; no formal dataset replacement')
    for index,(family,scale,variant) in enumerate(CASES):
        name=f'{family}_{variant+1:02d}';accepted=False
        for attempt in range(1,5):
            spec=experimental_spec(family,scale,variant,51000+index,vehicle,attempt)
            try:
                prepared=prepare_research(spec);bundle=publish_research(spec,root/'tracks'/name,prepared=prepared)
                entry=dict(name=name,target_family=spec.target_family,scale=scale,track_id=spec.track_id,
                    map=str(bundle.relative_to(root)),metadata=str((bundle.parent/(spec.track_id+'_metadata.json')).relative_to(root)),
                    recipe=str((bundle.parent/(spec.track_id+'_generation.yaml')).relative_to(root)),attempt=attempt,statistics=prepared.statistics)
                entry['comparison']=measured(entry,prepared.metadata);manifest['accepted'].append(entry);accepted=True
                print(f'Accepted {name} attempt {attempt}',flush=True);break
            except (GeometryError,ValueError) as exc:
                manifest['rejected'].append(dict(name=name,attempt=attempt,seed=spec.seed,native_recipe=spec.recipe(),reason=str(exc),layout_attempts=getattr(exc,'attempts',[])))
                print(f'Rejected {name} attempt {attempt}: {exc}',flush=True)
        if not accepted:manifest['missing'].append(name)
        (root/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    manifest['complete']=len(manifest['accepted'])==10
    originals=json.loads((ROOT/'datasets/phase5_v1/manifest.json').read_text())['accepted']
    selected=[]
    for family in ('hairpin','sweeper','chicane','s_curve',None):
        matching=[e for e in originals if e['target_family']==family]
        original=min(matching,key=lambda e:abs(e['statistics']['raw_lap_length_m']-(210 if family=='hairpin' else 170)))
        selected.append(original)
    comparisons=[]
    for e in selected:
        m=json.loads((ROOT/'datasets/phase5_v1'/e['metadata']).read_text());row=dict(e,name='original_'+e['slot_id'])
        comparisons.append(measured(row,m))
    (root/'original_comparison.json').write_text(json.dumps(comparisons,indent=2,allow_nan=False)+'\n')
    rows=[e['comparison'] for e in manifest['accepted']]
    (root/'comparison.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
    with (root/'comparison.csv').open('w',newline='') as handle:
        if rows:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    plots(root,manifest,selected)
    print(f"Pilot {len(manifest['accepted'])}/10; {len(manifest['rejected'])} rejected candidates",flush=True)
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'generated_maps/phase5_1_pilot')
    generate(parser.parse_args().output)
