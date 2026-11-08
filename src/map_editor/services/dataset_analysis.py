"""Dataset-level physical marginals, joint relationships and split comparison."""
import json
from pathlib import Path
import numpy as np
from .research_dataset import audit_dataset
from .technical_analysis import analyze_geometry,read_centerline,SCALES_M

FIELDS=('raw_lap_length_m','corner_count','corner_density_per_100m','minimum_sustained_radius_m',
    'p95_curvature_inv_m','maximum_curvature_inv_m','minimum_corner_angle_deg','median_corner_angle_deg','p90_corner_angle_deg',
    'longest_straight_m','curvature_reversals','left_turn_fraction','primary_coverage','supporting_fraction','active_curvature_fraction',
    'minimum_width_m','mean_width_m','width_std_m','symmetry_error_m')


def describe(values):
    a=np.asarray(values,dtype=float)
    return dict(count=len(a),minimum=float(a.min()),p25=float(np.percentile(a,25)),median=float(np.median(a)),
        p75=float(np.percentile(a,75)),maximum=float(a.max()),mean=float(a.mean()),std=float(a.std())) if len(a) else dict(count=0)


def analyze_dataset(root,output):
    root=Path(root);output=Path(output)
    if output.exists():raise FileExistsError('Refusing to overwrite scientific dataset analysis')
    integrity=audit_dataset(root,require_complete=False);entries=json.loads((root/'manifest.json').read_text())['accepted']
    tracks=[]
    for e in entries:
        xy=read_centerline(root/e['map'].replace('.yaml','_centerline.csv'))
        tracks.append(dict(slot_id=e['slot_id'],split=e['split'],generation_mode=e['generation_mode'],family=e['target_family'],
            complexity=e['complexity'],scale=e['scale'],statistics=e['statistics'],scales=[analyze_geometry(xy,sigma_m=sigma) for sigma in SCALES_M]))
    splits={split:{key:describe([e['statistics'][key] for e in entries if e['split']==split]) for key in FIELDS} for split in ('train','validation','test')}
    # Keep the immutable native statistics unchanged; expose actual variance
    # alongside standard deviation in this derived dataset analysis.
    for track in tracks:
        track['width_variance_m2']=track['statistics']['width_std_m']**2
    for split in splits:
        splits[split]['width_variance_m2']=describe([e['statistics']['width_std_m']**2 for e in entries if e['split']==split])
    marginals={key:describe([e['statistics'][key] for e in entries]) for key in FIELDS}
    marginals['width_variance_m2']=describe([e['statistics']['width_std_m']**2 for e in entries])
    joints=[]
    for e in entries:
        s=e['statistics'];joints.append(dict(slot_id=e['slot_id'],split=e['split'],family=e['target_family'] or 'composite',
            lap_m=s['raw_lap_length_m'],corners=s['corner_count'],radius_m=s['minimum_sustained_radius_m'],
            mean_width_m=s['mean_width_m'],p95_curvature_inv_m=s['p95_curvature_inv_m'],complexity=e['complexity']))
    correlations={}
    for first,second in [('raw_lap_length_m','corner_count'),('minimum_sustained_radius_m','mean_width_m')]:
        a=np.array([e['statistics'][first] for e in entries]);b=np.array([e['statistics'][second] for e in entries])
        correlations[first+'__'+second]=float(np.corrcoef(a,b)[0,1]) if min(a.std(),b.std())>1e-12 else None
    report=dict(complete=integrity['complete'],count=len(entries),quotas=integrity['quotas'],
        marginal_distributions=marginals,
        split_distributions=splits,joint_rows=joints,joint_pearson_correlations=correlations,
        per_track=tracks,policy=integrity['policy'],pairwise_similarity=integrity['pairwise_comparisons'],
        interpretation='Geometric distributions and finite-sample correlations only; no physical difficulty or controller-success labels')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report
