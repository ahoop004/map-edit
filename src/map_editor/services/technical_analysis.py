"""Scale-explicit, periodic coordinate analysis; never uses CSV heading fields."""
from __future__ import annotations
import csv
import math
from pathlib import Path
import numpy as np

ANALYSIS_VERSION = 'periodic_geometry_scales.v1'
SCALES_M = (0., .15, .4, .8)


def read_centerline(path):
    with Path(path).open() as handle:
        return np.array([(float(r['x']), float(r['y'])) for r in csv.DictReader(handle)])


def resample(points, spacing=.1):
    xy = np.asarray(points, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
        raise ValueError('Expected finite Nx2 coordinates')
    if len(xy)>1 and np.linalg.norm(xy[-1]-xy[0])<1e-8:
        xy=xy[:-1]
    xy=xy[np.r_[True,np.linalg.norm(np.diff(xy,axis=0),axis=1)>1e-9]]
    if len(xy)<4 or spacing<=0:
        raise ValueError('Closed analysis needs four distinct points and positive spacing')
    extended=np.vstack([xy,xy[0]])
    distances=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(extended,axis=0),axis=1))]
    lap=float(distances[-1])
    count=max(16,math.ceil(lap/spacing))
    s=np.arange(count)*lap/count
    return np.column_stack([np.interp(s,distances,extended[:,i]) for i in range(2)]),lap/count,lap


def periodic_runs(labels):
    """Return index arrays; merge the two seam pieces, including all-one labels."""
    labels=np.asarray(labels)
    cuts=np.flatnonzero(labels != np.roll(labels,1))
    if not len(cuts):
        return [np.arange(len(labels))]
    return [np.arange(a, (cuts[(i+1)%len(cuts)] + (len(labels) if i==len(cuts)-1 else 0)))%len(labels)
            for i,a in enumerate(cuts)]


def distribution(values):
    values=np.asarray(values,dtype=float)
    return dict(count=len(values),minimum=float(values.min()) if len(values) else None,
        median=float(np.median(values)) if len(values) else None,
        p90=float(np.percentile(values,90)) if len(values) else None,
        maximum=float(values.max()) if len(values) else None,values=values.tolist())


def analyze_geometry(points, *, sigma_m=.4, spacing_m=.1, straight_threshold=.025,
                     minimum_corner_length_m=.6, minimum_corner_angle_deg=15., include_profile=False):
    xy,step,raw_lap=resample(points,spacing_m)
    if not math.isfinite(sigma_m) or sigma_m<0:
        raise ValueError('Smoothing sigma must be finite and nonnegative')
    if sigma_m:
        freq=np.fft.rfftfreq(len(xy),d=step)
        kernel=np.exp(-.5*(2*math.pi*sigma_m*freq)**2)
        xy=np.fft.irfft(np.fft.rfft(xy,axis=0)*kernel[:,None],n=len(xy),axis=0)
    edges=np.roll(xy,-1,axis=0)-xy
    chords=np.linalg.norm(edges,axis=1)
    prev=np.roll(edges,1,axis=0)
    turn=np.arctan2(prev[:,0]*edges[:,1]-prev[:,1]*edges[:,0],(prev*edges).sum(axis=1))
    ds=(chords+np.roll(chords,1))/2
    k=turn/ds
    lap=float(chords.sum())
    rate=(np.roll(k,-1)-np.roll(k,1))/(2*ds)
    labels=np.where(k>straight_threshold,1,np.where(k < -straight_threshold,-1,0))
    runs=periodic_runs(labels)
    corners=[];straights=[]
    for indices in runs:
        length=float(ds[indices].sum());angle=float(turn[indices].sum())
        if labels[indices[0]]==0:
            straights.append(length)
        elif length>=minimum_corner_length_m and abs(math.degrees(angle))>=minimum_corner_angle_deg:
            corners.append(dict(start_m=float(indices[0]*step),length_m=length,
                signed_angle_deg=math.degrees(angle),mean_radius_m=length/abs(angle),
                minimum_radius_m=float(1/np.max(abs(k[indices]))),direction='left' if angle>0 else 'right'))
    signs=[1 if c['signed_angle_deg']>0 else -1 for c in corners]
    reversals=sum(a!=b for a,b in zip(signs,signs[1:]+signs[:1])) if len(signs)>1 else 0
    starts=np.array([c['start_m'] for c in corners])
    spacings=np.diff(np.r_[starts,starts[0]+raw_lap]) if len(starts) else []
    # Sustained peak: largest mean |k| over a complete 1 m window, no point spike.
    window=max(1,round(1/step))
    sustained=np.mean([np.roll(abs(k),i) for i in range(window)],axis=0)
    percentiles={str(p):float(np.percentile(abs(k),p)) for p in (50,75,90,95,99,100)}
    out=dict(analysis_version=ANALYSIS_VERSION,sigma_m=sigma_m,resampling_spacing_m=step,
        raw_lap_length_m=raw_lap,smoothed_lap_length_m=lap,
        thresholds=dict(near_straight_curvature_inv_m=straight_threshold,minimum_corner_length_m=minimum_corner_length_m,
                        minimum_corner_angle_deg=minimum_corner_angle_deg,sustained_window_m=window*step),
        curvature_abs_percentiles_inv_m=percentiles,maximum_curvature_inv_m=percentiles['100'],
        p95_curvature_inv_m=percentiles['95'],minimum_sustained_radius_m=float(1/max(sustained)),
        maximum_curvature_rate_inv_m2=float(max(abs(rate))),p95_curvature_rate_inv_m2=float(np.percentile(abs(rate),95)),
        near_straight_fraction=float(ds[labels==0].sum()/lap),straight_lengths_m=distribution(straights),
        longest_straight_m=max(straights,default=0.),corner_count=len(corners),
        corner_density_per_100m=len(corners)*100/lap,curvature_reversals=reversals,
        curvature_reversals_per_100m=reversals*100/lap,
        absolute_heading_change_rad_per_100m=float(abs(turn).sum()*100/lap),
        corner_angles_deg=distribution([abs(c['signed_angle_deg']) for c in corners]),
        corner_mean_radii_m=distribution([c['mean_radius_m'] for c in corners]),
        corner_spacing_m=distribution(spacings),shortest_significant_corner_m=min((c['length_m'] for c in corners),default=0.),
        left_corner_count=signs.count(1),right_corner_count=signs.count(-1),corners=corners)
    if include_profile:
        out['profile']=dict(s_m=(np.arange(len(k))*step).tolist(),curvature_inv_m=k.tolist(),
                            x_m=xy[:,0].tolist(),y_m=xy[:,1].tolist())
    return out


