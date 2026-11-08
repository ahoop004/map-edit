"""Frozen geometric independence screen, with fast exact cyclic correlations."""
import math
import numpy as np
from .technical_analysis import resample


def normalized_shape(points):
    xy=np.asarray(points,dtype=float)
    _,_,lap=resample(xy)
    xy,_,_=resample(xy,lap/256*(1+1e-12));xy-=xy.mean(axis=0)
    z=xy[:,0]+1j*xy[:,1];z/=np.sqrt(np.mean(abs(z)**2))
    return np.array([np.fft.fft(v) for v in (z,z[::-1],z.conjugate(),z.conjugate()[::-1])])


def shape_distance(first,second):
    # Unit-RMS complex points; maximize cyclic cross correlation magnitude to
    # remove optimal planar rotation, reflection, reversal and seam location.
    correlation=np.fft.ifft(first[0][None,:]*np.conjugate(second),axis=1)/first.shape[1]
    return float(np.sqrt(max(0.,2-2*float(abs(correlation).max()))))


def relative(a,b):return abs(a-b)/max(abs(a),abs(b),1e-12)


def pair_metrics(first,second,first_shape,second_shape):
    families=sorted(set(first['primary_family_exposure_fractions'])|set(second['primary_family_exposure_fractions']))
    return dict(normalized_shape_distance=shape_distance(first_shape,second_shape),
        relative_length=relative(first['raw_lap_length_m'],second['raw_lap_length_m']),
        relative_sustained_radius=relative(first['minimum_sustained_radius_m'],second['minimum_sustained_radius_m']),
        relative_p95_curvature=relative(first['p95_curvature_inv_m'],second['p95_curvature_inv_m']),
        family_exposure_l1=sum(abs(first['primary_family_exposure_fractions'].get(f,0)-second['primary_family_exposure_fractions'].get(f,0)) for f in families),
        corner_count_difference=abs(first['corner_count']-second['corner_count']))


def classify_pair(metrics,policy):
    if (metrics['normalized_shape_distance']<policy['normalized_shape_threshold'] and
        metrics['relative_length']<policy['relative_length_threshold'] and
        metrics['relative_sustained_radius']<policy['relative_radius_threshold'] and
        metrics['family_exposure_l1']<policy['family_exposure_l1_threshold']):return 'near_duplicate'
    if (metrics['normalized_shape_distance']<policy['ambiguous_shape_threshold'] and
        metrics['relative_length']<policy['ambiguous_relative_length_threshold'] and
        metrics['relative_p95_curvature']<policy['ambiguous_relative_curvature_threshold'] and
        metrics['family_exposure_l1']<policy['ambiguous_family_exposure_l1_threshold'] and metrics['corner_count_difference']<=1):return 'ambiguous'
    return 'independent_under_policy'


def screen(prepared,accepted,shape_cache,policy):
    from .technical_analysis import read_centerline
    identity=prepared.metadata['provenance']['identity'];shape=normalized_shape([(p.x,p.y) for p in prepared.sampled.states[:-1]])
    comparisons=[]
    for entry in accepted:
        other=entry['identity']
        if identity['centerline_fingerprint']==other['centerline_fingerprint'] or identity['coordinate_fingerprint']==other['coordinate_fingerprint']:
            return False,dict(status='exact_duplicate',related_slot=entry['slot_id']),shape
        m=pair_metrics(prepared.statistics,entry['statistics'],shape,shape_cache[entry['slot_id']]);status=classify_pair(m,policy)
        comparisons.append(dict(related_slot=entry['slot_id'],related_split=entry['split'],status=status,**m))
        if status!='independent_under_policy':return False,comparisons[-1],shape
    closest=min(comparisons,key=lambda p:p['normalized_shape_distance']) if comparisons else None
    return True,dict(status='accepted',compared_layouts=len(comparisons),closest_shape=closest),shape
