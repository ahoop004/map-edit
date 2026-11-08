#!/usr/bin/env python3
"""Bounded Phase 5.2 pilot and metric-axis comparison; never a dataset release."""
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
from map_editor.services.dataset_spec import default_dataset_spec
from map_editor.services.research_design import refined_spec
from map_editor.services.research_tracks import prepare_research,publish_research
from generate_research_tuning_pilot import measured,CASES as OLD_CASES
from plot_extended_pilot import assets,geometry,COLORS

CASES=OLD_CASES


def write_json(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def statistics(entry,metadata):
    row=measured(entry,metadata);s=entry['statistics']
    native=metadata['requested']['research_specification']
    requested=[r for r in native['inventory'] if not entry['target_family'] or r['family']==entry['target_family']]
    radii=[]
    for r in requested:
        p=r['parameters'];radii.extend(p.get('radii_m',[]) or ([p['radius_m']] if 'radius_m' in p else []))
        if p.get('end_radius_m') is not None:radii.append(p['end_radius_m'])
    row.update(primary_coverage=s['primary_coverage'],target_radii_m=radii,
        curvature_percentiles_inv_m=s['curvature_abs_percentiles_inv_m'],
        primary_active_curvature_exposure=s['primary_active_curvature_exposure'],
        layout_topology=metadata['provenance']['layout_solution']['topology'],
        curvature_reversals_per_100m=s['curvature_reversals_per_100m'],repetition_fraction=s['repetition_fraction'],
        primary_family_switch_count=s['primary_family_switch_count'],
        design_version=native.get('design_version','research_design.v1'),
        geometry_validation='passed',clearance='passed_at_sampled_poses')
    return row


def report(root,manifest,baseline):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import numpy as np
    old_manifest=json.loads((baseline/'manifest.json').read_text())
    # Allocation/configuration only: this does not generate a formal dataset.
    write_json(root/'v2_design_contract.json',default_dataset_spec(design_version='research_design.v2').recipe())
    old={e['name']:e for e in old_manifest['accepted']}
    accepted={e['name']:e for e in manifest['accepted']}
    loaded={name:assets(root,e) for name,e in accepted.items()}
    previous={name:assets(baseline,e) for name,e in old.items()}
    span=max(np.ptp(a[1],axis=0).max() for a in [*loaded.values(),*previous.values()])*1.12
    folder=root/'plots';folder.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':8,'svg.hashsalt':'phase5_2.pilot'})
    def save(fig,name):
        fig.savefig(folder/(name+'.png'),dpi=145)
        fig.savefig(folder/(name+'.svg'),metadata={'Date':None});plt.close(fig)
    fig,axes=plt.subplots(2,5,figsize=(23,11),constrained_layout=True)
    for ax,(family,scale,variant) in zip(axes.flat,CASES):
        name=f'{family}_{variant+1:02d}'
        if name in accepted:
            e=accepted[name];s=e['statistics'];geometry(ax,*loaded[name],span)
            ax.set_title(f"{name} · {s['raw_lap_length_m']:.0f} m\n{e['comparison']['layout_topology']}\nprimary {s['primary_coverage']:.0%}; active {s['active_curvature_fraction']:.0%}")
        else:ax.text(.5,.5,name+'\nNo accepted candidate\nSee retained failures',ha='center',transform=ax.transAxes);ax.set_axis_off()
    fig.suptitle(f"Phase 5.2 · {len(accepted)}/10 accepted · common {span:.0f} m × {span:.0f} m metric axes",fontsize=15)
    fig.legend(handles=[Patch(color=COLORS[f],label=f) for f in ('hairpin','sweeper','chicane','s_curve','corner','straight','transition')],loc='lower center',ncol=7)
    save(fig,'overview')
    # Ten matched panels keep the comparison readable at common metric scale.
    for start,label in ((0,'specialists_a'),(5,'specialists_b_and_composites')):
        fig,axes=plt.subplots(2,5,figsize=(23,11),constrained_layout=True)
        for j,(family,scale,variant) in enumerate(CASES[start:start+5]):
            name=f'{family}_{variant+1:02d}'
            for i,(source,entries,prefix) in enumerate(((previous,old,'5.1'),(loaded,accepted,'5.2'))):
                ax=axes[i,j]
                if name in source:
                    e=entries[name];s=e['statistics'];geometry(ax,*source[name],span)
                    ax.set_title(f"Phase {prefix} {name} · {s['raw_lap_length_m']:.0f} m\nprimary {s['primary_coverage']:.0%}; active {s['active_curvature_fraction']:.0%}")
                else:ax.text(.5,.5,'No accepted candidate',ha='center',transform=ax.transAxes);ax.set_axis_off()
        fig.suptitle(f'Phase 5.1 vs 5.2 · common {span:.0f} m metric axes; lengths shown, not matched experiments',fontsize=14)
        save(fig,'phase5_1_comparison_'+label)
    old_rows=[statistics(e,json.loads((baseline/e['metadata']).read_text())) for e in old.values()]
    rows=[e['comparison'] for e in manifest['accepted']]
    pairs=[]
    for row in rows:
        before=next(r for r in old_rows if r['name']==row['name'])
        fields=('length_m','primary_coverage','supporting_fraction','active_curvature_exposure','significant_turn_count',
                'target_frequency_per_100m','curvature_reversals_per_100m','repetition_fraction','primary_family_switch_count')
        pairs.append(dict(name=row['name'],before={k:before[k] for k in fields},after={k:row[k] for k in fields},
                          before_topology=before['layout_topology'],after_topology=row['layout_topology']))
    topologies=dict(Counter(row['layout_topology'] for row in rows))
    layout_records=[r for e in manifest['rejected'] for r in e.get('layout_attempts',[])]
    for e in manifest['accepted']:
        meta=json.loads((root/e['metadata']).read_text());layout_records.extend(meta['provenance']['layout_attempts'])
    summary=dict(accepted=len(rows),rejected=len(manifest['rejected']),missing=manifest['missing'],
        distinct_topology_strategies=len(topologies),topology_counts=topologies,
        layout_attempt_status_counts=dict(Counter(r['status'] for r in layout_records)),
        composite_coverage=[{k:r[k] for k in ('name','length_m','primary_coverage','supporting_fraction','active_curvature_exposure','maneuver_counts')} for r in rows if r['family']=='composite'],
        common_axes_span_m=span,comparison=pairs,
        native_replay=dict(tracks=len(rows),status='passed',byte_identical=True,artifacts_compared=10*len(rows)),
        interpretation='Topology names denote construction strategies, not proof of independent shapes. Lengths differ; no controlled driving comparison.',
        baseline=str(baseline.relative_to(ROOT)),formal_dataset_generated=False)
    write_json(root/'summary.json',summary);write_json(root/'comparison.json',rows);write_json(root/'phase5_1_comparison.json',old_rows)
    with (root/'comparison.csv').open('w',newline='') as handle:
        if rows:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader()
            writer.writerows({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows)
    html='<!doctype html><meta charset="utf-8"><title>Phase 5.2 pilot</title><style>body{font:16px system-ui;max-width:1500px;margin:30px auto}img{width:100%}td,th{padding:6px;text-align:left}table{border-collapse:collapse}tr{border-bottom:1px solid #ccc}</style>'
    html+=f'<h1>Phase 5.2 pilot: {len(rows)}/10</h1><p>{len(manifest["rejected"])} rejected candidates; {len(topologies)} topology strategies. All accepted bundles pass native replay and geometry validation.</p>'
    html+='<p><a href="comparison.csv">CSV</a> · <a href="comparison.json">Metrics</a> · <a href="summary.json">Comparison</a> · <a href="manifest.json">Recipes and failures</a></p><img src="plots/overview.png" alt="Ten-track gallery">'
    for label in ('specialists_a','specialists_b_and_composites'):html+=f'<img src="plots/phase5_1_comparison_{label}.png" alt="Phase 5.1 versus Phase 5.2">'
    (root/'index.html').write_text(html+'<p>Sampled clearance; physical drivability unassessed. No formal release or independence audit.</p>\n')
    return summary


def generate(root,baseline,*,resume=False):
    root=Path(root)
    if resume:
        manifest=json.loads((root/'manifest.json').read_text())
        if manifest['tuning_pass']!=1:raise ValueError('At most one focused adjustment pass is permitted')
        manifest['tuning_pass']=2
    else:
        root.mkdir(parents=True,exist_ok=False)
        manifest=dict(dataset_id='phase5_2_pilot',design_version='research_design.v2',requested=10,complete=False,
            tuning_pass=1,accepted=[],rejected=[],missing=[],scope='offline geometry pilot; no formal release')
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json')
    accepted_names={e['name'] for e in manifest['accepted']}
    for index,(family,scale,variant) in enumerate(CASES):
        name=f'{family}_{variant+1:02d}'
        if name in accepted_names:continue
        for attempt in range(1,5):
            spec=None
            try:
                spec=refined_spec(family,scale,variant,52000+index,vehicle,attempt)
                prepared=prepare_research(spec);bundle=publish_research(spec,root/'tracks'/name,prepared=prepared)
                entry=dict(name=name,target_family=spec.target_family,scale=scale,track_id=spec.track_id,
                    map=str(bundle.relative_to(root)),metadata=str((bundle.parent/(spec.track_id+'_metadata.json')).relative_to(root)),
                    recipe=str((bundle.parent/(spec.track_id+'_generation.yaml')).relative_to(root)),attempt=attempt,
                    tuning_pass=manifest['tuning_pass'],statistics=prepared.statistics)
                entry['comparison']=statistics(entry,prepared.metadata);manifest['accepted'].append(entry);accepted_names.add(name)
                print(f"Accepted {name} attempt {attempt}: primary {prepared.statistics['primary_coverage']:.1%}, active {prepared.statistics['active_curvature_fraction']:.1%}",flush=True);break
            except (GeometryError,ValueError) as exc:
                record=dict(name=name,attempt=attempt,tuning_pass=manifest['tuning_pass'],seed=spec.seed if spec else None,
                    native_recipe=spec.recipe() if spec else None,reason=str(exc),layout_attempts=getattr(exc,'attempts',[]))
                manifest['rejected'].append(record)
                details=[r.get('reason',r['status']) for r in record['layout_attempts']]
                print(f'Rejected {name} attempt {attempt}: {exc}: {details}',flush=True)
            write_json(root/'manifest.json',manifest)
        manifest['missing']=[f'{f}_{v+1:02d}' for f,s,v in CASES if f'{f}_{v+1:02d}' not in accepted_names]
        write_json(root/'manifest.json',manifest)
    manifest['complete']=len(accepted_names)==10;write_json(root/'manifest.json',manifest)
    summary=report(root,manifest,baseline)
    print(f"Pilot {summary['accepted']}/10; {summary['rejected']} rejected; {summary['distinct_topology_strategies']} topology strategies",flush=True)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'generated_maps/phase5_2_pilot')
    parser.add_argument('--baseline',type=Path,default=ROOT/'examples/phase5_1_pilot')
    parser.add_argument('--resume-adjustment',action='store_true',help='One focused adjustment pass over missing cases only')
    args=parser.parse_args();generate(args.output,args.baseline,resume=args.resume_adjustment)
