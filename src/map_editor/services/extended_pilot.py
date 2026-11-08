"""Offline long-track and width-pair requests, publication and partial manifests."""
from dataclasses import replace
from copy import deepcopy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from time import perf_counter
from map_editor.geometry import GeometryError
from map_editor.geometry.width_profile import WidthProfile
from .technical_spec import TechnicalRequest
from .extended_spec import ExtendedSpec,SupportingTurn,LayoutTopology,GENERATOR_VERSION,spec_from_recipe


def _requests_for_groups(groups,index,mixed):
    requests=[];ends=[]
    for group,angles in enumerate(groups):
        for j,angle in enumerate(angles):
            radius=(1.6+.35*((index+group+j)%5)) if not mixed else (2.+.45*((index+j)%3) if angle<0 else 3.5+.7*((index+group+j)%5))
            params=dict(radius_m=radius,turn_angle_deg=abs(angle),direction='left' if angle>0 else 'right',transition_m=.75)
            family='kink' if abs(angle)<=35 else 'corner'
            if family=='corner' and (index+group+j)%4==1:params['end_radius_m']=radius*1.4
            elif family=='corner' and (index+group+j)%4==2:params.update(radius_m=radius*1.35,end_radius_m=radius)
            if family=='corner' and group==2 and j==0 and index%2:
                family='compound_corner';params['apex_radii_m']=[radius*1.5,radius,radius*1.7,radius*1.1,radius*1.5]
            fixed=(26.+4*index+3*(group%2)) if j==len(angles)-1 else (3.+(group+j+index)%4 if not mixed else 7.+(group*2+j)%6)
            requests.append(TechnicalRequest(f'cluster_{group+1}_turn_{j+1}',family,params,fixed))
        ends.append(len(requests)-1)
    return tuple(requests),ends


def _topologies(inventory,ends,variant):
    n=len(inventory);order=tuple(range(n))
    radius=5.+.5*(variant%3)
    turns=lambda slots:tuple(SupportingTurn(i,(12.,55.),radius,.7) for i in slots)
    shifted=[max(0,i-1) for i in ends]
    # Noncyclic permutation of the four explicit cluster blocks.
    cuts=[0]+[i+1 for i in ends];blocks=[list(range(a,b)) for a,b in zip(cuts,cuts[1:])]
    reordered=tuple(i for g in (0,2,1,3) for i in blocks[g])
    return (LayoutTopology('cluster_exits',order,turns(ends)),
            LayoutTopology('inside_clusters',order,turns(shifted)),
            LayoutTopology('reordered_clusters',reordered,turns(ends)))


