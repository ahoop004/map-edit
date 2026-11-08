#!/usr/bin/env python3
"""Phase 5.2C: diagnose saved budgets, then 4 configurations in 18 categories."""
import argparse
from collections import Counter,defaultdict
from dataclasses import replace
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from map_editor.geometry import GeometryError
from map_editor.services.dataset_spec import default_dataset_spec,DatasetSlot
from map_editor.services.research_spec import spec_from_recipe
from map_editor.services.research_design import candidate_spec
from map_editor.services.research_tracks import prepare_research
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.extended_layout import MotionModel,supporting_curve
from map_editor.services.dataset_diversity import normalized_shape,pair_metrics,classify_pair
from generate_research_diversity_pilot import write_json


def diagnose(source,root):
    old=json.loads(source.read_text());rows=[]
    for e in old['evidence']:
        if e['status']!='rejected':continue
        s=spec_from_recipe(e['native_recipe']);top=s.topologies[0];model=MotionModel(s,top)
        angles=np.array([math.radians(min(t.angle_bounds_deg,key=abs)) for t in top.turns])
        lower_support=sum(supporting_curve(t,a).length_m for t,a in zip(top.turns,angles))
        primary=sum(r.build().length_m for r in s.inventory)
        heading_deficit=math.tau-model.fixed_heading
        flags=[]
        if primary/s.target_lap_length_m<s.minimum_primary_coverage-1e-5:flags.append('fixed_primary_coverage_below_floor')
        lo,hi=s.connector_length_bounds_m
        if primary+lower_support+lo*len(s.inventory)>s.target_lap_length_m+1e-6:flags.append('minimum_source_and_support_exceed_lap')
        if not sum(math.radians(t.angle_bounds_deg[0]) for t in top.turns)-1e-7<=heading_deficit<=sum(math.radians(t.angle_bounds_deg[1]) for t in top.turns)+1e-7:
            flags.append('heading_deficit_outside_support_bounds')
        certificate=None
        if all(t.angle_bounds_deg[0]==t.angle_bounds_deg[1] for t in top.turns):
            # A necessary scalar projection bound, not a closure algorithm.
            # Available straight length cannot generate more displacement along
            # any direction than its length times the best available heading.
            n=len(s.inventory);initial=np.r_[np.full(n,lo),angles];fixed=model.evaluate(initial)
            available=-fixed[3];directions=[]
            for i in range(n):
                p=initial.copy();p[i]+=1;directions.append(model.evaluate(p)[:2]-fixed[:2])
            normals=[np.array([math.cos(a),math.sin(a)]) for a in np.arange(8)*math.pi/4]
            if np.linalg.norm(fixed[:2])>1e-9:normals.append(-fixed[:2]/np.linalg.norm(fixed[:2]))
            for normal in normals:
                required=float(-fixed[:2]@normal);maximum=float(max(np.array(directions)@normal)*max(0.,available))
                if required>maximum+1e-6:
                    flags.append('insufficient_gap_displacement_budget')
                    certificate=dict(direction=normal.tolist(),required_projection_m=required,maximum_available_projection_m=maximum)
                    break
        reason='coverage' if any('objective failure' in a.get('reason','') for a in e['layout_attempts']) else 'bounded_closure'
        rows.append(dict(category=e['category'],replicate=e['replicate'],construction=s.topology_family,
            generation_mode=s.generation_mode,family=s.target_family or 'composite',scale=next(c['scale'] for c in old['categories'] if c['category']==e['category']),
            reason=reason,target_m=s.target_lap_length_m,primary_source_m=primary,primary_fraction=primary/s.target_lap_length_m,
            minimum_support_source_m=lower_support+lo*len(s.inventory),heading_deficit_rad=heading_deficit,
            structural_flags=flags,displacement_certificate=certificate,
            failure_reasons=[a.get('reason') for a in e['layout_attempts']]))
    grouped=defaultdict(Counter)
    for r in rows:grouped[(r['family'],r['scale'],r['construction'])][r['reason']]+=1
    report=dict(failures=len(rows),reason_counts=dict(Counter(r['reason'] for r in rows)),
        structural_flags=dict(Counter(flag for r in rows for flag in r['structural_flags'])),
        grouped=[dict(family=f,scale=s,construction=t,reasons=dict(v)) for (f,s,t),v in grouped.items()],evidence=rows,
        interpretation='Flags are necessary-condition violations. Absence of a flag does not establish feasibility, particularly with adjustable supporting angles.',
        old_independence_flags=old['non_independent_pairs'])
    write_json(root/'failure_diagnosis.json',report)
    return report


def snapshot():
    roots=[ROOT/'datasets/phase5_v1',ROOT/'examples/phase3b_pilot',ROOT/'examples/phase4b_pilot',ROOT/'examples/phase5_1_pilot',ROOT/'generated_maps/phase5_2_pilot',ROOT/'generated_maps/phase5_2b_pilot']
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for root in roots for p in sorted(root.rglob('*')) if p.is_file()}


