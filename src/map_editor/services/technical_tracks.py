"""Technical candidates: full validation, geometric selection, native publication."""
from copy import deepcopy
from dataclasses import dataclass, asdict, replace
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import numpy as np
from map_editor.geometry import GeometryError
from map_editor.geometry.measurement import position_curvatures
from map_editor.geometry.technical import TechnicalManeuver, validate_technical
from map_editor.geometry.validation import validate_raster_footprint
from map_editor.geometry.spatial import self_intersects, minimum_boundary_separation
from map_editor.models.annotations import Point2D, Pose2D, SpawnPoint
from map_editor.exporters.centerline import CenterlineSample
from map_editor.services.parametric_track import ParametricTrackSpec, prepare_parametric_track
from map_editor.services.procedural_track import TrackSpecError, _rasterize_walls, export_track_geometry
from map_editor.services.composite_tracks import _rotate_samples, _source_validation
from map_editor.services.composite_statistics import (interval, contains, halfturn_symmetry_error,
    curvature_profile_fingerprint, coordinate_fingerprint)
from map_editor.services.geometry_metadata import validate_geometry_metadata
from map_editor.services.specialist_templates import canonical_hash
from map_editor.services.specialist_tracks import consumer_smoke
from map_editor.services.track_profile import profile_metrics
from map_editor.services.yaml_serializer import load_map_yaml, dump_map_yaml
from .technical_analysis import analyze_geometry
from .technical_layout import layout_candidates
from .technical_spec import GENERATOR_VERSION, load_technical_spec


class TechnicalGenerationError(GeometryError):
    def __init__(self,message,attempts):
        super().__init__(message);self.attempts=deepcopy(attempts)


@dataclass
class PreparedTechnical:
    settings: object
    geometry: object
    metadata: dict
    sampled: object
    statistics: dict
    items: tuple


def complexity_metrics(points,annotations,items):
    stats=analyze_geometry(points,sigma_m=.4,include_profile=True)
    lap=sum(a['length_m'] for a in annotations)
    primary=sum(a['length_m'] for a in annotations if a['requested']['composition_role']=='primary')/lap
    k=np.array(stats.pop('profile')['curvature_inv_m']);k=k-k.mean()
    denom=float(k@k)
    repetition=max((float(k@np.roll(k,round(len(k)/n)))/denom for n in (2,3,4)),default=0.) if denom else 1.
    approaches=[]
    for index,item in enumerate(items):
        if item.role!='primary' or item.maneuver.type=='straight': continue
        preceding=0.
        for back in range(1,len(items)):
            previous=items[(index-back)%len(items)].maneuver
            if any(max(abs(s.k_start),abs(s.k_end))>1e-10 for s in previous.segments): break
            preceding+=previous.length_m
        peak=max(max(abs(s.k_start),abs(s.k_end)) for s in item.maneuver.segments)
        approaches.append(dict(inventory_name=item.request_name,family=item.maneuver.type,
            preceding_exact_straight_m=preceding,following_peak_curvature_inv_m=peak,
            turn_angle_deg=abs(math.degrees(item.maneuver.at(item.maneuver.length_m).heading))))
    stats.update(primary_coverage=primary,supporting_fraction=1-primary,
        symmetry_error_m=halfturn_symmetry_error([Point2D(*p) for p in points]),
        repetition_fraction=max(0.,min(1.,repetition)),
        minimum_corner_angle_deg=stats['corner_angles_deg']['minimum'] or 0.,
        maximum_corner_angle_deg=stats['corner_angles_deg']['maximum'] or 0.,
        median_corner_angle_deg=stats['corner_angles_deg']['median'] or 0.,
        p90_corner_angle_deg=stats['corner_angles_deg']['p90'] or 0.,
        corner_angle_std_deg=float(np.std(stats['corner_angles_deg']['values'])) if stats['corner_count'] else 0.,
        primary_family_count=len({i.maneuver.type for i in items if i.role=='primary'}),
        family_exposure_fractions={kind:sum(a['length_m'] for a in annotations if a['type']==kind)/lap
            for kind in sorted({a['type'] for a in annotations})},
        maneuver_count=len(annotations),annotation_order=[a['type'] for a in annotations],
        physical_drivability='unassessed',driving_difficulty='unrated')
    stats.update(turn_approaches=approaches,long_straight_to_tight_corner_count=sum(
        a['preceding_exact_straight_m']>=20 and a['following_peak_curvature_inv_m']>=.4 for a in approaches))
    return stats