def default_extended_specs(vehicle):
    specs=[]
    triples=[[100,-70,40],[80,-55,45],[110,-75,35],[90,-60,40]]
    quads=[[70,-45,80,-35],[95,-55,65,-35],[60,-40,100,-50],[85,-30,55,-40]]
    for mixed in (False,True):
        for i,target in enumerate((310.,345.,385.,425.)):
            groups=[list(g) for g in (triples if mixed else quads)]
            # Different significant-region counts without manufactured reflections.
            if not mixed and i<2:
                groups=[list(triples[j]) if j>=2*i else list(quads[j]) for j in range(4)]
            if mixed and i>=2:groups[1]=list(quads[1]);groups[3]=list(quads[3])
            # Vary the primary total: supporting turns supply the exact deficit.
            adjustment=(-5 if i==0 else 5 if i==2 else 0)
            for g in groups:g[0]+=adjustment
            if mixed:
                changes=((35,-35,10,-10),(20,-20,-30,30),(25,-45,30,-10))
                if i<3:
                    for g,change in zip(groups,changes[i]):g[0]+=change
                else:
                    groups=[[130,-20,40],[-60,100,-50],[100,-20,70],[45,-100,45]]
            elif i==3:
                for g,change in zip(groups,(20,-25,10,-5)):g[0]+=change
            inventory,ends=_requests_for_groups(groups,i,mixed)
            if i in (1,2) or mixed:
                scales=((.5,1.5,.6,1.4) if i==1 else (1.7,.45,1.5,.35) if i==2
                        else (1.2,.8,1.1,.9) if i==0 else (1.4,.6,1.3,.7))
                updated=list(inventory)
                for group,end in enumerate(ends):
                    updated[end]=replace(updated[end],straight_after_m=updated[end].straight_after_m*scales[group])
                inventory=tuple(updated)
            category='long_irregular_mixed' if mixed else 'long_technical'
            objectives=dict(corner_count=(12,20),corner_density_per_100m=(2.8,7.),
                p95_curvature_inv_m=(.1,.75),curvature_reversals=(6,20),
                near_straight_fraction=(.25,.88),symmetry_error_m=(.5,150.),repetition_fraction=(0.,.88),
                longest_straight_m=(15.,95.),shortest_significant_corner_m=(.6,25.),
                left_turn_fraction=(.3,.85))
            specs.append(ExtendedSpec(inventory,vehicle,_topologies(inventory,ends,i),target_lap_length_m=target,
                lap_length_range_m=(300.,450.),variant=f'{category}_{i+1}',category=category,
                objectives=objectives,seed=4100+(10 if mixed else 0)+i))
    # Each pair's centerline settings are exactly identical; only width/identity change.
    for i in range(2):
        groups=[list(g) for g in triples]
        inventory,ends=_requests_for_groups(groups,i+1,False)
        target=260.+20*i
        base=ExtendedSpec(inventory,vehicle,_topologies(inventory,ends,i),target_lap_length_m=target,
            lap_length_range_m=(250.,290.),seed=4200+i,category='width_comparison',matched_group=f'width_pair_{i+1}',
            objectives=dict(corner_count=(12,20),primary_coverage=(.6,1.),symmetry_error_m=(.2,150.)),
            variant=f'width_pair_{i+1}_uniform',width=WidthProfile.constant(1.5))
        specs.append(base)
        if i==0:
            width=WidthProfile(((0.,.9),(.2,1.1),(.4,.58),(.55,.58),(.75,.95),(1.,.9)),
                ((0.,.9),(.2,1.05),(.4,.62),(.55,.62),(.75,1.1),(1.,.9)))
        else:
            width=WidthProfile(((0.,.7),(.15,.55),(.3,.55),(.55,1.2),(.8,.85),(1.,.7)),
                ((0.,1.1),(.15,.6),(.3,.6),(.55,.95),(.8,1.2),(1.,1.1)))
        specs.append(replace(base,variant=f'width_pair_{i+1}_variable',width=width))
    return tuple(specs)


def load_extended_pilot(path):
    data=json.loads(Path(path).read_text())
    if data.get('generator')!=GENERATOR_VERSION or data.get('kind')!='extended_pilot' or data.get('schema_version')!=1:
        raise GeometryError('Unsupported extended pilot recipe')
    return tuple(spec_from_recipe(s) for s in data['requests'])


