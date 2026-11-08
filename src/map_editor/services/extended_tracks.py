"""Standalone long-track acceptance, variable corridors and immutable native replay."""
from copy import deepcopy
from dataclasses import asdict,dataclass,replace
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from time import perf_counter
import numpy as np
from map_editor.geometry import GeometryError,GeometrySequence,Maneuver
from map_editor.geometry.measurement import validate_maneuver,position_curvatures
from map_editor.geometry.technical import TechnicalManeuver,validate_technical
from map_editor.geometry.corridor import variable_boundaries,validate_corridor,validate_raster_corridor
from map_editor.geometry.spatial import self_intersects
from map_editor.models.annotations import Point2D,Pose2D,SpawnPoint
from map_editor.exporters.centerline import CenterlineSample
from .procedural_track import (TrackSpec,TrackGeometry,TrackSpecError,_validate_spec,_validate_corridor_raster)
from .offline_export import rasterize_corridor,export_offline
from .geometry_metadata import build_geometry_metadata,validate_geometry_metadata
from .track_profile import profile_metrics
from .yaml_serializer import load_map_yaml,dump_map_yaml
from .composite_statistics import (interval,contains,ordered_annotations,halfturn_symmetry_error,
    curvature_profile_fingerprint,coordinate_fingerprint)
from .technical_analysis import analyze_geometry
from .specialist_templates import canonical_hash
from .extended_spec import GENERATOR_VERSION,WIDTH_METRICS,load_extended_spec,spec_from_recipe
from .extended_layout import extended_candidates


class ExtendedGenerationError(GeometryError):
    def __init__(self,message,attempts):super().__init__(message);self.attempts=deepcopy(attempts)


@dataclass
class CenterlineResult:
    sampled: object
    items: tuple
    annotations: list
    statistics: dict
    validation: dict
    solution: dict
    score: float
    fingerprint: str


@dataclass
class PreparedExtended:
    settings: object
    geometry: object
    metadata: dict
    sampled: object
    items: tuple
    statistics: dict
    raster: tuple


def evaluate_objectives(spec,stats,*,width=False):
    requested={k:v for k,v in spec.objectives.items() if (k in WIDTH_METRICS)==width}
    if not width:
        for key,bounds in dict(raw_lap_length_m=spec.lap_length_range_m,
            primary_coverage=(spec.minimum_primary_coverage,1.),supporting_fraction=(0.,spec.maximum_supporting_fraction)).items():
            existing=requested.get(key,bounds);requested[key]=(max(bounds[0],existing[0]),min(bounds[1],existing[1]))
    measured={key:stats[key] for key in requested}
    failures=[dict(metric=k,requested=list(v),measured=measured[k]) for k,v in requested.items() if not v[0]-1e-7<=measured[k]<=v[1]+1e-7]
    evaluation=dict(requested_targets={k:list(v) for k,v in requested.items()},measured_outcomes=measured,failures=failures)
    return evaluation


def _rotate(sampled,index):
    states=sampled.states[:-1];offset=states[index].s;length=sampled.length_m
    turn=sampled.states[-1].heading-states[0].heading
    order=list(range(index,len(states)))+list(range(index))
    values=[replace(states[i],s=states[i].s-offset+(length if i<index else 0),
        heading=states[i].heading+(turn if i<index else 0)) for i in order]
    values.append(replace(values[0],s=length,heading=values[0].heading+turn))
    return replace(sampled,states=tuple(values),spans=(),maneuvers=())


def _measured(item,states):
    m=item.maneuver
    measured=validate_technical(m,states) if isinstance(m,TechnicalManeuver) else validate_maneuver(m,states)
    if 'source_type' in m.requested:
        p=m.requested
        source=Maneuver(p['source_type'],m.direction,m.segments,p['source_parameters'])
        measured['source_primitive_acceptance']=validate_maneuver(source,states)
    measured.update(start_curvature_rate_inv_m2=m.segments[0].at(0).curvature_rate,
        end_curvature_rate_inv_m2=m.segments[-1].at(m.segments[-1].length_m).curvature_rate)
    return measured


