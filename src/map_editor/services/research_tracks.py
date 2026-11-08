"""New specialist/composite publication; all validation is standalone/offline."""
from copy import deepcopy
from dataclasses import asdict,dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
import tempfile
from time import perf_counter
import numpy as np
from map_editor.geometry import GeometryError
from map_editor.geometry.corridor import variable_boundaries,validate_corridor,validate_raster_corridor
from map_editor.geometry.measurement import position_curvatures
from map_editor.exporters.centerline import CenterlineSample
from map_editor.models.annotations import Pose2D,SpawnPoint
from .procedural_track import TrackGeometry,TrackSpec,TrackSpecError,_validate_spec,_validate_corridor_raster
from .geometry_metadata import build_geometry_metadata,validate_geometry_metadata
from .offline_export import rasterize_corridor,export_offline
from .track_profile import profile_metrics
from .yaml_serializer import load_map_yaml,dump_map_yaml
from .composite_statistics import contains,coordinate_fingerprint
from .specialist_templates import canonical_hash,FAMILIES
from .extended_layout import extended_candidates
from .extended_tracks import _centerline_result,evaluate_objectives
from .research_spec import GENERATOR_VERSION,ResearchSpec,load_research_spec,spec_from_recipe

class ResearchGenerationError(GeometryError):
    def __init__(self,message,attempts):super().__init__(message);self.attempts=deepcopy(attempts)

@dataclass
class PreparedResearch:
    settings: object
    geometry: object
    metadata: dict
    sampled: object
    items: tuple
    statistics: dict
    raster: tuple

def _finish_research(spec,result,journal,profile):
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
    metadata.update(schema_version='2.0.0',generator_version=GENERATOR_VERSION,generation_mode=spec.generation_mode,split=spec.split,
        geometry_family='research_'+spec.generation_mode,dataset_id=spec.dataset_id,random_seed=spec.seed,
        maneuvers=result.annotations,difficulty={'label':'unrated'})
    metadata['requested'].pop('track_width_m')
    metadata['requested'].update(research_specification=spec.recipe(),width_profile=asdict(spec.width),width_interpretation='periodic independent left/right normal offsets')
    identity=dict(generator=GENERATOR_VERSION,layout_version=spec.layout_version,configuration_sha256=spec.configuration_id,
        centerline_fingerprint=result.fingerprint,
        coordinate_fingerprint=coordinate_fingerprint(sampled.points,0.),width_sha256=canonical_hash(asdict(spec.width)),
        corridor_fingerprint=canonical_hash(dict(centerline=result.fingerprint,width=asdict(spec.width))),
        inventory_lineage=canonical_hash(sorted(canonical_hash(asdict(r)) for r in spec.inventory)),
        parent_layout_lineage=spec.parent_lineage,near_duplicate_group=spec.parent_lineage,slot_id=spec.slot_id,split=spec.split,template_topology=spec.topology_family,candidate_seed=spec.seed,vehicle=asdict(spec.vehicle))
    metadata['provenance'].update(identity=identity,validation=validation,research_statistics=stats,
        layout_solution=result.solution,layout_attempts=deepcopy(journal),geometric_selection_score=result.score,
        selection_policy='centerline objectives first; width validation cannot change the winner',
        evaluation_metadata_only=True,policy_observations_changed=False,integration=dict(status='not_run',reason='offline_geometry_scope'),
        evaluation_csv=spec.track_id+'_evaluation.csv',width_profile_origin='exported centerline seam')
    validate_research_metadata(metadata)
    return PreparedResearch(settings,geometry,metadata,sampled,result.items,stats,raster)