def wall_measurements(centerline,wall_csv,spacing_m=2.):
    """Normal-ray width and nearest segment distance; estimates, not clearance certification."""
    walls={}
    with Path(wall_csv).open() as handle:
        for r in csv.DictReader(handle):
            p=(float(r['x']),float(r['y']))
            if all(math.isfinite(v) for v in p): walls.setdefault(r['wall_id'],[]).append(p)
    a=[];b=[]
    for points in walls.values():
        points=np.asarray(points)
        if len(points)>1:
            a.extend(points);b.extend(np.roll(points,-1,axis=0))
    if not a:return dict(status='unavailable')
    a=np.asarray(a);b=np.asarray(b);edge=b-a;norm2=(edge*edge).sum(axis=1)
    valid=norm2>1e-16;a=a[valid];edge=edge[valid];norm2=norm2[valid]
    xy,_,_=resample(centerline,spacing_m)
    widths=[];clearances=[]
    for i,p in enumerate(xy):
        tangent=xy[(i+1)%len(xy)]-xy[(i-1)%len(xy)]
        tangent=tangent/np.linalg.norm(tangent);n=np.array([-tangent[1],tangent[0]])
        rel=a-p
        den=n[0]*edge[:,1]-n[1]*edge[:,0]
        usable=abs(den)>1e-10
        t=np.full(len(a),np.nan);u=t.copy()
        t[usable]=(rel[usable,0]*edge[usable,1]-rel[usable,1]*edge[usable,0])/den[usable]
        u[usable]=(rel[usable,0]*n[1]-rel[usable,1]*n[0])/den[usable]
        hits=t[(u>=0)&(u<=1)]
        pos=hits[hits>=0];neg=hits[hits<0]
        if len(pos) and len(neg): widths.append(float(pos.min()-neg.max()))
        fraction=np.clip((-rel*edge).sum(axis=1)/norm2,0,1)
        clearances.append(float(np.linalg.norm(rel+fraction[:,None]*edge,axis=1).min()))
    return dict(status='sampled_estimates_only',poses_sampled=len(xy),normal_ray_valid_poses=len(widths),
        normal_ray_corridor_width_m=distribution(widths),nearest_wall_clearance_m=distribution(clearances),
        method='periodic 2 m centerline samples; normal-ray segment hits and nearest wall segments; no vehicle footprint certification')
