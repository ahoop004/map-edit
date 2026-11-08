"""Offline multiscale measurements and normalized layout diversity diagnostics."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from .technical_analysis import analyze_geometry,read_centerline,resample,SCALES_M,ANALYSIS_VERSION


def shape_distance(first,second):
    def normalize(points):
        _,_,length=resample(points)
        xy,_,_=resample(points,length/256*(1+1e-12));xy-=xy.mean(axis=0)
        z=xy[:,0]+1j*xy[:,1]
        return z/np.sqrt(np.mean(abs(z)**2))
    a,b=normalize(first),normalize(second)
    correlation=max(abs(np.vdot(a,np.roll(other,i)))/len(a)
        for other in (b,b[::-1],b.conjugate(),b.conjugate()[::-1]) for i in range(len(a)))
    return float(np.sqrt(max(0.,2-2*correlation)))


def analyze_extended_pilot(root,output):
    root=Path(root);output=Path(output)
    if output.exists():raise FileExistsError('Refusing to overwrite extended analysis')
    manifest=json.loads((root/'manifest.json').read_text());tracks=[];shapes={}
    for entry in manifest['accepted']:
        folder=(root/entry['map']).parent;metadata=json.loads((root/entry['metadata']).read_text())
        centerline=folder/metadata['artifacts']['centerline'];xy=read_centerline(centerline)
        shapes[entry['variant']]=xy
        tracks.append(dict(variant=entry['variant'],category=entry['category'],
            centerline_sha256=hashlib.sha256(centerline.read_bytes()).hexdigest(),
            centerline_fingerprint=entry['identity']['centerline_fingerprint'],
            scales=[analyze_geometry(xy,sigma_m=sigma) for sigma in SCALES_M],
            width_statistics={k:v for k,v in entry['statistics'].items() if 'width' in k},
            geometry_statistics=entry['statistics'],
            geometric_validation=metadata['provenance']['validation']))
    names=list(shapes)
    pairs=[dict(first=a,second=b,normalized_shape_distance=shape_distance(shapes[a],shapes[b]))
        for i,a in enumerate(names) for b in names[i+1:]]
    report=dict(analysis_version=ANALYSIS_VERSION,scales_m=list(SCALES_M),acceptance_scale_m=.4,
        physical_drivability='unassessed',integration='not_run_offline',tracks=tracks,
        normalized_shape_method='256 periodic source-arclength samples; unit RMS radius, optimal rotation, cyclic shift, reflection and reversal; approximate diagnostic without a certified duplicate threshold',
        shape_pairs=pairs,matched_pairs=manifest['matched_pairs'])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