def _composition(spec,result):
    stats=result.statistics;annotations=result.annotations;lap=stats['raw_lap_length_m']
    primary=[a for a in annotations if a['requested']['composition_role']=='primary']
    families=sorted({a['type'] for a in primary})
    exposure={f:sum(a['length_m'] for a in primary if a['type']==f)/lap for f in families}
    active=0.;active_by_family={f:0. for f in families}
    # Integrate true differential geometry over source/chord intervals; preserve
    # internal zero-curvature regions inside opposing-turn annotations.
    for item in result.items:
        length=item.maneuver.length_m
        curved=sum(s.length_m for s in item.maneuver.segments if max(abs(s.k_start),abs(s.k_end))>1e-5)
        active+=curved
        if item.role=='primary':active_by_family[item.maneuver.type]+=curved
    source_length=result.sampled.length_m
    stats.update(primary_family_exposure_fractions=exposure,measured_primary_families=families,
        active_curvature_fraction=active/source_length,
        primary_active_curvature_exposure={k:v/source_length for k,v in active_by_family.items()},
        primary_family_count=len(families),target_family=spec.target_family,
        target_exposure_fraction=exposure.get(spec.target_family,0.) if spec.target_family else None)
    if spec.generation_mode=='specialist':
        if families!=[spec.target_family] or exposure[spec.target_family]<spec.minimum_target_exposure-1e-7:
            raise GeometryError('Measured specialist family/dominance acceptance failed')
        fraction=active_by_family[spec.target_family]/sum(a['length_m'] for a in primary)
        if spec.target_family!='straight' and fraction<spec.minimum_target_active_fraction:raise GeometryError('Specialist target hides excessive internal straight geometry')
        if spec.target_family=='sweeper' and any(a['measured']['minimum_radius_m']<5 or a['length_m']<5 for a in primary):
            raise GeometryError('Sweeper specialist requires sustained large-radius windows')
    else:
        if len(families)!=spec.expected_primary_families:raise GeometryError('Measured primary-family count differs from allocated composite complexity')
        if any(not spec.minimum_family_exposure<=v<=spec.maximum_family_exposure for v in exposure.values()):
            raise GeometryError('Composite family exposure outside declared meaningful coverage bounds')
    # Cyclic label changes are separate from geometric corner/reversal counts.
    from .composite_statistics import ordered_annotations
    ordered=ordered_annotations(annotations)
    projected=[a for a in ordered if a['requested']['composition_role']=='primary']
    matrix={f:{g:0 for g in families} for f in families}
    for i,a in enumerate(projected):matrix[a['type']][projected[(i+1)%len(projected)]['type']]+=1
    changes=sum(a['type']!=projected[(i+1)%len(projected)]['type'] for i,a in enumerate(projected))
    stats.update(primary_order_transition_matrix=matrix,primary_family_switch_count=changes,
        primary_switch_density_per_100m=100*changes/lap,
        requested_primary_inventory=[dict(name=r.name,family=r.family,parameters=r.parameters) for r in spec.inventory])


def prepare_research(spec,*,profile=None):
    profile={} if profile is None else profile;started=perf_counter();journal=[];valid=[]
    for candidate in research_candidates(spec,journal):
        try:
            result=_centerline_result(spec,candidate);_composition(spec,result)
            journal[-1].update(status='valid',geometric_selection_score=result.score,
                composition=dict(primary_families=result.statistics['measured_primary_families'],
                    exposure=result.statistics['primary_family_exposure_fractions']))
            valid.append((result.score,len(journal)-1,result))
        except (GeometryError,ValueError) as exc:
            journal[-1].update(status='rejected',failure_stage='centerline_or_composition',reason=str(exc))
            if hasattr(exc,'objective_evaluation'):journal[-1]['objective_evaluation']=exc.objective_evaluation
    if not valid:raise ResearchGenerationError('No valid research candidate in bounded search',journal)
    score,winner,result=min(valid,key=lambda x:(x[0],x[1]))
    for record in journal:
        if record['status']=='valid':record['status']='valid_not_selected'
    journal[winner]['status']='selected'
    try:prepared=_finish_research(spec,result,journal,profile)
    except (GeometryError,ValueError) as exc:
        journal[winner].update(status='rejected',failure_stage='corridor',reason=str(exc))
        raise ResearchGenerationError('Requested research corridor failed: '+str(exc),journal) from exc
    prepared.metadata['provenance']['layout_selection']=dict(selected_candidate=winner+1,evaluated_candidates=len(journal),valid_candidates=len(valid))
    profile['total_preparation_seconds']=perf_counter()-started
    return prepared


def research_candidates(spec,journal):
    if spec.assembly_method=='bounded_supporting_turns.v1':
        yield from extended_candidates(spec,journal)
        return
    from .composite_assembly import AssemblyItem,connector
    from .extended_layout import ExtendedCandidate
    from map_editor.geometry import Frame,straight
    items=[]
    for block in range(2):
        for i,r in enumerate(spec.inventory):
            items.append(AssemblyItem(r.build(),'primary',r.name,i,block_instance=block))
            items.append(connector(straight(spec.support_gap_m),'motif_gap',adjustable=False))
    record=dict(candidate=1,topology='controlled_halfturn_five',method='controlled_halfturn.v1',status='candidate',
        order=list(range(len(spec.inventory))),exact_rotated_block_closure=True)
    journal.append(record)
    yield ExtendedCandidate(tuple(items),Frame(),dict(record))