def _centerline_result(spec,candidate):
    source=GeometrySequence([i.maneuver for i in candidate.items],frame=candidate.frame,require_g2=True).sample(spec.spacing_m,closed=True)
    if abs(source.states[-1].heading-source.states[0].heading-math.tau)>1e-7:
        raise GeometryError('Source full-lap winding must be +2 pi')
    curvature=np.array([p.curvature for p in source.states]);rate=max(abs(p.curvature_rate) for p in source.states)
    rate=max(rate,max(abs(b.curvature-a.curvature)/(b.s-a.s) for a,b in zip(source.states,source.states[1:])))
    peak=max(abs(curvature))
    if peak>1/spec.limits.minimum_radius_m+1e-9:raise GeometryError('Source radius below explicit minimum')
    if rate>spec.limits.maximum_curvature_rate_inv_m2:raise GeometryError('Source curvature rate exceeds explicit maximum')
    if max(abs(spec.vehicle.lr_m*curvature))>=1:raise GeometryError('Curvature outside resolved vehicle kinematic domain')
    steering=np.arctan((spec.vehicle.lf_m+spec.vehicle.lr_m)*curvature/np.sqrt(1-(spec.vehicle.lr_m*curvature)**2))
    if min(steering)<spec.vehicle.steering_min_rad or max(steering)>spec.vehicle.steering_max_rad:
        raise GeometryError('Geometric steering exceeds saved vehicle bounds')
    states=tuple(replace(p,x=round(p.x,6),y=round(p.y,6)) for p in source.states)
    states=(*states[:-1],replace(states[-1],x=states[0].x,y=states[0].y));source=replace(source,states=states)
    if self_intersects(source.points,closed=True):raise GeometryError('Quantized centerline self-intersects')
    xy=np.array([(p.x,p.y) for p in states]);edges=np.diff(xy,axis=0)
    previous=np.roll(edges,1,axis=0)
    polygon_winding=float(np.arctan2(previous[:,0]*edges[:,1]-previous[:,1]*edges[:,0],(previous*edges).sum(axis=1)).sum())
    if abs(polygon_winding-math.tau)>1e-7:raise GeometryError('Exported full-lap winding is invalid')
    s=np.r_[0.,np.cumsum(np.linalg.norm(edges,axis=1))];lap=float(s[-1]);requested=spec.seam_offset_m%source.length_m
    seam=min(range(len(states)-1),key=lambda i:min(abs(states[i].s-requested),source.length_m-abs(states[i].s-requested)))
    annotations=[]
    for i,(item,(start,end)) in enumerate(zip(candidate.items,source.spans)):
        measured=_measured(item,states[start:end+1]);length=float(s[end]-s[start])
        if item.role=='primary' and item.maneuver.type!='straight' and length<spec.minimum_useful_corner_m:
            raise GeometryError('Final primary turn below requested useful length')
        annotations.append(dict(id=f'maneuver_{i+1:03d}',type=item.maneuver.type,direction=item.maneuver.direction,
            **interval(float(s[start]-s[seam]),length,lap),requested=dict(item.maneuver.requested,
                composition_role=item.role,inventory_name=item.request_name,inventory_index=item.inventory_index,
                adjustable_connector=item.adjustable),measured=measured,difficulty={'label':'unrated'}))
    sampled=_rotate(source,seam);points=sampled.points
    stats=analyze_geometry([(p.x,p.y) for p in points],sigma_m=.4,include_profile=True)
    k=np.array(stats.pop('profile')['curvature_inv_m']);k-=k.mean();denom=float(k@k)
    repetition=max(0.,min(1.,max(float(k@np.roll(k,round(len(k)/n)))/denom for n in (2,3,4)))) if denom else 1.
    angles=[abs(c['signed_angle_deg']) for c in stats['corners']]
    total_turn=sum(angles);left_turn=sum(abs(c['signed_angle_deg']) for c in stats['corners'] if c['direction']=='left')
    primary=sum(a['length_m'] for a in annotations if a['requested']['composition_role']=='primary')/lap
    stats.update(primary_coverage=primary,supporting_fraction=1-primary,
        primary_family_count=len({i.maneuver.type for i in candidate.items if i.role=='primary'}),
        family_exposure_fractions={kind:sum(a['length_m'] for a in annotations if a['type']==kind)/lap for kind in sorted({a['type'] for a in annotations})},
        left_turn_fraction=left_turn/total_turn if total_turn else 0.,
        minimum_corner_angle_deg=min(angles,default=0.),maximum_corner_angle_deg=max(angles,default=0.),
        median_corner_angle_deg=float(np.median(angles)) if angles else 0.,p90_corner_angle_deg=float(np.percentile(angles,90)) if angles else 0.,
        corner_angle_std_deg=float(np.std(angles)) if angles else 0.,
        symmetry_error_m=halfturn_symmetry_error(points),repetition_fraction=repetition,
        annotation_order=[a['type'] for a in ordered_annotations(annotations)],
        physical_drivability='unassessed',driving_difficulty='unrated')
    approaches=0
    for i,item in enumerate(candidate.items):
        if item.role!='primary' or item.maneuver.type=='straight':continue
        straight=0.
        for j in range(1,len(candidate.items)):
            m=candidate.items[(i-j)%len(candidate.items)].maneuver
            if any(max(abs(s.k_start),abs(s.k_end))>1e-10 for s in m.segments):break
            straight+=m.length_m
        if straight>=20 and max(max(abs(s.k_start),abs(s.k_end)) for s in item.maneuver.segments)>=.4:approaches+=1
    stats['long_straight_to_tight_corner_count']=approaches
    evaluation=evaluate_objectives(spec,stats)
    if evaluation['failures']:
        error=GeometryError('Centerline objective failure: '+', '.join(f['metric'] for f in evaluation['failures']))
        error.objective_evaluation=evaluation;raise error
    targets={k:v for k,v in spec.objectives.items() if k not in WIDTH_METRICS}
    distances=[((stats[key]-(lo+hi)/2)/max((hi-lo)/2,1e-6))**2 for key,(lo,hi) in targets.items()]
    score=float(sum(distances)/max(1,len(distances))+repetition-.03*stats['curvature_reversals_per_100m']-.01*min(stats['symmetry_error_m'],30.))
    validation=dict(maximum_curvature_rate_inv_m2=rate,minimum_source_radius_m=float(1/peak),
        geometric_steering_range_rad=[float(min(steering)),float(max(steering))],geometric_steering_within_bounds=True,
        csv_coordinate_precision_m=1e-6,source_curve_length_m=source.length_m,polygon_winding_rad=polygon_winding,
        continuity_residuals=list(source.joints),lap_seam=dict(requested_offset_m=spec.seam_offset_m,actual_csv_offset_m=float(s[seam])),
        centerline_objective_evaluation=evaluation,physical_drivability='unassessed')
    return CenterlineResult(sampled,candidate.items,annotations,stats,validation,candidate.solution,score,
        curvature_profile_fingerprint(candidate.items,0.))