def check_objectives(spec,stats):
    checks=dict(spec.objectives)
    for key,bounds in dict(raw_lap_length_m=spec.lap_length_range_m,
        primary_coverage=(spec.minimum_primary_coverage,1.),supporting_fraction=(0.,spec.maximum_supporting_fraction)).items():
        requested=checks.get(key,bounds)
        checks[key]=(max(bounds[0],requested[0]),min(bounds[1],requested[1]))
    failures=[f'{key}={stats[key]:.6g} outside [{bounds[0]}, {bounds[1]}]'
              for key,bounds in checks.items() if not bounds[0]-1e-7<=stats[key]<=bounds[1]+1e-7]
    if failures:
        raise GeometryError('Complexity acceptance: '+'; '.join(failures))
    # Dimensionless objective distance plus measured irregularity/alternation.
    distances=[((stats[key]-(lo+hi)/2)/max((hi-lo)/2,1e-6))**2 for key,(lo,hi) in spec.objectives.items()]
    return float((sum(distances)/max(1,len(distances))) + stats['repetition_fraction']
                 - .03*stats['curvature_reversals_per_100m'] - .01*min(stats['symmetry_error_m'],20.))


def prepare_candidate(spec,candidate):
    native=ParametricTrackSpec(spec.track_id,tuple(i.maneuver for i in candidate.items),
        spacing_m=spec.spacing_m,width_m=spec.track_width_m,resolution=spec.resolution_m_per_pixel,
        padding=spec.padding_m,frame=candidate.frame,vehicle=spec.vehicle,random_seed=spec.seed,
        dataset_id=spec.dataset_id,limits=spec.limits,metadata_schema_version='2.0.0')
    settings,geometry,metadata,source=prepare_parametric_track(native)
    steering=np.arctan((spec.vehicle.lf_m+spec.vehicle.lr_m)*np.array([s.curvature for s in source.states]))
    if steering.min()<spec.vehicle.steering_min_rad or steering.max()>spec.vehicle.steering_max_rad:
        raise GeometryError('Required geometric steering exceeds the actual vehicle snapshot bounds')
    states=tuple(replace(s,x=round(s.x,6),y=round(s.y,6)) for s in source.states)
    states=(*states[:-1],replace(states[-1],x=states[0].x,y=states[0].y))
    source=replace(source,states=states)
    geometry.walls=[[Point2D(round(p.x,6),round(p.y,6)) for p in wall] for wall in geometry.walls]
    if self_intersects(source.points,closed=True) or any(self_intersects(w,closed=True) for w in geometry.walls):
        raise GeometryError('Quantized technical centerline/wall intersection')
    gap=minimum_boundary_separation(*geometry.walls,closed=True)
    usable=gap-2*spec.limits.footprint_margin_m
    raster_bound=usable-4*math.sqrt(2)*spec.resolution_m_per_pixel
    if raster_bound<spec.limits.minimum_usable_width_m:
        raise GeometryError('Quantized technical corridor width failure')
    s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff([(p.x,p.y) for p in states],axis=0),axis=1))]
    lap=float(s[-1]);requested_seam=spec.seam_offset_m%source.length_m
    index=min(range(len(states)-1),key=lambda i:min(abs(states[i].s-requested_seam),source.length_m-abs(states[i].s-requested_seam)))
    annotations=[]
    for i,(item,(start,end)) in enumerate(zip(candidate.items,source.spans)):
        measured=(validate_technical(item.maneuver,states[start:end+1],spec.track_width_m)
                  if isinstance(item.maneuver,TechnicalManeuver) else _source_validation(item,states[start:end+1],spec.track_width_m))
        length=float(s[end]-s[start])
        if item.role=='primary' and item.maneuver.type!='straight' and length<spec.minimum_useful_corner_m:
            raise GeometryError('Technical primary corner below useful length')
        annotations.append(dict(id=f'maneuver_{i+1:03d}',type=item.maneuver.type,direction=item.maneuver.direction,
            **interval(float(s[start]-s[index]),length,lap),requested=dict(item.maneuver.requested,
                composition_role=item.role,inventory_name=item.request_name,inventory_index=item.inventory_index,
                adjustable_connector=item.adjustable),measured=measured,difficulty={'label':'unrated'}))
    sampled=_rotate_samples(source,index)
    distances=np.r_[0.,np.cumsum(np.linalg.norm(np.diff([(p.x,p.y) for p in sampled.states],axis=0),axis=1))]
    k=position_curvatures((sampled.states[-2],*sampled.states[:-1],sampled.states[1]))[1:-1]
    geometry.samples=[CenterlineSample(p.x,p.y,p.heading) for p in sampled.states[:-1]]
    geometry.profile=[dict(s_m=float(distances[i]),x_m=p.x,y_m=p.y,heading_rad=p.heading,
        curvature_inv_m=float(k[i]),width_m=spec.track_width_m,left_width_m=spec.track_width_m/2,
        right_width_m=spec.track_width_m/2) for i,p in enumerate(sampled.states[:-1])]
    geometry.metrics=profile_metrics(sampled.points,geometry.profile)
    stats=complexity_metrics([(p.x,p.y) for p in sampled.states[:-1]],annotations,candidate.items)
    score=check_objectives(spec,stats)
    raster=_rasterize_walls(geometry.walls,resolution=spec.resolution_m_per_pixel,padding=spec.padding_m,
        thickness_px=1,occupancy_mode='corridor')
    validation=metadata['provenance']['validation']
    validation.update(exported_global_boundary_separation_m=gap,exported_usable_width_m=usable,
        geometric_steering_range_rad=[float(steering.min()),float(steering.max())],
        geometric_steering_within_vehicle_bounds=True,
        exported_raster_usable_width_bound_m=raster_bound,csv_coordinate_precision_m=1e-6,
        exported_raster_footprint=validate_raster_footprint(sampled,(*raster,spec.resolution_m_per_pixel),spec.vehicle,spec.limits.footprint_margin_m),
        feasibility_advisory=dict(status='not_requested',physical_drivability='unassessed'))
    identity=dict(generator=GENERATOR_VERSION,layout_version=spec.layout_version,configuration_sha256=spec.configuration_id,
        geometry_fingerprint=curvature_profile_fingerprint(candidate.items,spec.track_width_m),
        coordinate_fingerprint=coordinate_fingerprint(sampled.points,spec.track_width_m),
        inventory_lineage=canonical_hash(sorted(canonical_hash(asdict(r)) for r in spec.inventory)),
        candidate_seed=spec.seed,vehicle=asdict(spec.vehicle),topology_order=candidate.solution['order'])
    metadata.update(generator_version=GENERATOR_VERSION,generation_mode='composite',geometry_family='technical_distributed_layout',
        maneuvers=annotations,measured=geometry.metrics,difficulty={'label':'unrated'})
    metadata['requested']['technical_specification']=spec.recipe()
    metadata['provenance'].update(identity=identity,technical_statistics=stats,layout_solution=candidate.solution,
        geometric_selection_score=score,score_interpretation='candidate geometry selection only; no physical difficulty rating',
        measured_layout_symmetry='asymmetric' if stats['symmetry_error_m']>.001 else 'halfturn_symmetric',
        evaluation_metadata_only=True,policy_observations_changed=False,
        lap_seam=dict(requested_offset_m=spec.seam_offset_m,actual_csv_offset_m=float(s[index])),
        evaluation_csv=spec.track_id+'_evaluation.csv')
    validate_technical_metadata(metadata)
    return PreparedTechnical(settings,geometry,metadata,sampled,stats,candidate.items)


