#!/usr/bin/env python3
"""One bounded Phase 5.2E candidate-pool preflight; no map publication."""
import argparse
from collections import Counter
from dataclasses import replace
import csv
from itertools import combinations
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from map_editor.geometry import GeometryError
from map_editor.services.dataset_spec import default_dataset_spec
from map_editor.services.research_design import candidate_spec
from map_editor.services.research_tracks import prepare_research
from map_editor.services.research_pool_selection import select_candidates
from map_editor.services.dataset_diversity import classify_pair,pair_metrics
from map_editor.services.extended_spec import load_vehicle_snapshot
from preflight_research_v2 import protected,metrics,shape_of,compare
from generate_research_diversity_pilot import write_json
from plot_extended_pilot import geometry,COLORS

PREPARATION_CAP=180


def snapshot():
    import hashlib
    result=protected()
    for p in sorted((ROOT/'generated_maps/phase5_2d_preflight').rglob('*')):
        if p.is_file():result[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def save_review(root,e,p):
    folder=root/'candidates'/e['name'];folder.mkdir(parents=True)
    write_json(folder/'metadata.json',p.metadata)
    np.savez_compressed(folder/'review.npz',xy=np.array([(s.x,s.y) for s in p.sampled.states[:-1]]),
        profile=np.array([tuple(r[k] for k in ('s_m','heading_rad','left_width_m','right_width_m')) for r in p.geometry.profile]),
        **{f'wall_{i}':np.array([(v.x,v.y) for v in wall]) for i,wall in enumerate(p.geometry.walls)})


def run(root):
    root.mkdir(parents=True,exist_ok=False)
    frozen=snapshot();dataset=default_dataset_spec(design_version='research_design.v2')
    write_json(root/'protocol.json',dict(allocation=dataset.recipe(),initial_specialist_pool=2,initial_composite_pool=3,
        maximum_specialist_pool=3,maximum_composite_pool=5,maximum_preparations=PREPARATION_CAP,
        additional_attempts='Only slots unfilled by selection, with no valid geometry, or composites lacking low-repetition options; at most two extra pool rounds.',
        selector=dict(max_node_visits=5000,max_passes=3,maximum_displaced_slots=2,repair_depth=2),
        publication=False,simulator=False))
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json')
    records=[];valid={};shapes={};counts=Counter();conflicts={};pair_records=[]
    slots={s.slot_id:s for s in dataset.slots}
    def generate(slot):
        if len(records)>=PREPARATION_CAP:return
        counts[slot.slot_id]+=1;attempt=counts[slot.slot_id];name=f'{slot.slot_id}__{attempt}';spec=None
        try:
            spec=candidate_spec(dataset,slot,attempt,vehicle)
            p=prepare_research(spec)
            assert (spec.split,spec.parent_lineage,spec.slot_id)==(slot.split,slot.parent_lineage,slot.slot_id)
            e=dict(name=name,slot_id=slot.slot_id,split=slot.split,scale=slot.scale,family=slot.family,complexity=slot.complexity,
                generation_mode=slot.generation_mode,attempt=attempt,status='geometry_valid',native_recipe=spec.recipe(),
                statistics=p.statistics,identity=p.metadata['provenance']['identity'],layout_attempts=p.metadata['provenance']['layout_attempts'])
            e['technical_quality']=dict(low_repetition=p.statistics['repetition_fraction']<.65,
                high_repetition=p.statistics['repetition_fraction']>.95,
                primary_family_exposure=p.statistics['primary_family_exposure_fractions'],
                interpretation='Repetition ranks valid geometry; it is not a difficulty or independent-topology label.')
            shape=shape_of(p);conflicts[name]=set()
            for other in valid.values():
                pair=compare(e,other,shape,shapes[other['name']],dataset.policy)
                if pair['status']!='independent_under_policy':
                    conflicts[name].add(other['name']);conflicts[other['name']].add(name)
                    pair.update(same_slot=slot.slot_id==other['slot_id'],cross_split=slot.split!=other['split']);pair_records.append(pair)
            valid[name]=e;shapes[name]=shape;save_review(root,e,p)
        except (GeometryError,ValueError) as exc:
            e=dict(name=name,slot_id=slot.slot_id,split=slot.split,scale=slot.scale,family=slot.family,complexity=slot.complexity,
                generation_mode=slot.generation_mode,attempt=attempt,status='geometry_rejected',reason=str(exc),
                native_recipe=spec.recipe() if spec else None,layout_attempts=getattr(exc,'attempts',[]))
        records.append(e)
        print(name+': '+e['status']+(f" repetition={e['statistics']['repetition_fraction']:.3f}" if e['status']=='geometry_valid' else f" {[a.get('reason') for a in e['layout_attempts']] or e['reason']}"),flush=True)
        write_json(root/'progress.json',dict(attempted=len(records),geometry_valid=len(valid),evidence=records))
    def choose():
        pools={s.slot_id:[e['name'] for e in valid.values() if e['slot_id']==s.slot_id] for s in dataset.slots}
        attrs={n:dict(repetition=e['statistics']['repetition_fraction'],composite=e['generation_mode']=='composite') for n,e in valid.items()}
        return select_candidates(pools,conflicts,attrs)
    for slot in dataset.slots:
        for _ in range(3 if slot.generation_mode=='composite' else 2):generate(slot)
    selection=choose();rounds=[dict(stage='initial_pool',attempted=len(records),**selection)]
    for extra_round in range(2):
        chosen=selection['selection']
        composite_low=sum(valid[n]['generation_mode']=='composite' and valid[n]['statistics']['repetition_fraction']<.65 for n in chosen.values())
        problematic=[]
        for slot in dataset.slots:
            options=[e for e in valid.values() if e['slot_id']==slot.slot_id]
            cap=5 if slot.generation_mode=='composite' else 3
            needs=slot.slot_id not in chosen or composite_low<20 and slot.generation_mode=='composite' and not any(e['statistics']['repetition_fraction']<.65 for e in options)
            if needs and counts[slot.slot_id]<cap:problematic.append(slot)
        if not problematic or len(records)>=PREPARATION_CAP:break
        problematic.sort(key=lambda s:(selection['slot_independent_option_counts'][s.slot_id],s.slot_id))
        for slot in problematic:generate(slot)
        selection=choose();rounds.append(dict(stage=f'problematic_pool_extension_{extra_round+1}',attempted=len(records),**selection))
    # Compare scarcity+repair selection with the original slot-order greedy rule
    # on exactly the same pool, so generation and selection gains are separable.
    greedy={}
    for slot in dataset.slots:
        for e in records:
            if e['slot_id']==slot.slot_id and e['status']=='geometry_valid' and all(e['name'] not in conflicts[n] for n in greedy.values()):
                greedy[slot.slot_id]=e['name'];break
    selected=[valid[n] for s,n in sorted(selection['selection'].items())]
    retained_pairs=[dict(compare(a,b,shapes[a['name']],shapes[b['name']],dataset.policy),cross_split=a['split']!=b['split']) for a,b in combinations(selected,2)]
    assert all(p['status']=='independent_under_policy' for p in retained_pairs)
    composites=[e for e in selected if e['generation_mode']=='composite']
    low=sum(e['statistics']['repetition_fraction']<.65 for e in composites);high=sum(e['statistics']['repetition_fraction']>.95 for e in composites)
    baseline=json.loads((ROOT/'generated_maps/phase5_2d_preflight/preflight.json').read_text())
    by_category={}
    for e in records:
        c=(e['family'] or 'composite_'+str(e['complexity']))+'_'+e['scale']
        by_category.setdefault(c,Counter())[e['status']]+=1
    summary=dict(complete=True,slots_requested=60,filled=len(selected),missing=[s.slot_id for s in dataset.slots if s.slot_id not in selection['selection']],
        allocation_complete=len(selected)==60,geometric_diversity_goal_met=low>=20,low_repetition_composites=low,high_repetition_composites=high,
        selected_specialists=len(selected)-len(composites),selected_composites=len(composites),preparations=len(records),geometry_valid=len(valid),geometry_rejected=len(records)-len(valid),
        pool_independence_conflicts=sum(not p['same_slot'] for p in pair_records),pool_cross_split_conflicts=sum(p['cross_split'] for p in pair_records),
        selected_pair_comparisons=len(retained_pairs),selected_cross_split_comparisons=sum(p['cross_split'] for p in retained_pairs),retained_conflicts=[],
        candidate_replacements=selection['candidate_replacements'],selection_node_visits=selection['node_visits'],selection_budget_exhausted=selection['budget_exhausted'],
        same_pool_slot_order_greedy_filled=len(greedy),same_pool_slot_order_greedy_low_repetition_composites=sum(valid[n]['generation_mode']=='composite' and valid[n]['statistics']['repetition_fraction']<.65 for n in greedy.values()),
        phase5_2d_baseline=dict(filled=baseline['filled'],selected_composites=25,low_repetition_composites=sum(e['generation_mode']=='composite' and e['statistics']['repetition_fraction']<.65 for e in baseline['accepted']),
            high_repetition_composites=19,preparations=baseline['attempted']),
        by_split=dict(Counter(e['split'] for e in selected)),by_scale=dict(Counter(e['scale'] for e in selected)),
        category_counts={k:dict(v) for k,v in sorted(by_category.items())},selected=selected,
        selection_rounds=rounds,evidence=records,conflict_pairs=pair_records,retained_pairs=retained_pairs,policy=dataset.policy,
        allocation=dataset.recipe(),formal_dataset_generated=False,
        limitation='Bounded heuristic over finite pools, not an optimality proof. Low repetition is not a driving-difficulty or independent-topology claim.')
    write_json(root/'preflight.json',summary)
    write_json(root/'summary.json',{k:v for k,v in summary.items() if k not in ('selected','selection_rounds','evidence','conflict_pairs','retained_pairs','allocation')})
    with (root/'selected_metrics.csv').open('w',newline='') as handle:
        rows=[dict(slot_id=e['slot_id'],candidate=e['name'],split=e['split'],scale=e['scale'],families='|'.join(e['statistics']['measured_primary_families']),**metrics(e)) for e in selected]
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    make_gallery(root,selected,shapes,dataset.policy)
    assert snapshot()==frozen,'Protected V1 or pilot output changed'
    write_json(root/'preservation.json',dict(unchanged=True,artifact_count=len(frozen),sha256=frozen))
    print(f'Pool preflight: {len(selected)}/60; low repetition {low}/30; high repetition {high}; {len(records)} preparations',flush=True)
    return summary


def make_gallery(root,selected,shapes,policy):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    composites=[e for e in selected if e['generation_mode']=='composite']
    chosen=[];covered=set()
    while len(chosen)<min(10,len(composites)):
        remaining=[e for e in composites if e not in chosen]
        def rank(e):
            key=(tuple(e['statistics']['measured_primary_families']),e['scale'])
            distance=min((pair_metrics(e['statistics'],p['statistics'],shapes[e['name']],shapes[p['name']])['normalized_shape_distance'] for p in chosen),default=1.)
            return (key not in covered,e['statistics']['repetition_fraction']<.65,distance,-e['statistics']['repetition_fraction'],e['name'])
        e=max(remaining,key=rank);chosen.append(e);covered.add((tuple(e['statistics']['measured_primary_families']),e['scale']))
    loaded={}
    for e in chosen:
        folder=root/'candidates'/e['name'];metadata=json.loads((folder/'metadata.json').read_text())
        with np.load(folder/'review.npz') as data:
            fields=('s_m','heading_rad','left_width_m','right_width_m')
            profile=np.array([tuple(r) for r in data['profile']],dtype=[(f,float) for f in fields])
            loaded[e['name']]=(metadata,data['xy'].copy(),profile,[data[k].copy() for k in sorted(data.files) if k.startswith('wall_')])
    span=max(np.ptp(x[1],axis=0).max() for x in loaded.values())*1.12
    fig,axes=plt.subplots(2,5,figsize=(23,11),constrained_layout=True)
    for ax,e in zip(axes.flat,chosen):
        geometry(ax,*loaded[e['name']],span);m=metrics(e)
        ax.set_title(f"{e['slot_id']}\n{' / '.join(e['statistics']['measured_primary_families'])}\n{m['length_m']:.0f} m · active {m['active_curvature']:.0%} · repetition {m['repetition']:.2f}",fontsize=8)
    fig.suptitle(f'Phase 5.2E: representative selected composites · common {span:.0f} m metric axes',fontsize=14)
    fig.legend(handles=[Patch(color=COLORS[k],label=k) for k in COLORS],loc='lower center',ncol=10)
    fig.savefig(root/'composite_gallery.png',dpi=145);fig.savefig(root/'composite_gallery.svg',metadata={'Date':None});plt.close(fig)
    write_json(root/'gallery_selection.json',[dict(name=e['name'],families=e['statistics']['measured_primary_families'],**metrics(e)) for e in chosen])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'generated_maps/phase5_2e_preflight')
    run(parser.parse_args().output)