def _finish_corridor(spec,result,journal,profile):
    started=perf_counter();sampled=result.sampled
    # Width knots use the exported seam's source arclength, independent of rounding.
    left,right=spec.width.evaluate([p.s for p in sampled.states[:-1]],sampled.length_m)
    walls=variable_boundaries(sampled,left,right,spec.maximum_offset_curvature)
    validation,index=validate_corridor(sampled,walls,left+right,spec.vehicle,spec.limits)
    profile['corridor_validation_seconds']=perf_counter()-started
    start=perf_counter();rows=[]
    distances=np.r_[0.,np.cumsum(np.linalg.norm(np.diff([(p.x,p.y) for p in sampled.states],axis=0),axis=1))]
    curvature=position_curvatures((sampled.states[-2],*sampled.states[:-1],sampled.states[1]))[1:-1]
    for i,p in enumerate(sampled.states[:-1]):
        n=(-math.sin(p.heading),math.cos(p.heading))
        l=index.ray(p,n,float(left[i]+.0001));r=index.ray(p,(-n[0],-n[1]),float(right[i]+.0001))
        rows.append(dict(s_m=float(distances[i]),x_m=p.x,y_m=p.y,heading_rad=p.heading,
            curvature_inv_m=float(curvature[i]),width_m=l+r,left_width_m=l,right_width_m=r))
    geometry=TrackGeometry([CenterlineSample(p.x,p.y,p.heading) for p in sampled.states[:-1]],walls,rows,profile_metrics(sampled.points,rows))
    profile['measured_width_profile_seconds']=perf_counter()-start;start=perf_counter()
    raster=rasterize_corridor(walls,resolution=spec.resolution_m_per_pixel,padding=spec.padding_m)
    pixels,width,height,ox,oy=raster
    _validate_corridor_raster(sampled.points,pixels,width,height,ox,oy,spec.resolution_m_per_pixel)
    raster_validation=validate_raster_corridor(sampled,(*raster,spec.resolution_m_per_pixel),spec.vehicle,spec.limits)
    validation.update(raster_validation)
    profile['raster_validation_seconds']=perf_counter()-start
    stats=deepcopy(result.statistics);widths=np.array([r['width_m'] for r in rows])
    weights=np.diff(distances)
    stats.update(minimum_width_m=float(min(widths)),maximum_width_m=float(max(widths)),
        mean_width_m=float(np.average(widths,weights=weights)),width_std_m=float(np.sqrt(np.average((widths-np.average(widths,weights=weights))**2,weights=weights))),
        minimum_left_width_m=min(r['left_width_m'] for r in rows),minimum_right_width_m=min(r['right_width_m'] for r in rows),
        minimum_raster_width_m=raster_validation['minimum_raster_width_m'])
    evaluation=evaluate_objectives(spec,stats,width=True)
    if evaluation['failures']:
        error=GeometryError('Width objective failure: '+', '.join(f['metric'] for f in evaluation['failures']))
        error.objective_evaluation=evaluation;raise error
    validation.update(result.validation,width_objective_evaluation=evaluation)
    settings=TrackSpec(spec.track_id,sampled.points,track_width=stats['mean_width_m'],centerline_spacing=spec.spacing_m,
        resolution=spec.resolution_m_per_pixel,padding=spec.padding_m,wall_thickness_px=1,
        min_curvature_radius=spec.limits.minimum_radius_m,min_wall_separation=spec.limits.minimum_usable_width_m,
        target_length=spec.target_lap_length_m,occupancy_mode='corridor')
    _validate_spec(settings)
    metadata=build_geometry_metadata(settings,geometry.metrics)
    metadata.update(schema_version='2.0.0',generator_version=GENERATOR_VERSION,generation_mode='composite',
        geometry_family='extended_offline_circuit',dataset_id=spec.dataset_id,random_seed=spec.seed,
        maneuvers=result.annotations,difficulty={'label':'unrated'})
    metadata['requested'].pop('track_width_m')
    metadata['requested'].update(extended_specification=spec.recipe(),width_profile=asdict(spec.width),width_interpretation='periodic independent left/right normal offsets')
    identity=dict(generator=GENERATOR_VERSION,layout_version=spec.layout_version,configuration_sha256=spec.configuration_id,
        centerline_configuration_sha256=spec.centerline_configuration_id,centerline_fingerprint=result.fingerprint,
        coordinate_fingerprint=coordinate_fingerprint(sampled.points,0.),width_sha256=canonical_hash(asdict(spec.width)),
        corridor_fingerprint=canonical_hash(dict(centerline=result.fingerprint,width=asdict(spec.width))),
        inventory_lineage=canonical_hash(sorted(canonical_hash(asdict(r)) for r in spec.inventory)),
        matched_group=spec.matched_group,candidate_seed=spec.seed,vehicle=asdict(spec.vehicle))
    metadata['provenance'].update(identity=identity,validation=validation,extended_statistics=stats,
        layout_solution=result.solution,layout_attempts=deepcopy(journal),geometric_selection_score=result.score,
        selection_policy='centerline objectives first; width validation cannot change the winner',
        evaluation_metadata_only=True,policy_observations_changed=False,integration=dict(status='not_run',reason='offline_geometry_scope'),
        evaluation_csv=spec.track_id+'_evaluation.csv',width_profile_origin='exported centerline seam')
    validate_extended_metadata(metadata)
    return PreparedExtended(settings,geometry,metadata,sampled,result.items,stats,raster)