def validate_technical_metadata(metadata):
    validate_geometry_metadata(metadata)
    if metadata['generator_version']!=GENERATOR_VERSION or metadata['schema_version']!='2.0.0':
        raise GeometryError('Technical metadata version mismatch')
    if metadata['split']!='unspecified' or metadata['difficulty']['label']!='unrated':
        raise GeometryError('Technical generation assigns no research splits or driving rating')
    lap=metadata['measured']['length_m']
    if abs(sum(a['length_m'] for a in metadata['maneuvers'])-lap)>1e-7:
        raise GeometryError('Technical windows must partition lap')
    primary=sum(a['length_m'] for a in metadata['maneuvers'] if a['requested']['composition_role']=='primary')/lap
    if abs(primary-metadata['provenance']['technical_statistics']['primary_coverage'])>1e-8:
        raise GeometryError('Technical exposure inconsistent with annotations')


def prepare_technical(spec,excluded_fingerprints=()):
    journal=[];valid=[]
    for candidate in layout_candidates(spec,journal):
        try:
            prepared=prepare_candidate(spec,candidate)
            score=prepared.metadata['provenance']['geometric_selection_score']
            journal[-1].update(status='valid',geometric_selection_score=score,
                measured_complexity={k:prepared.statistics[k] for k in spec.objectives})
            valid.append((score,len(journal)-1,prepared))
        except (GeometryError,TrackSpecError,ValueError) as exc:
            journal[-1].update(status='rejected',reason=str(exc))
    if not valid:
        raise TechnicalGenerationError('No technical candidate passed bounded layout/complexity validation',journal)
    score,index,prepared=min(valid,key=lambda x:(x[0],x[1]))
    identity=prepared.metadata['provenance']['identity']
    if identity['geometry_fingerprint'] in excluded_fingerprints or identity['coordinate_fingerprint'] in excluded_fingerprints:
        journal[index].update(status='rejected',reason='Duplicate winning technical geometry')
        raise TechnicalGenerationError('Duplicate winning technical geometry; request needs a distinct inventory/layout recipe',journal)
    for record in journal:
        if record['status']=='valid': record['status']='valid_not_selected'
    journal[index]['status']='selected'
    prepared.metadata['provenance']['layout_attempts']=deepcopy(journal)
    prepared.metadata['provenance']['layout_selection']=dict(selected_candidate=index+1,valid_candidates=len(valid),
        evaluated_candidates=len(journal),criterion='minimum geometric objective score, then earliest candidate')
    return prepared