def validate_research_metadata(metadata):
    validate_geometry_metadata(metadata)
    spec=spec_from_recipe(metadata['requested']['research_specification'])
    if metadata['generator_version']!=GENERATOR_VERSION or metadata['track_id']!=spec.track_id or metadata['generation_mode']!=spec.generation_mode or metadata['split']!=spec.split:
        raise GeometryError('Research recipe/metadata intent or identity mismatch')
    if metadata['difficulty']['label']!='unrated' or metadata['provenance']['identity']['parent_layout_lineage']!=spec.parent_lineage:
        raise GeometryError('Research rating/lineage mismatch')
    lap=metadata['measured']['length_m'];annotations=metadata['maneuvers'];stats=metadata['provenance']['research_statistics']
    if abs(sum(a['length_m'] for a in annotations)-lap)>1e-7:raise GeometryError('Research periodic windows must partition the complete lap')
    exposure={f:sum(a['length_m'] for a in annotations if a['type']==f and a['requested']['composition_role']=='primary')/lap for f in stats['measured_primary_families']}
    if any(abs(v-stats['primary_family_exposure_fractions'][f])>1e-8 for f,v in exposure.items()):raise GeometryError('Research family exposure disagrees with annotations')
    if spec.generation_mode=='specialist' and (set(exposure)!={spec.target_family} or exposure[spec.target_family]<spec.minimum_target_exposure-1e-7):raise GeometryError('Specialist dominance must be measured')
    if spec.generation_mode=='composite' and len(exposure)!=spec.expected_primary_families:raise GeometryError('Composite complexity differs from intent')
    if not metadata['provenance']['evaluation_metadata_only'] or metadata['provenance']['policy_observations_changed']:raise GeometryError('Research labels are evaluation-only')
    if metadata['provenance']['identity']['configuration_sha256']!=spec.configuration_id:raise GeometryError('Research configuration checksum mismatch')


def _write_bundle(spec,prepared,directory):
    path=export_offline(prepared.settings,prepared.geometry,prepared.metadata,spec.recipe(),prepared.raster,directory)
    document=load_map_yaml(path);pose=min(prepared.sampled.states[:-1],key=lambda p:abs(p.s-(prepared.sampled.length_m-1)))
    document.annotations.spawn_points=[SpawnPoint('grid_1',Pose2D(pose.x,pose.y,pose.heading))]
    document.extra_fields['geometry_validation']='geometrically_validated; physical_drivability_unassessed'
    dump_map_yaml(document,path)
    lap=prepared.metadata['measured']['length_m']
    with (directory/(spec.track_id+'_evaluation.csv')).open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['s_m','maneuver_id','family','composition_role','distance_to_boundary_m','evaluation_only']);writer.writeheader()
        for row in prepared.geometry.profile:
            a=next(a for a in prepared.metadata['maneuvers'] if contains(a,row['s_m']))
            writer.writerow(dict(s_m=row['s_m'],maneuver_id=a['id'],family=a['type'],composition_role=a['requested']['composition_role'],distance_to_boundary_m=(a['s_end_m']-row['s_m'])%lap,evaluation_only=True))
    return path


def publish_research(spec,output_dir,*,prepared=None,profile=None):
    output_dir=Path(output_dir)
    if output_dir.exists():raise FileExistsError('Refusing to overwrite research bundle')
    prepared=prepared or prepare_research(spec)
    if prepared.metadata['requested']['research_specification']!=spec.recipe():raise GeometryError('Prepared research result does not match recipe')
    profile={} if profile is None else profile;output_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.research-',dir=output_dir.parent) as temporary:
        start=perf_counter();staging=Path(temporary)/'bundle';path=_write_bundle(spec,prepared,staging)
        names=[*prepared.metadata['artifacts'].values(),spec.track_id+'_evaluation.csv']
        hashes={name:hashlib.sha256((staging/name).read_bytes()).hexdigest() for name in names}
        profile['export_seconds']=perf_counter()-start;start=perf_counter()
        loaded=load_research_spec(staging/prepared.metadata['artifacts']['recipe']);regenerated=prepare_research(loaded)
        replay_dir=Path(temporary)/'replay';_write_bundle(loaded,regenerated,replay_dir)
        for name in names:
            if (staging/name).read_bytes()!=(replay_dir/name).read_bytes():raise GeometryError('Research byte replay changed '+name)
        profile['replay_seconds']=perf_counter()-start
        report=dict(generator=GENERATOR_VERSION,geometric_validity='accepted',physical_drivability='unassessed',driving_difficulty='unrated',
            integration=dict(status='not_run',reason='offline_research_dataset'),split=spec.split,slot_id=spec.slot_id,attempt=spec.attempt,candidate_seed=spec.seed,
            identity=prepared.metadata['provenance']['identity'],statistics=prepared.statistics,validation=prepared.metadata['provenance']['validation'],
            recipe_replay=dict(status='passed',byte_identical=True,artifacts_compared=len(names)),artifact_sha256=hashes,
            layout_attempts=prepared.metadata['provenance']['layout_attempts'])
        (staging/(spec.track_id+'_validation.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        if output_dir.exists():raise FileExistsError('Refusing to overwrite research bundle')
        # Staging is on the destination filesystem. Publish the complete
        # directory in one rename so interruption cannot expose a partial bundle.
        staging.rename(output_dir)
    return output_dir/path.name