def prepare_extended(spec,*,profile=None):
    profile={} if profile is None else profile
    journal=[];valid=[];started=perf_counter();last=started;closure_seconds=0.;analysis_seconds=0.
    for candidate in extended_candidates(spec,journal):
        closure_seconds+=perf_counter()-last;begin=perf_counter()
        try:
            result=_centerline_result(spec,candidate)
            journal[-1].update(status='valid',geometric_selection_score=result.score,
                objective_evaluation=result.validation['centerline_objective_evaluation'],centerline_fingerprint=result.fingerprint)
            valid.append((result.score,len(journal)-1,result))
        except (GeometryError,TrackSpecError,ValueError) as exc:
            journal[-1].update(status='rejected',failure_stage='centerline',reason=str(exc))
            if hasattr(exc,'objective_evaluation'):journal[-1]['objective_evaluation']=exc.objective_evaluation
        analysis_seconds+=perf_counter()-begin;last=perf_counter()
    closure_seconds+=perf_counter()-last
    profile.update(closure_search_seconds=closure_seconds,centerline_analysis_seconds=analysis_seconds)
    if not valid:raise ExtendedGenerationError('No centerline passed the bounded extended search',journal)
    score,winner,result=min(valid,key=lambda x:(x[0],x[1]))
    for record in journal:
        if record['status']=='valid':record['status']='valid_not_selected'
    journal[winner]['status']='selected'
    try:prepared=_finish_corridor(spec,result,journal,profile)
    except (GeometryError,TrackSpecError,ValueError) as exc:
        journal[winner].update(status='rejected',failure_stage='corridor',reason=str(exc))
        if hasattr(exc,'objective_evaluation'):journal[winner]['objective_evaluation']=exc.objective_evaluation
        raise ExtendedGenerationError('Winning centerline failed its requested corridor: '+str(exc),journal) from exc
    prepared.metadata['provenance']['layout_selection']=dict(selected_candidate=winner+1,valid_centerlines=len(valid),evaluated_candidates=len(journal))
    profile['total_preparation_seconds']=perf_counter()-started
    return prepared


