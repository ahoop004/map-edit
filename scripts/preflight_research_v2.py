#!/usr/bin/env python3
"""Phase 5.2D bounded irregular-composite screen and conditional 60-slot dry run."""
import argparse
from collections import Counter
from dataclasses import replace
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from map_editor.geometry import GeometryError
from map_editor.services.dataset_spec import default_dataset_spec
from map_editor.services.research_design import candidate_spec
from map_editor.services.research_reliable_design import irregular_composite_spec,IRREGULAR_VARIANTS
from map_editor.services.research_tracks import prepare_research
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.dataset_diversity import normalized_shape,pair_metrics,classify_pair
from generate_research_diversity_pilot import write_json
from plot_extended_pilot import geometry,COLORS

CASES=(('medium',4),('medium',5),('long',5))


def protected():
    roots=[ROOT/'datasets/phase5_v1',ROOT/'examples',*(ROOT/'generated_maps'/p for p in ('phase5_2_pilot','phase5_2b_pilot','phase5_2c_readiness'))]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for root in roots for p in sorted(root.rglob('*')) if p.is_file()}


def shape_of(prepared):return normalized_shape([(p.x,p.y) for p in prepared.sampled.states[:-1]])


def metrics(e):
    s=e['statistics']
    return dict(primary_coverage=s['primary_coverage'],supporting_fraction=s['supporting_fraction'],
        active_curvature=s['active_curvature_fraction'],significant_turns=s['corner_count'],family_transitions=s['primary_family_switch_count'],
        repetition=s['repetition_fraction'],symmetry_error_m=s['symmetry_error_m'],length_m=s['raw_lap_length_m'],
        primary_straight_fraction=s['primary_family_exposure_fractions'].get('straight',0.))


def irregular_review(entry):
    m=metrics(entry)
    failures=[]
    if m['repetition']>=.65:failures.append('periodic_repetition_at_least_0.65')
    if m['symmetry_error_m']<=1.:failures.append('near_halfturn_symmetry')
    if m['active_curvature']<.35:failures.append('active_curvature_below_0.35')
    if m['primary_straight_fraction']>.30:failures.append('primary_straights_exceed_0.30')
    return dict(eligible=not failures,failures=failures,metrics=m)


def compare(a,b,sa,sb,policy):
    m=pair_metrics(a['statistics'],b['statistics'],sa,sb)
    ia,ib=a['identity'],b['identity']
    exact=ia['centerline_fingerprint']==ib['centerline_fingerprint'] or ia['coordinate_fingerprint']==ib['coordinate_fingerprint']
    return dict(first=a['name'],second=b['name'],status='exact_duplicate' if exact else classify_pair(m,policy),**m)


def independent_subset(entries,shapes,policy):
    pairs=[compare(a,b,shapes[a['name']],shapes[b['name']],policy) for i,a in enumerate(entries) for b in entries[i+1:]]
    best=[]
    for mask in range(1<<len(entries)):
        selected=[e['name'] for i,e in enumerate(entries) if mask&(1<<i)]
        if len(selected)>len(best) and all(p['status']=='independent_under_policy' for p in pairs if p['first'] in selected and p['second'] in selected):best=selected
    return best,pairs


def save_review(root,e,p):
    folder=root/'focus'/e['name'];folder.mkdir(parents=True)
    xy=np.array([(s.x,s.y) for s in p.sampled.states[:-1]])
    np.savetxt(folder/'coordinates.csv',xy,delimiter=',',header='x_m,y_m',comments='',fmt='%.6f')
    write_json(folder/'review.json',dict(metadata=p.metadata,profile=p.geometry.profile,
        walls=[[(v.x,v.y) for v in wall] for wall in p.geometry.walls]))