def screen(root):
    if (root/'readiness.json').exists():raise FileExistsError('Readiness screen is immutable; no repeated tuning')
    frozen=snapshot();old=json.loads((ROOT/'generated_maps/phase5_2b_pilot/readiness.json').read_text())
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json');dataset=default_dataset_spec(design_version='research_design.v2')
    cases=[('composite',None,c,s) for c in (2,3,4,5) for s in ('short','medium','long')]
    cases += [('specialist',f,None,s) for f in ('chicane','s_curve') for s in ('short','medium','long')]
    records=[];shapes={};categories=[];survivors=[]
    for index,(mode,family,complexity,scale) in enumerate(cases):
        name=f'{family or "composite_"+str(complexity)}_{scale}'
        slot=DatasetSlot('readiness_'+name,'train',mode,family,complexity,scale,72000+index,'phase5_2c_'+name)
        # Each slot starts on variant zero; 4 attempts cover all 4 template words.
        slot=replace(slot,design_seed=slot.design_seed-slot.design_seed%4)
        valid=[]
        for attempt in range(1,5):
            spec=None;key=f'{name}_{attempt}'
            try:
                spec=candidate_spec(dataset,slot,attempt,vehicle)
                prepared=prepare_research(spec)
                shape=normalized_shape([(p.x,p.y) for p in prepared.sampled.states[:-1]])
                shapes[key]=shape
                e=dict(name=key,category=name,configuration=attempt,status='accepted',native_recipe=spec.recipe(),statistics=prepared.statistics,
                    identity=prepared.metadata['provenance']['identity'],layout_attempts=prepared.metadata['provenance']['layout_attempts'])
                valid.append(e);survivors.append(e)
                # Small review artifact only, no map bundles or native replay.
                xy=np.array([(p.x,p.y) for p in prepared.sampled.states[:-1]])
                (root/'coordinates').mkdir(exist_ok=True);np.savetxt(root/'coordinates'/(key+'.csv'),xy,delimiter=',',header='x_m,y_m',comments='',fmt='%.6f')
            except (GeometryError,ValueError) as exc:
                e=dict(name=key,category=name,configuration=attempt,status='rejected',native_recipe=spec.recipe() if spec else None,
                    reason=str(exc),layout_attempts=getattr(exc,'attempts',[]))
            records.append(e)
            print(f'{key}: '+e['status']+(f" primary={e['statistics']['primary_coverage']:.1%}" if e['status']=='accepted' else f" {[a.get('reason') for a in e['layout_attempts']] or e['reason']}"),flush=True)
            write_json(root/'readiness.json',dict(complete=False,evidence=records,categories=categories))
        pairs=[]
        for i,a in enumerate(valid):
            for b in valid[i+1:]:
                metrics=pair_metrics(a['statistics'],b['statistics'],shapes[a['name']],shapes[b['name']])
                pairs.append(dict(first=a['name'],second=b['name'],status=classify_pair(metrics,dataset.policy),**metrics))
        # Four vertices: exhaust all subsets for the largest pairwise-independent set.
        independent=[]
        for mask in range(1<<len(valid)):
            subset=[v['name'] for i,v in enumerate(valid) if mask&(1<<i)]
            if len(subset)>len(independent) and all(p['status']=='independent_under_policy' for p in pairs if p['first'] in subset and p['second'] in subset):independent=subset
        before=next(c for c in old['categories'] if c['category']==name)
        categories.append(dict(category=name,original_passes=before['accepted'],original_attempted=2,improved_passes=len(valid),improved_attempted=4,
            independent_count=len(independent),independent_set=independent,target_met=len(independent)>=2,pairs=pairs,
            primary_coverage_range=[min(e['statistics']['primary_coverage'] for e in valid),max(e['statistics']['primary_coverage'] for e in valid)] if valid else None))
    global_flags=[]
    for i,a in enumerate(survivors):
        for b in survivors[i+1:]:
            metrics=pair_metrics(a['statistics'],b['statistics'],shapes[a['name']],shapes[b['name']]);status=classify_pair(metrics,dataset.policy)
            if status!='independent_under_policy':global_flags.append(dict(first=a['name'],second=b['name'],status=status,**metrics))
    for e in records:
        related=[p for p in global_flags if e['name'] in (p['first'],p['second'])]
        e['primary_coverage']=e.get('statistics',{}).get('primary_coverage')
        e['duplicate_status']=('geometry_rejected' if e['status']=='rejected' else
            'near_duplicate' if any(p['status']=='near_duplicate' for p in related) else
            'ambiguous' if related else 'independent_under_policy_for_screened_pairs')
        e['related_duplicate_samples']=[p['second'] if p['first']==e['name'] else p['first'] for p in related]
    result=dict(complete=True,attempted=len(records),accepted=len(survivors),rejected=len(records)-len(survivors),
        categories=categories,evidence=records,non_independent_pairs=global_flags,policy=dataset.policy,
        target_met_categories=sum(c['target_met'] for c in categories),formal_dataset_generated=False,
        initial_target_met=all(c['target_met'] for c in categories),
        remaining_categories=[c['category'] for c in categories if not c['target_met']],
        limitation='4 deterministic configurations per category; pairwise screening is not the 60-track audit. Half-turn templates repeat motifs and enforce symmetry.')
    write_json(root/'readiness.json',result)
    summary={k:v for k,v in result.items() if k!='evidence'};write_json(root/'summary.json',summary)
    with (root/'summary.csv').open('w',newline='') as handle:
        fields=('category','original_passes','original_attempted','improved_passes','improved_attempted','independent_count','target_met')
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows({k:c[k] for k in fields} for c in categories)
    assert frozen==snapshot(),'Existing pilot or V1 artifact changed'
    write_json(root/'preservation.json',dict(unchanged=True,artifact_count=len(frozen),sha256=frozen))
    print(f"Screen {len(survivors)}/{len(records)} passes; {result['target_met_categories']}/18 categories meet initial independence target",flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'generated_maps/phase5_2c_readiness')
    parser.add_argument('--diagnose-only',action='store_true');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    diagnose(ROOT/'generated_maps/phase5_2b_pilot/readiness.json',args.output)
    if not args.diagnose_only:screen(args.output)