def validate_extended_metadata(metadata):
    validate_geometry_metadata(metadata)
    if metadata['generator_version']!=GENERATOR_VERSION or metadata['schema_version']!='2.0.0' or metadata['generation_mode']!='composite':
        raise GeometryError('Extended intent/version mismatch')
    if metadata['split']!='unspecified' or metadata['difficulty']['label']!='unrated':raise GeometryError('No dataset split or physical rating is assigned')
    lap=metadata['measured']['length_m'];annotations=metadata['maneuvers']
    if abs(sum(a['length_m'] for a in annotations)-lap)>1e-7:raise GeometryError('Extended intervals must partition the periodic lap')
    primary=sum(a['length_m'] for a in annotations if a['requested']['composition_role']=='primary')/lap
    if abs(primary-metadata['provenance']['extended_statistics']['primary_coverage'])>1e-8:raise GeometryError('Primary exposure disagrees with annotations')
    stats=metadata['provenance']['extended_statistics'];measured=metadata['measured']
    for key in ('minimum_width_m','maximum_width_m'):
        if abs(stats[key]-measured[key])>1e-9:raise GeometryError('Width statistics disagree with measured profile')
    if not stats['minimum_width_m']<=stats['mean_width_m']<=stats['maximum_width_m'] or stats['width_std_m']<0:
        raise GeometryError('Invalid width distribution')
    validation=metadata['provenance']['validation']
    if abs(stats['minimum_raster_width_m']-validation['minimum_raster_width_m'])>1e-9:
        raise GeometryError('Raster width statistics disagree with validation')
    spec=spec_from_recipe(metadata['requested']['extended_specification'])
    if spec.configuration_id!=metadata['provenance']['identity']['configuration_sha256'] or metadata['track_id']!=spec.track_id:
        raise GeometryError('Extended identity disagrees with native specification')
    if not metadata['provenance']['evaluation_metadata_only'] or metadata['provenance']['policy_observations_changed']:
        raise GeometryError('Labels must remain evaluation-only')