def gallery(root,result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    chosen=[name for c in result['categories'] for name in c['independent_set'][:2]]
    loaded={}
    for name in chosen:
        folder=root/'focus'/name;review=json.loads((folder/'review.json').read_text())
        xy=np.loadtxt(folder/'coordinates.csv',delimiter=',',skiprows=1)
        fields=('s_m','heading_rad','left_width_m','right_width_m')
        profile=np.array([tuple(r[k] for k in fields) for r in review['profile']],dtype=[(k,float) for k in fields])
        loaded[name]=(review['metadata'],xy,profile,[np.array(w) for w in review['walls']])
    span=max((np.ptp(v[1],axis=0).max() for v in loaded.values()),default=80.)*1.12
    fig,axes=plt.subplots(3,2,figsize=(13,17),constrained_layout=True)
    entries={e['name']:e for e in result['evidence']}
    for row,c in enumerate(result['categories']):
        for j in range(2):
            ax=axes[row,j]
            if j<len(c['independent_set']):
                name=c['independent_set'][j];e=entries[name];m=metrics(e)
                geometry(ax,*loaded[name],span)
                ax.set_title(f"{name} · {m['length_m']:.0f} m\n{e['native_recipe']['topology_family']}\nactive {m['active_curvature']:.0%}; turns {m['significant_turns']}; switches {m['family_transitions']}; repetition {m['repetition']:.2f}",fontsize=8)
            else:ax.text(.5,.5,c['category']+'\nNo second independent eligible layout',ha='center',transform=ax.transAxes);ax.set_axis_off()
    fig.suptitle(f'Phase 5.2D asymmetric composites · common {span:.0f} m metric axes',fontsize=14)
    fig.legend(handles=[Patch(color=COLORS[k],label=k) for k in ('hairpin','sweeper','chicane','s_curve','corner','straight','transition')],loc='lower center',ncol=7)
    fig.savefig(root/'focus_gallery.png',dpi=145);fig.savefig(root/'focus_gallery.svg',metadata={'Date':None});plt.close(fig)


def focus(root):
    if (root/'focused_screen.json').exists():raise FileExistsError('Focused screen is immutable')
    frozen=protected();write_json(root/'preservation.json',dict(sha256=frozen,unchanged=False))
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json');policy=default_dataset_spec().policy
    old=json.loads((ROOT/'generated_maps/phase5_2c_readiness/readiness.json').read_text())
    baseline=[dict(e,name='phase5_2c_'+e['name']) for e in old['evidence'] if e['status']=='accepted']
    old_shapes={e['name']:normalized_shape(np.loadtxt(ROOT/'generated_maps/phase5_2c_readiness/coordinates'/(e['name'].removeprefix('phase5_2c_')+'.csv'),delimiter=',',skiprows=1)) for e in baseline}
    evidence=[];categories=[];shapes={};accepted=[];old_pairs=[]
    for index,(scale,complexity) in enumerate(CASES):
        category=f'composite_{complexity}_{scale}';eligible=[];best=[];pairs=[]
        for variant in range(6):
            name=f'{category}_profile_{variant}';spec=None
            try:
                # The same closure seed for all six explicitly different designs.
                spec=irregular_composite_spec(scale,complexity,variant,85000+index,vehicle,variant+1)
                p=prepare_research(spec)
                e=dict(name=name,category=category,variant=variant,status='geometry_accepted',native_recipe=spec.recipe(),
                    statistics=p.statistics,identity=p.metadata['provenance']['identity'],layout_attempts=p.metadata['provenance']['layout_attempts'])
                e['technical_review']=irregular_review(e);shapes[name]=shape_of(p);accepted.append(e);save_review(root,e,p)
                for old_e in baseline:
                    old_pairs.append(compare(e,old_e,shapes[name],old_shapes[old_e['name']],policy))
                if e['technical_review']['eligible']:eligible.append(e)
                best,pairs=independent_subset(eligible,shapes,policy)
            except (GeometryError,ValueError) as exc:
                e=dict(name=name,category=category,variant=variant,status='rejected',reason=str(exc),
                    native_recipe=spec.recipe() if spec else None,layout_attempts=getattr(exc,'attempts',[]))
            evidence.append(e)
            print(name+': '+e['status']+(f" {metrics(e)}" if e['status']=='geometry_accepted' else f" {[r.get('reason') for r in e['layout_attempts']] or e['reason']}"),flush=True)
            write_json(root/'focused_progress.json',dict(evidence=evidence,categories=categories))
            if len(best)>=2:break
        before=next(c for c in old['categories'] if c['category']==category)
        categories.append(dict(category=category,scale=scale,complexity=complexity,attempted=sum(e['category']==category for e in evidence),
            geometry_accepted=sum(e['category']==category for e in accepted),eligible=len(eligible),independent_set=best,independent_count=len(best),
            promoted_variants=[e['variant'] for e in eligible if e['name'] in best],target_met=len(best)>=2,
            previous_geometry_accepted=before['improved_passes'],previous_attempted=4,previous_independent_count=before['independent_count'],pairs=pairs))
    cross_new=[compare(a,b,shapes[a['name']],shapes[b['name']],policy) for i,a in enumerate(accepted) for b in accepted[i+1:] if a['category']!=b['category']]
    result=dict(categories=categories,evidence=evidence,all_categories_pass=all(c['target_met'] for c in categories),
        phase5_2c_comparisons=old_pairs,cross_category_comparisons=cross_new,policy=policy,
        technical_review_criteria=dict(maximum_repetition_exclusive=.65,minimum_symmetry_error_exclusive_m=1.,minimum_active_curvature=.35,maximum_primary_straight_exposure=.30),
        preflight_status='pending' if all(c['target_met'] for c in categories) else 'not_run_prerequisite_failed')
    write_json(root/'focused_screen.json',result);gallery(root,result)
    rows=[]
    for e in accepted:
        closest=min((p for p in old_pairs if p['first']==e['name']),key=lambda p:p['normalized_shape_distance'])
        rows.append(dict(name=e['name'],category=e['category'],layout=e['native_recipe']['topology_family'],**metrics(e),
            closest_phase5_2c=closest['second'],closest_phase5_2c_shape_distance=closest['normalized_shape_distance'],closest_phase5_2c_status=closest['status']))
    if rows:
        with (root/'focus_metrics.csv').open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert frozen==protected(),'Protected outputs changed'
    write_json(root/'preservation.json',dict(sha256=frozen,unchanged=True,artifact_count=len(frozen)))
    return result


def preflight(root):
    result=json.loads((root/'focused_screen.json').read_text())
    if not result['all_categories_pass']:raise ValueError('60-slot preflight requires all focused categories to pass')
    if any(tuple(c['promoted_variants'])!=IRREGULAR_VARIANTS[(c['scale'],c['complexity'])] for c in result['categories']):
        raise ValueError('Preflight profiles differ from the independently screened constructions')
    if (root/'preflight.json').exists():raise FileExistsError('Only one preflight is authorized')
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json');dataset=default_dataset_spec(design_version='research_design.v2')
    accepted=[];shapes={};attempts=[];filled=set();slots={s.slot_id:s for s in dataset.slots}
    for attempt in (1,2,3):
        # Initial round covers every slot before either fallback round.
        for slot in dataset.slots:
            if slot.slot_id in filled:continue
            spec=None
            try:
                spec=candidate_spec(dataset,slot,attempt,vehicle);p=prepare_research(spec)
                name=slot.slot_id;e=dict(name=name,slot_id=name,split=slot.split,scale=slot.scale,family=slot.family,
                    complexity=slot.complexity,generation_mode=slot.generation_mode,attempt=attempt,native_recipe=spec.recipe(),
                    statistics=p.statistics,identity=p.metadata['provenance']['identity'])
                shape=shape_of(p);comparisons=[compare(e,a,shape,shapes[a['name']],dataset.policy) for a in accepted]
                failures=[c for c in comparisons if c['status']!='independent_under_policy']
                affected=slot.generation_mode=='composite' and (slot.scale,slot.complexity) in CASES
                review=irregular_review(e) if affected else None
                status='independence_rejected' if failures else 'technical_review_rejected' if review and not review['eligible'] else 'accepted'
                record=dict(e,status=status,layout_attempts=p.metadata['provenance']['layout_attempts'],technical_review=review,
                    duplicate_comparisons=failures,closest_shape=min(comparisons,key=lambda c:c['normalized_shape_distance']) if comparisons else None)
                if status=='accepted':accepted.append(e);shapes[name]=shape;filled.add(name)
            except (GeometryError,ValueError) as exc:
                record=dict(slot_id=slot.slot_id,split=slot.split,scale=slot.scale,family=slot.family,complexity=slot.complexity,
                    generation_mode=slot.generation_mode,attempt=attempt,status='geometry_rejected',reason=str(exc),
                    native_recipe=spec.recipe() if spec else None,layout_attempts=getattr(exc,'attempts',[]))
            attempts.append(record);print(f"Preflight {slot.slot_id} #{attempt}: {record['status']}",flush=True)
            write_json(root/'preflight_progress.json',dict(complete=False,attempts=attempts,filled=len(filled)))
    pairs=[dict(compare(a,b,shapes[a['name']],shapes[b['name']],dataset.policy),cross_split=a['split']!=b['split']) for i,a in enumerate(accepted) for b in accepted[i+1:]]
    missing=[s.slot_id for s in dataset.slots if s.slot_id not in filled]
    summary=dict(complete=True,allocation=dataset.recipe(),slots_requested=60,filled=len(filled),missing=missing,
        attempted=len(attempts),maximum_attempts_per_slot=3,status_counts=dict(Counter(r['status'] for r in attempts)),
        first_round_status_counts=dict(Counter(r['status'] for r in attempts if r['attempt']==1)),
        accepted_by_split=dict(Counter(e['split'] for e in accepted)),accepted_by_scale=dict(Counter(e['scale'] for e in accepted)),
        filled_categories=dict(Counter((e['family'] or 'composite_'+str(e['complexity']))+'_'+e['scale'] for e in accepted)),
        retained_pairwise_comparisons=len(pairs),cross_split_comparisons=sum(p['cross_split'] for p in pairs),
        retained_independence_failures=[p for p in pairs if p['status']!='independent_under_policy'],
        accepted=accepted,attempts=attempts,pairs=pairs,
        formal_dataset_generated=False,selection='Greedy allocation order; one candidate per slot initially, at most two fallback candidates for unfilled slots. No solver or global selection optimization added.')
    write_json(root/'preflight.json',summary)
    write_json(root/'preflight_summary.json',{k:v for k,v in summary.items() if k not in ('attempts','accepted','pairs','allocation')})
    result.update(preflight_status='completed',preflight_result='preflight.json');write_json(root/'focused_screen.json',result)
    assert json.loads((root/'preservation.json').read_text())['sha256']==protected(),'Protected outputs changed'
    print(f"Preflight filled {len(filled)}/60 from {len(attempts)} candidate preparations",flush=True)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['focus','preflight']);parser.add_argument('--output',type=Path,default=ROOT/'generated_maps/phase5_2d_preflight')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    (focus if args.command=='focus' else preflight)(args.output)