def generate_extended_pilot(specs,output_dir,*,profile_path=None,progress=None):
    from .extended_tracks import prepare_extended,publish_extended,ExtendedGenerationError
    output_dir=Path(output_dir)
    if output_dir.exists():raise FileExistsError('Refusing to overwrite extended pilot')
    if profile_path and Path(profile_path).exists():raise FileExistsError('Refusing to overwrite extended runtime record')
    if len({s.variant for s in specs})!=len(specs):raise GeometryError('Duplicate extended pilot variant')
    output_dir.mkdir(parents=True,exist_ok=False)
    (output_dir/'pilot_recipe.json').write_text(json.dumps(dict(schema_version=1,generator=GENERATOR_VERSION,
        kind='extended_pilot',requests=[s.recipe() for s in specs]),indent=2)+'\n')
    report=dict(generator=GENERATOR_VERSION,requested_tracks=len(specs),complete=False,
        integration=dict(status='not_run',reason='offline_geometry_scope'),accepted=[],rejected=[],incomplete_requests=[],request_failures=[],matched_pairs=[])
    timings=[];seen={};pairs={};all_attempts=[];started=perf_counter()
    def save(): (output_dir/'manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    for spec in specs:
        profile=dict(variant=spec.variant);begin=perf_counter();prepared=None
        try:
            prepared=prepare_extended(spec,profile=profile)
            identity=prepared.metadata['provenance']['identity'];fingerprint=identity['centerline_fingerprint']
            if fingerprint in seen and (spec.matched_group is None or seen[fingerprint]!=spec.matched_group):
                raise ExtendedGenerationError('Duplicate centerline outside an explicitly matched width pair',prepared.metadata['provenance']['layout_attempts'])
            buffer=io.StringIO(newline='');writer=csv.writer(buffer)
            writer.writerow(['x','y','theta','velocity'])
            writer.writerows([f'{p.x:.6f}',f'{p.y:.6f}',f'{p.theta:.6f}',''] for p in prepared.geometry.samples)
            center_hash=hashlib.sha256(buffer.getvalue().encode()).hexdigest()
            if spec.matched_group in pairs:
                first=pairs[spec.matched_group]
                if first['centerline_sha256']!=center_hash or first['width_sha256']==identity['width_sha256']:
                    raise ExtendedGenerationError('Matched pair must preserve centerline bytes and change width',prepared.metadata['provenance']['layout_attempts'])
            path=publish_extended(spec,output_dir/spec.track_id,prepared=prepared,profile=profile)
            if spec.matched_group:
                centerline=path.parent/(spec.track_id+'_centerline.csv')
                if hashlib.sha256(centerline.read_bytes()).hexdigest()!=center_hash:
                    raise GeometryError('Exported centerline differs from the matched-pair preflight')
                if spec.matched_group in pairs:
                    first=pairs[spec.matched_group]
                    if first['centerline_sha256']!=center_hash or first['width_sha256']==identity['width_sha256']:
                        raise GeometryError('Width comparison must preserve exact centerline bytes and change width')
                    report['matched_pairs'].append(dict(group=spec.matched_group,
                        tracks=[first['track_id'],spec.track_id],centerline_sha256=center_hash,
                        centerline_byte_identical=True,width_specifications_distinct=True,
                        width_sha256=[first['width_sha256'],identity['width_sha256']]))
                else:pairs[spec.matched_group]=dict(centerline_sha256=center_hash,track_id=spec.track_id,width_sha256=identity['width_sha256'])
            report['accepted'].append(dict(variant=spec.variant,category=spec.category,track_id=spec.track_id,
                map=str(path.relative_to(output_dir)),metadata=str((path.parent/(spec.track_id+'_metadata.json')).relative_to(output_dir)),
                recipe=str((path.parent/(spec.track_id+'_generation.yaml')).relative_to(output_dir)),
                validation=str((path.parent/(spec.track_id+'_validation.json')).relative_to(output_dir)),
                identity=identity,statistics=prepared.statistics,layout_selection=prepared.metadata['provenance']['layout_selection']))
            seen[fingerprint]=spec.matched_group
            for attempt in prepared.metadata['provenance']['layout_attempts']:
                if attempt['status']=='rejected':report['rejected'].append(dict(variant=spec.variant,**attempt))
            all_attempts.extend(prepared.metadata['provenance']['layout_attempts'])
            if progress:progress('Accepted '+spec.variant)
        except ExtendedGenerationError as exc:
            report['incomplete_requests'].append(spec.variant)
            report['request_failures'].append(dict(variant=spec.variant,reason=str(exc)))
            for a in exc.attempts:
                if a['status']=='selected':a.update(status='rejected',failure_stage='pilot',reason=str(exc))
            report['rejected'].extend(dict(variant=spec.variant,**a) for a in exc.attempts if a['status']=='rejected')
            all_attempts.extend(exc.attempts)
            if progress:progress('Rejected '+spec.variant+': '+str(exc))
        except (GeometryError,OSError) as exc:
            report['incomplete_requests'].append(spec.variant)
            report['request_failures'].append(dict(variant=spec.variant,failure_stage='publication',reason=str(exc)))
            if prepared is not None:
                attempts=deepcopy(prepared.metadata['provenance']['layout_attempts'])
                for attempt in attempts:
                    if attempt['status']=='selected':attempt.update(status='rejected',failure_stage='publication',reason=str(exc))
                all_attempts.extend(attempts)
                report['rejected'].extend(dict(variant=spec.variant,**a) for a in attempts if a['status']=='rejected')
            if progress:progress('Publication failed '+spec.variant+': '+str(exc))
        profile['request_total_seconds']=perf_counter()-begin;timings.append(profile);save()
    counts={}
    for attempt in all_attempts:
        counts[attempt['status']]=counts.get(attempt['status'],0)+1
    report['candidate_accounting']=counts
    groups={s.matched_group for s in specs if s.matched_group}
    report['complete']=len(report['accepted'])==len(specs) and len(report['matched_pairs'])==len(groups)
    save()
    if profile_path:
        Path(profile_path).parent.mkdir(parents=True,exist_ok=True)
        Path(profile_path).write_text(json.dumps(dict(total_seconds=perf_counter()-started,tracks=timings),indent=2)+'\n')
    return report