def _write_bundle(spec,prepared,directory):
    path=export_offline(prepared.settings,prepared.geometry,prepared.metadata,spec.recipe(),prepared.raster,directory)
    document=load_map_yaml(path);pose=min(prepared.sampled.states[:-1],key=lambda p:abs(p.s-(prepared.sampled.length_m-1)))
    document.annotations.spawn_points=[SpawnPoint('grid_1',Pose2D(pose.x,pose.y,pose.heading))]
    document.extra_fields['geometry_validation']='geometrically_validated; physical_drivability_unassessed'
    dump_map_yaml(document,path)
    lap=prepared.metadata['measured']['length_m']
    with (directory/(spec.track_id+'_evaluation.csv')).open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['s_m','maneuver_id','family','composition_role','distance_to_boundary_m','evaluation_only'])
        writer.writeheader()
        for row in prepared.geometry.profile:
            a=next(a for a in prepared.metadata['maneuvers'] if contains(a,row['s_m']))
            writer.writerow(dict(s_m=row['s_m'],maneuver_id=a['id'],family=a['type'],composition_role=a['requested']['composition_role'],
                distance_to_boundary_m=(a['s_end_m']-row['s_m'])%lap,evaluation_only=True))
    return path


def publish_extended(spec,output_dir,*,prepared=None,profile=None):
    output_dir=Path(output_dir)
    if output_dir.exists():raise FileExistsError('Refusing to overwrite extended bundle: '+str(output_dir))
    prepared=prepared or prepare_extended(spec)
    if prepared.metadata['requested']['extended_specification']!=spec.recipe():raise GeometryError('Prepared result does not match the extended recipe')
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    profile={} if profile is None else profile
    with tempfile.TemporaryDirectory(prefix='.extended-',dir=output_dir.parent) as temporary:
        start=perf_counter();staging=Path(temporary)/'bundle';path=_write_bundle(spec,prepared,staging)
        profile['export_seconds']=perf_counter()-start
        names=list(prepared.metadata['artifacts'].values())+[spec.track_id+'_evaluation.csv']
        hashes={name:hashlib.sha256((staging/name).read_bytes()).hexdigest() for name in names}
        start=perf_counter();loaded=load_extended_spec(staging/prepared.metadata['artifacts']['recipe'])
        regenerated=prepare_extended(loaded);replay_dir=Path(temporary)/'replay';_write_bundle(loaded,regenerated,replay_dir)
        for name in names:
            if (staging/name).read_bytes()!=(replay_dir/name).read_bytes():raise GeometryError('Extended native replay changed '+name)
        profile['replay_seconds']=perf_counter()-start
        report=dict(generator=GENERATOR_VERSION,geometric_validity='accepted',physical_drivability='unassessed',
            integration=dict(status='not_run',reason='offline_geometry_scope'),
            recipe_replay=dict(status='passed',byte_identical=True,artifacts_compared=len(names)),artifact_sha256=hashes,
            validation=prepared.metadata['provenance']['validation'],statistics=prepared.statistics,
            layout_attempts=prepared.metadata['provenance']['layout_attempts'])
        (staging/(spec.track_id+'_validation.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        output_dir.mkdir(exist_ok=False)
        try:
            for artifact in staging.iterdir():shutil.move(str(artifact),output_dir/artifact.name)
        except BaseException:
            shutil.rmtree(output_dir);raise
    return output_dir/path.name
