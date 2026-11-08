#!/usr/bin/env python3
"""Bounded Phase 5.2B recovery and 27-cell geometric readiness screen, no release."""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from map_editor.geometry import GeometryError
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.dataset_spec import default_dataset_spec,DatasetSlot
from map_editor.services.research_design import corrected_spec,candidate_spec
from map_editor.services.research_tracks import prepare_research,publish_research
from map_editor.services.dataset_diversity import normalized_shape,pair_metrics,classify_pair
from generate_research_diversity_pilot import CASES,statistics,report,write_json


def checksums(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def recover(root,source):
    root.mkdir(parents=True,exist_ok=True)
    if (root/'manifest.json').exists():raise FileExistsError('Corrective manifest already exists; refusing another pass')
    original=checksums(source)
    manifest=deepcopy(json.loads((source/'manifest.json').read_text()))
    manifest.update(dataset_id='phase5_2b_pilot',corrective_pass='phase5_2b',source=str(source.relative_to(ROOT)))
    manifest['recovery_rejected']=[]
    for e in manifest['accepted']:
        folder=(source/e['map']).parent
        shutil.copytree(folder,root/folder.relative_to(source))
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json')
    missing=list(manifest['missing'])
    for index,(family,scale,variant) in enumerate(CASES):
        name=f'{family}_{variant+1:02d}'
        if name not in missing:continue
        for attempt in range(1,7):
            spec=None
            try:
                spec=replace(corrected_spec(family,scale,variant,53000+index,vehicle,attempt),candidate_budget=1)
                prepared=prepare_research(spec)
                bundle=publish_research(spec,root/'tracks'/name,prepared=prepared)
                entry=dict(name=name,target_family=spec.target_family,scale=scale,track_id=spec.track_id,
                    map=str(bundle.relative_to(root)),metadata=str((bundle.parent/(spec.track_id+'_metadata.json')).relative_to(root)),
                    recipe=str((bundle.parent/(spec.track_id+'_generation.yaml')).relative_to(root)),attempt=attempt,
                    tuning_pass='phase5_2b',statistics=prepared.statistics)
                entry['comparison']=statistics(entry,prepared.metadata)
                manifest['accepted'].append(entry);manifest['missing'].remove(name)
                print(f"Recovered {name} attempt {attempt}: {prepared.statistics['raw_lap_length_m']:.0f} m, primary {prepared.statistics['primary_coverage']:.1%}",flush=True)
                break
            except (GeometryError,ValueError) as exc:
                record=dict(name=name,attempt=attempt,tuning_pass='phase5_2b',seed=spec.seed if spec else None,
                    native_recipe=spec.recipe() if spec else None,reason=str(exc),layout_attempts=getattr(exc,'attempts',[]))
                manifest['rejected'].append(record);manifest['recovery_rejected'].append(record)
                print(f"Rejected {name} {attempt}: {[r.get('reason') for r in record['layout_attempts']] or str(exc)}",flush=True)
            write_json(root/'manifest.json',manifest)
        write_json(root/'manifest.json',manifest)
    manifest['complete']=len(manifest['accepted'])==10
    order={f'{f}_{v+1:02d}':i for i,(f,s,v) in enumerate(CASES)}
    manifest['accepted'].sort(key=lambda e:order[e['name']])
    write_json(root/'manifest.json',manifest)
    report(root,manifest,ROOT/'examples/phase5_1_pilot')
    assert original==checksums(source),'Source pilot changed'
    copied={}
    for e in json.loads((source/'manifest.json').read_text())['accepted']:
        relative=(source/e['map']).parent.relative_to(source)
        assert checksums(source/relative)==checksums(root/relative)
        copied[e['name']]='byte_identical'
    write_json(root/'preservation.json',dict(source_artifact_sha256=original,copied_tracks=copied,source_unchanged=True))
    return manifest


def readiness(root):
    path=root/'readiness.json'
    if path.exists():raise FileExistsError('Readiness evidence already exists')
    vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json')
    dataset=default_dataset_spec(design_version='research_design.v2')
    cases=[('specialist',f,None,s) for f in ('straight','hairpin','sweeper','chicane','s_curve') for s in ('short','medium','long')]
    cases += [('composite',None,c,s) for c in (2,3,4,5) for s in ('short','medium','long')]
    evidence=[];categories=[];shapes={};successes=[]
    for index,(mode,family,complexity,scale) in enumerate(cases):
        label=f'{family or "composite_"+str(complexity)}_{scale}'
        slot=DatasetSlot('readiness_'+label,'train',mode,family,complexity,scale,61000+index,'readiness_lineage_'+label)
        records=[]
        # Two independent root seeds; distinct candidate attempts also exercise
        # strategy fallback. This is 54 preparations, zero published bundles.
        for replicate in (1,2):
            spec=None
            trial=replace(dataset,root_seed=20261120+replicate)
            try:
                spec=candidate_spec(trial,slot,replicate,vehicle)
                prepared=prepare_research(spec);s=prepared.statistics
                shape=normalized_shape([(p.x,p.y) for p in prepared.sampled.states[:-1]])
                key=f'{label}_{replicate}';shapes[key]=shape
                record=dict(category=label,replicate=replicate,status='accepted',native_recipe=spec.recipe(),
                    statistics=s,identity=prepared.metadata['provenance']['identity'],
                    layout_attempts=prepared.metadata['provenance']['layout_attempts'],sample_id=key)
                successes.append(record)
            except (GeometryError,ValueError) as exc:
                record=dict(category=label,replicate=replicate,status='rejected',
                    native_recipe=spec.recipe() if spec else None,reason=str(exc),layout_attempts=getattr(exc,'attempts',[]))
            records.append(record);evidence.append(record)
            print(f"Readiness {label} {replicate}: {record['status']}"+(f": {[r.get('reason') for r in record['layout_attempts']]}" if record['status']=='rejected' else ''),flush=True)
        accepted=[r for r in records if r['status']=='accepted']
        category=dict(category=label,mode=mode,family=family,complexity=complexity,scale=scale,
            accepted=len(accepted),attempted=2,low_acceptance=len(accepted)<2,diversity='insufficient_successes')
        if len(accepted)==2:
            a,b=accepted;metrics=pair_metrics(a['statistics'],b['statistics'],shapes[a['sample_id']],shapes[b['sample_id']])
            category.update(diversity=classify_pair(metrics,dataset.policy),pair_metrics=metrics)
        categories.append(category)
        write_json(path,dict(complete=False,categories=categories,evidence=evidence))
    pairs=[]
    for i,a in enumerate(successes):
        for b in successes[i+1:]:
            metrics=pair_metrics(a['statistics'],b['statistics'],shapes[a['sample_id']],shapes[b['sample_id']])
            status=classify_pair(metrics,dataset.policy)
            if status!='independent_under_policy':pairs.append(dict(first=a['sample_id'],second=b['sample_id'],status=status,**metrics))
    result=dict(complete=True,scope='54 geometric preparations across 27 categories; no publication or native replay',
        attempted=len(evidence),accepted=len(successes),rejected=len(evidence)-len(successes),categories=categories,
        low_acceptance_categories=[c['category'] for c in categories if c['low_acceptance']],
        non_independent_pairs=pairs,policy=dataset.policy,evidence=evidence,
        readiness='not_established' if any(c['low_acceptance'] for c in categories) or pairs else 'small_screen_passed',
        limitation='Two draws per category do not establish 60-track success or split independence. This is not the formal dataset audit.')
    write_json(path,result)
    summary={k:v for k,v in result.items() if k!='evidence'}
    summary['diversity_flags']=dict(Counter(p['status'] for p in pairs))
    write_json(root/'readiness_summary.json',summary)
    with (root/'readiness_summary.csv').open('w',newline='') as handle:
        fields=('category','mode','family','complexity','scale','accepted','attempted','low_acceptance','diversity')
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        writer.writerows({k:c[k] for k in fields} for c in categories)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'generated_maps/phase5_2b_pilot')
    parser.add_argument('--source',type=Path,default=ROOT/'generated_maps/phase5_2_pilot')
    parser.add_argument('--readiness-only',action='store_true')
    args=parser.parse_args()
    if not args.readiness_only:recover(args.output,args.source)
    readiness(args.output)
