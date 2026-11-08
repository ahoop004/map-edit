#!/usr/bin/env python3
"""Development-only specialist readiness and near-duplicate calibration; offline."""
from dataclasses import replace
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.dataset_spec import default_dataset_spec,SCALES
from map_editor.services.research_design import candidate_spec
from map_editor.services.research_tracks import prepare_research,ResearchGenerationError
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.services.specialist_templates import FAMILIES
from map_editor.services.dataset_diversity import normalized_shape,shape_distance,pair_metrics,classify_pair
from map_editor.services.technical_analysis import read_centerline


def readiness(output):
    if output.exists():raise FileExistsError('Refusing to overwrite readiness evidence')
    dataset=default_dataset_spec();vehicle=load_vehicle_snapshot(ROOT/'profiles/f110_resolved_phase3b.json');entries=[]
    for family in FAMILIES:
        base=next(s for s in dataset.slots if s.family==family and s.split=='train')
        for scale in SCALES:
            slot=replace(base,scale=scale);rejected=[]
            for attempt in range(1,7):
                spec=candidate_spec(dataset,slot,attempt,vehicle)
                try:p=prepare_research(spec)
                except ResearchGenerationError as exc:rejected.append(dict(attempt=attempt,reason=str(exc),decisions=exc.attempts));continue
                entries.append(dict(family=family,scale=scale,status='passed',recipe=spec.recipe(),
                    measured=p.statistics,classification_checks=len(p.metadata['maneuvers']),rejected=rejected,
                    footprint=p.metadata['provenance']['validation']['raster_footprint']))
                print('Ready '+family+' '+scale,flush=True);break
            else:entries.append(dict(family=family,scale=scale,status='failed',rejected=rejected))
    report=dict(kind='development_specialist_readiness',formal_dataset=False,complete=all(e['status']=='passed' for e in entries),cases=entries)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if not report['complete']:raise ValueError('Specialist readiness incomplete')


def calibrate(output):
    if output.exists():raise FileExistsError('Refusing to overwrite frozen calibration')
    dataset=default_dataset_spec();policy=dataset.policy;root=ROOT/'examples/phase4b_pilot';manifest=json.loads((root/'manifest.json').read_text())
    tracks=[];points={};shapes={};pairs=[]
    for e in manifest['accepted']:
        metadata=json.loads((root/e['metadata']).read_text());path=(root/e['map']).parent/metadata['artifacts']['centerline']
        xy=read_centerline(path);points[e['variant']]=xy;shapes[e['variant']]=normalized_shape(xy)
        stats=dict(e['statistics']);stats['primary_family_exposure_fractions']={}
        for a in metadata['maneuvers']:
            if a['requested']['composition_role']=='primary':stats['primary_family_exposure_fractions'][a['type']]=stats['primary_family_exposure_fractions'].get(a['type'],0)+a['length_m']/stats['raw_lap_length_m']
        tracks.append(dict(name=e['variant'],statistics=stats,source_centerline_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    for i,a in enumerate(tracks):
        for b in tracks[i+1:]:
            m=pair_metrics(a['statistics'],b['statistics'],shapes[a['name']],shapes[b['name']]);pairs.append(dict(first=a['name'],second=b['name'],status=classify_pair(m,policy),**m))
    name=tracks[0]['name'];xy=points[name];theta=.73;rot=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
    variants=dict(translation=xy+[50,-20],rotation=xy@rot.T,reflection=xy*[-1,1],reversal=xy[::-1],seam_shift=np.roll(xy,170,axis=0),width_only=xy.copy())
    checks=[]
    for variant,value in variants.items():
        d=shape_distance(shapes[name],normalized_shape(value));checks.append(dict(transform=variant,normalized_distance=d,accepted_as_independent=False))
        if d>.01:raise AssertionError('Forbidden representation not recognized: '+variant)
    report=dict(version=policy['version'],policy=policy,frozen_before_formal_generation=True,
        calibration_sources='checked-in Phase 4B development pilot and forbidden representation transformations; no held-out formal validation/test candidates',
        rationale='Conservative conjunction of shape (<0.055), physical length (<15%), sustained radius (<20%) and primary exposure L1 (<0.25); ambiguous band (<0.085) also requires close length/p95 curvature, exposure and corner counts. Both classes reject globally. Large physical scale/severity differences can establish independence despite similar normalized shape.',
        sources=[dict(name=t['name'],centerline_sha256=t['source_centerline_sha256']) for t in tracks],
        development_pairs=pairs,forbidden_transform_checks=checks)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['readiness','calibrate']);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();(readiness if a.command=='readiness' else calibrate)(a.output)
