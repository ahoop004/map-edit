"""Twelve distinct technical requests and bounded auditable publication."""
from dataclasses import replace
import json
import math
from pathlib import Path
from time import perf_counter
from map_editor.geometry import GeometryError
from .technical_spec import TechnicalSpec,TechnicalRequest,GENERATOR_VERSION,spec_from_recipe
from .technical_tracks import prepare_technical,publish_technical,TechnicalGenerationError


def default_technical_specs(vehicle):
    patterns=[
        [90,-45,90,45,90,-60,90,60],
        [75,-35,100,70,-45,80,75,-55,60,35],
        [120,-60,90,60,75,-45,90,30],
        [90,-60,100,50,90,-75,80,75,-45,55],
        [75,-30,105,60,-60,90,90,-45,75],
        [100,-50,80,65,-35,100,-60,70,90],
        [160,-80,80,90,-70,150,-60,90],
        [180,-90,90,60,-60,180,-90,90],
        [150,-60,60,90,-60,150,-90,120],
        [60,-30,90,60,90,-45,75,60],
        [90,-30,60,75,-45,90,120],
        [100,-25,75,90,-35,60,95]]
    specs=[]
    categories=['compact_technical','irregular_mixed','corner_dense','high_speed_transitions']
    for i,angles in enumerate(patterns):
        category=categories[i//3];variant=f'{category}_{i%3+1}'
        requests=[]
        for j,angle in enumerate(angles):
            radius=(1.35+.18*((j+i)%4)) if i<3 or 6<=i<9 else (1.6+.4*((j+i)%4))
            if i>=9:
                radius=1.5 if j in (2,4) else 3.+.7*(j%3)
            ramp=.7 if radius<1.6 else .65
            params=dict(radius_m=radius,direction='left' if angle>0 else 'right')
            if abs(angle)>=150:
                family='hairpin';params.update(turn_angle_rad=math.radians(abs(angle)),entry_transition_m=ramp,exit_transition_m=ramp)
            else:
                family='kink' if abs(angle)<=35 else 'corner'
                params.update(turn_angle_deg=abs(angle),transition_m=ramp)
                if family=='corner' and j%4==1:
                    params['end_radius_m']=radius*1.5
                elif family=='corner' and j%4==3:
                    params.update(radius_m=radius*1.4,end_radius_m=radius)
                # Two separated apexes, measurable from sampled knot curvature.
                if family=='corner' and j==0 and i%3==2:
                    family='compound_corner'
                    params['apex_radii_m']=[radius*1.6,radius,radius*1.8,radius*1.1,radius*1.6]
            second_long_index=5 if i==10 else 3
            primary_straight=(3.5+(j*2+i)%4) if i<9 else (45.+5*(i-9) if j==1 else 30.+5*(i-9) if j==second_long_index else 5. if j==0 else 5.+j%3)
            requests.append(TechnicalRequest('feature_'+str(j+1),family,params,primary_straight))
        fixed=sum(r.build().length_m+r.straight_after_m for r in requests)
        lap=fixed+(28.+4*(i%3) if i<9 else 45.+7*(i%3))
        order=tuple(range(len(requests)))
        swapped=list(order);swapped[1],swapped[2]=swapped[2],swapped[1]
        third=list(order);third[-2],third[-3]=third[-3],third[-2]
        objectives=dict(corner_density_per_100m=(3.0,15.),maximum_curvature_inv_m=(.25,.9),
            p95_curvature_inv_m=(.12,.8),curvature_reversals=(2,16),near_straight_fraction=(.2,.85),
            longest_straight_m=(2.,95.),shortest_significant_corner_m=(.6,15.),
            minimum_corner_angle_deg=(15.,180.),maximum_corner_angle_deg=(40.,210.),
            symmetry_error_m=(.1,100.),repetition_fraction=(0.,.94))
        if i<3:
            objectives.update(corner_density_per_100m=(7.,15.),p95_curvature_inv_m=(.3,.8),longest_straight_m=(3.,25.))
        elif i<6:
            objectives.update(corner_density_per_100m=(5.,12.),longest_straight_m=(3.,35.))
        elif i<9:
            objectives.update(corner_density_per_100m=(6.,14.),p95_curvature_inv_m=(.35,.8),longest_straight_m=(3.,30.))
        else:
            objectives.update(corner_density_per_100m=(2.5,6.),longest_straight_m=(40.,95.),
                long_straight_to_tight_corner_count=(1,10))
        specs.append(TechnicalSpec(tuple(requests),vehicle,variant=variant,category=category,
            topology_orders=(order,tuple(swapped),tuple(third)),candidate_budget=6,seed=3100+i,
            target_lap_length_m=lap,lap_length_range_m=(lap-.5,lap+.5),objectives=objectives,
            connector_bounds_m=(.4,25. if i<9 else 45.)))
    return tuple(specs)


def generate_technical_pilot(specs,output_dir,*,reference,profile_path=None,progress=None):
    output_dir=Path(output_dir)
    if output_dir.exists(): raise FileExistsError('Refusing to overwrite technical pilot')
    if profile_path and Path(profile_path).exists(): raise FileExistsError('Refusing to overwrite technical runtime record')
    if not (Path(reference)/'src/utils/map_loader.py').is_file(): raise GeometryError('Actual marl_race reference checkout required')
    if len({s.variant for s in specs})!=len(specs): raise GeometryError('Duplicate technical pilot variant')
    output_dir.mkdir(parents=True,exist_ok=False)
    (output_dir/'pilot_recipe.json').write_text(json.dumps(dict(schema_version=1,generator=GENERATOR_VERSION,
        kind='technical_pilot',requests=[s.recipe() for s in specs]),indent=2)+'\n')
    report=dict(generator=GENERATOR_VERSION,requested_tracks=len(specs),complete=False,accepted=[],rejected=[],incomplete_requests=[])
    def save(): (output_dir/'manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();started=perf_counter();timings=[];fingerprints=set()
    for spec in specs:
        begin=perf_counter()
        try:
            prepared=prepare_technical(spec)
            identity=prepared.metadata['provenance']['identity']
            if identity['geometry_fingerprint'] in fingerprints or identity['coordinate_fingerprint'] in fingerprints:
                raise TechnicalGenerationError('Duplicate winning geometry in technical pilot',prepared.metadata['provenance']['layout_attempts'])
            preparation=perf_counter()-begin;publish_start=perf_counter()
            path=publish_technical(spec,output_dir/spec.track_id,reference=reference,prepared=prepared)
            for key in ('geometry_fingerprint','coordinate_fingerprint'):fingerprints.add(identity[key])
            report['accepted'].append(dict(variant=spec.variant,category=spec.category,track_id=spec.track_id,
                map=str(path.relative_to(output_dir)),metadata=str((path.parent/(spec.track_id+'_metadata.json')).relative_to(output_dir)),
                validation=str((path.parent/(spec.track_id+'_validation.json')).relative_to(output_dir)),identity=identity,
                statistics=prepared.statistics,layout_selection=prepared.metadata['provenance']['layout_selection']))
            for a in prepared.metadata['provenance']['layout_attempts']:
                if a['status']=='rejected':report['rejected'].append(dict(variant=spec.variant,**a))
            timings.append(dict(variant=spec.variant,preparation_seconds=preparation,publish_replay_smoke_seconds=perf_counter()-publish_start))
            if progress:progress('Accepted '+spec.variant)
        except TechnicalGenerationError as exc:
            report['incomplete_requests'].append(spec.variant)
            report['rejected'].extend(dict(variant=spec.variant,**a) for a in exc.attempts)
            if progress:progress('Rejected '+spec.variant+': '+str(exc))
        save()
    report['complete']=len(report['accepted'])==len(specs)
    report['candidate_accounting']=dict(evaluated=sum(a['layout_selection']['evaluated_candidates'] for a in report['accepted'])+
        sum(1 for a in report['rejected'] if a['variant'] in report['incomplete_requests']),
        selected=len(report['accepted']),rejected=len(report['rejected']),
        valid_not_selected=sum(a['layout_selection']['valid_candidates']-1 for a in report['accepted']))
    save()
    if profile_path:
        Path(profile_path).parent.mkdir(parents=True,exist_ok=True)
        Path(profile_path).write_text(json.dumps(dict(total_seconds=perf_counter()-started,tracks=timings),indent=2)+'\n')
    return report


def load_technical_pilot(path):
    data=json.loads(Path(path).read_text())
    if data.get('generator')!=GENERATOR_VERSION or data.get('kind')!='technical_pilot' or data.get('schema_version')!=1:
        raise GeometryError('Unsupported technical pilot recipe')
    return tuple(spec_from_recipe(d) for d in data['requests'])
