#!/usr/bin/env python3
"""Reference and Phase 2/3/3B comparison at explicitly recorded spatial scales."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.technical_analysis import read_centerline,analyze_geometry,wall_measurements,resample,SCALES_M,ANALYSIS_VERSION


def normalized_shape_distance(first,second):
    def normalize(points):
        _,_,lap=resample(points)
        xy,_,_=resample(points,lap/256*(1+1e-12))
        xy=xy-xy.mean(axis=0)
        z=xy[:,0]+1j*xy[:,1]
        return z/np.sqrt(np.mean(abs(z)**2))
    a,b=normalize(first),normalize(second)
    correlation=max(abs(np.vdot(a,np.roll(other,shift)))/len(a)
        for other in (b,b[::-1],b.conjugate(),b.conjugate()[::-1]) for shift in range(len(a)))
    return float(np.sqrt(max(0.,2-2*correlation)))


def collect(pilot,reference):
    entries=[]
    for name in ('Budapest','Hockenheim'):
        folder=reference/'maps'/(name+'_map');stem=name+'_map'
        entries.append((name,'reference',folder/(stem+'_centerline.csv'),folder/(stem+'_walls.csv')))
    old=json.loads((ROOT/'examples/phase2_pilot/manifest.json').read_text())
    for e in old['accepted'][::2]:
        folder=ROOT/'examples/phase2_pilot'/e['track_id']
        entries.append(('P2 '+e['target_family'] if 'target_family' in e else 'P2 '+e['family'],'phase2',
            folder/(e['track_id']+'_centerline.csv'),folder/(e['track_id']+'_walls.csv')))
    old=json.loads((ROOT/'examples/phase3_pilot/manifest.json').read_text())
    for e in old['accepted']:
        if e['variant'] not in ('two_symmetric','five_symmetric','five_asymmetric','matched_order_a'):continue
        folder=ROOT/'examples/phase3_pilot'/e['track_id']
        entries.append(('P3 '+e['variant'],'phase3',folder/(e['track_id']+'_centerline.csv'),folder/(e['track_id']+'_walls.csv')))
    for e in json.loads((pilot/'manifest.json').read_text())['accepted']:
        folder=pilot/e['track_id']
        entries.append((e['variant'],'phase3b',folder/(e['track_id']+'_centerline.csv'),folder/(e['track_id']+'_walls.csv')))
    return entries


def analyze(pilot,reference,output):
    if output.exists():raise FileExistsError('Refusing to overwrite analysis evidence')
    results=[];shapes={}
    for name,group,centerline,walls in collect(pilot,reference):
        xy=read_centerline(centerline)
        if group in ('reference','phase3b'):shapes[name]=xy
        results.append(dict(name=name,group=group,source_centerline=str(centerline.relative_to(ROOT) if centerline.is_relative_to(ROOT) else centerline.relative_to(reference)),
            centerline_sha256=hashlib.sha256(centerline.read_bytes()).hexdigest(),wall_sha256=hashlib.sha256(walls.read_bytes()).hexdigest(),
            scales=[analyze_geometry(xy,sigma_m=s) for s in SCALES_M],width_clearance=wall_measurements(xy,walls)))
        print('Analyzed '+name,flush=True)
    report=dict(analysis_version=ANALYSIS_VERSION,spatial_smoothing_sigmas_m=SCALES_M,reference_scale_m=.4,
        coordinates_only=True,uses_csv_headings=False,physical_drivability='unassessed',tracks=results)
    report['layout_shape_comparison']=dict(method='256 periodic arclength samples, centered/unit RMS radius; minimum coordinate RMS after cyclic shift, optimal rotation, reflection, reversal and uniform scaling; approximate diagnostic, not a universal duplicate proof',
        pairs=[dict(first=a,second=b,normalized_rms_distance=normalized_shape_distance(shapes[a],shapes[b]))
            for i,a in enumerate(shapes) for b in list(shapes)[i+1:]])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot',type=Path,default=ROOT/'examples/phase3b_pilot')
    p.add_argument('--marl-race-root',type=Path,default=ROOT.parent/'marl_race')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyze(a.pilot,a.marl_race_root,a.output)