def write_bundle(spec,prepared,directory):
    path=export_track_geometry(prepared.settings,prepared.geometry,directory,
        metadata_contract=prepared.metadata,generation_recipe=spec.recipe())
    document=load_map_yaml(path)
    pose=min(prepared.sampled.states[:-1],key=lambda p:abs(p.s-(prepared.sampled.length_m-1)))
    document.annotations.spawn_points=[SpawnPoint('grid_1',Pose2D(pose.x,pose.y,pose.heading))]
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


def publish_technical(spec,output_dir,*,reference=None,prepared=None):
    output_dir=Path(output_dir)
    if output_dir.exists(): raise FileExistsError('Refusing to overwrite technical bundle: '+str(output_dir))
    prepared=prepared or prepare_technical(spec)
    if prepared.metadata['requested']['technical_specification']!=spec.recipe():
        raise GeometryError('Prepared technical geometry does not match the publication recipe')
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.technical-',dir=output_dir.parent) as temp:
        staging=Path(temp)/'bundle';path=write_bundle(spec,prepared,staging)
        integration=consumer_smoke(path,reference) if reference else dict(status='not_run')
        names=list(prepared.metadata['artifacts'].values())+[spec.track_id+'_evaluation.csv']
        hashes={name:hashlib.sha256((staging/name).read_bytes()).hexdigest() for name in names}
        loaded=load_technical_spec(staging/prepared.metadata['artifacts']['recipe'])
        replay=prepare_technical(loaded)
        # Pilot duplicate exclusions affect candidate eligibility only; publication
        # must select the same unconstrained winner to remain a native recipe.
        replay_dir=Path(temp)/'replay';write_bundle(loaded,replay,replay_dir)
        for name in names:
            if (staging/name).read_bytes()!=(replay_dir/name).read_bytes():
                raise GeometryError('Technical native replay changed '+name)
        report=dict(generator=GENERATOR_VERSION,geometric_validity='accepted',physical_drivability='unassessed',
            integration=integration,recipe_replay=dict(status='passed',byte_identical=True,artifacts_compared=len(names)),
            artifact_sha256=hashes,validation=prepared.metadata['provenance']['validation'],
            continuity=prepared.metadata['provenance']['continuity_residuals'],statistics=prepared.statistics,
            layout_attempts=prepared.metadata['provenance']['layout_attempts'])
        (staging/(spec.track_id+'_validation.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        output_dir.mkdir(exist_ok=False)
        try:
            for item in staging.iterdir(): shutil.move(str(item),output_dir/item.name)
        except BaseException:
            shutil.rmtree(output_dir);raise
    return output_dir/path.name
