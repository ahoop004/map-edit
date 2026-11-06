"""Composite export, periodic annotations, native replay and immutable publication."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

import numpy as np
from map_editor.exporters.centerline import CenterlineSample
from map_editor.geometry import GeometryError, Maneuver
from map_editor.geometry.measurement import position_curvatures, validate_maneuver
from map_editor.geometry.spatial import self_intersects, minimum_boundary_separation
from map_editor.geometry.validation import validate_raster_footprint, feasibility_advisory
from map_editor.models.annotations import Point2D, Pose2D, SpawnPoint
from map_editor.services.composite_spec import GENERATOR_VERSION, CompositeSpec, load_composite_spec
from map_editor.services.composite_assembly import assembly_candidates
from map_editor.services.composite_statistics import (
    composite_statistics, coordinate_fingerprint, curvature_profile_fingerprint, evaluation_rows,
    halfturn_symmetry_error, interval, contains, MATRIX_LABELS, ordered_annotations,
)
from map_editor.services.geometry_metadata import validate_geometry_metadata
from map_editor.services.parametric_track import ParametricTrackSpec, prepare_parametric_track
from map_editor.services.procedural_track import TrackSpecError, _rasterize_walls, export_track_geometry
from map_editor.services.specialist_tracks import consumer_smoke
from map_editor.services.specialist_templates import FAMILIES
from map_editor.services.track_profile import profile_metrics
from map_editor.services.yaml_serializer import load_map_yaml, dump_map_yaml


class CompositeGenerationError(GeometryError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = deepcopy(attempts)


@dataclass
class PreparedComposite:
    export_settings: object
    geometry: object
    metadata: dict
    sampled: object
    assembly: object
    statistics: dict


def _source_validation(item, states, width):
    result = validate_maneuver(item.maneuver, states, width_m=width)
    first,last=item.maneuver.segments[0],item.maneuver.segments[-1]
    result["start_curvature_rate_inv_m2"]=first.at(0).curvature_rate
    result["end_curvature_rate_inv_m2"]=last.at(last.length_m).curvature_rate
    requested = item.maneuver.requested
    if "source_type" in requested:
        params = deepcopy(requested["source_parameters"])
        if "direction" in params:
            params["direction"] = item.maneuver.direction
        if requested["source_type"] == "transition":
            params.update(k_start_inv_m=item.maneuver.segments[0].k_start, k_end_inv_m=item.maneuver.segments[-1].k_end)
        source = Maneuver(requested["source_type"], item.maneuver.direction, item.maneuver.segments, params)
        result["source_primitive_acceptance"] = validate_maneuver(source, states, width_m=width)
    return result


def _rotate_samples(sampled, index):
    states = sampled.states[:-1]
    length = sampled.states[-1].s
    turn = sampled.states[-1].heading-sampled.states[0].heading
    offset = states[index].s
    order = list(range(index, len(states)))+list(range(index))
    values = [replace(states[i], s=states[i].s-offset+(length if i < index else 0),
                      heading=states[i].heading+(turn if i < index else 0)) for i in order]
    values.append(replace(values[0], s=length, heading=values[0].heading+turn))
    # Intervals can cross the new seam; a simple [start,end] index span no longer
    # describes them. The metadata's periodic intervals are authoritative.
    return replace(sampled, states=tuple(values), spans=(), maneuvers=())


def _prepare_candidate(spec, assembly, journal):
    items = assembly.items
    native = ParametricTrackSpec(spec.track_id, tuple(i.maneuver for i in items),
        spacing_m=spec.spacing_m, width_m=spec.track_width_m, resolution=spec.resolution_m_per_pixel,
        padding=spec.padding_m, frame=assembly.frame, vehicle=spec.vehicle, random_seed=spec.seed,
        dataset_id=spec.dataset_id, limits=spec.limits)
    settings, geometry, metadata, source = prepare_parametric_track(native)
    states = tuple(replace(s, x=float(f"{s.x:.6f}"), y=float(f"{s.y:.6f}")) for s in source.states)
    states = (*states[:-1], replace(states[-1], x=states[0].x, y=states[0].y))
    source = replace(source, states=tuple(states))
    geometry.walls = [[Point2D(float(f"{p.x:.6f}"), float(f"{p.y:.6f}")) for p in wall] for wall in geometry.walls]
    if self_intersects(source.points, closed=True) or any(self_intersects(w, closed=True) for w in geometry.walls):
        raise GeometryError("Exported CSV geometry intersects after coordinate quantization")
    gap = minimum_boundary_separation(*geometry.walls, closed=True)
    usable = gap-2*spec.limits.footprint_margin_m
    raster_bound = usable-4*math.sqrt(2)*spec.resolution_m_per_pixel
    if min(usable, raster_bound) < spec.limits.minimum_usable_width_m:
        raise GeometryError("Exported corridor/raster clearance below configured minimum")
    original_s = np.r_[0., np.cumsum([math.hypot(b.x-a.x, b.y-a.y) for a,b in zip(states, states[1:])])]
    lap = float(original_s[-1])
    if not spec.lap_length_range_m[0] <= lap <= spec.lap_length_range_m[1]:
        raise GeometryError(f"Final lap length {lap:.6f} outside requested range {spec.lap_length_range_m}")
    seam_request = spec.seam_offset_m % source.length_m
    seam_index = min(range(len(states)-1), key=lambda i: min(abs(states[i].s-seam_request),
                    source.length_m-abs(states[i].s-seam_request)))
    offset = float(original_s[seam_index])
    sampled = _rotate_samples(source, seam_index)
    annotations, internal = [], {}
    for i, (item, (start, end)) in enumerate(zip(items, source.spans)):
        measured = _source_validation(item, states[start:end+1], spec.track_width_m)
        window_length = float(original_s[end]-original_s[start])
        if item.role == "primary" and window_length+1e-7 < spec.minimum_useful_length_m:
            raise GeometryError("Final primary window below minimum useful segment length")
        identifier = f"maneuver_{i+1:03d}"
        requested = deepcopy(item.maneuver.requested)
        requested.update(composition_role=item.role, inventory_name=item.request_name,
                         inventory_index=item.inventory_index, motif_instance=item.motif_instance,
                         block_instance=item.block_instance, adjustable_connector=item.adjustable)
        annotations.append(dict(id=identifier, type=item.maneuver.type, direction=item.maneuver.direction,
            **interval(float(original_s[start])-offset, window_length, lap), requested=requested,
            measured=measured, difficulty={"label":"unrated"}))
        regions = []
        for j in range(start,end):
            ka,kb = states[j].curvature,states[j+1].curvature
            if max(abs(ka),abs(kb))<=1e-5:
                demand="straight"
            elif ka*kb<0:
                demand="curvature_reversal"
            else:
                demand="left_curve" if ka+kb>0 else "right_curve"
            length=float(original_s[j+1]-original_s[j])
            if regions and regions[-1]["driving_demand"]==demand:
                regions[-1]["length_m"]+=length
            else:
                regions.append(dict(driving_demand=demand, original_start_m=float(original_s[j]), length_m=length))
        internal[identifier]=[dict(driving_demand=r["driving_demand"],
            **interval(r["original_start_m"]-offset,r["length_m"],lap)) for r in regions]
    points=sampled.points
    distances=np.r_[0.,np.cumsum([math.hypot(b.x-a.x,b.y-a.y) for a,b in zip(sampled.states,sampled.states[1:])])]
    curvature=position_curvatures((sampled.states[-2],*sampled.states[:-1],sampled.states[1]))[1:-1]
    geometry.profile=[dict(s_m=float(distances[i]),x_m=s.x,y_m=s.y,heading_rad=s.heading,
        curvature_inv_m=float(curvature[i]),width_m=spec.track_width_m,left_width_m=spec.track_width_m/2,
        right_width_m=spec.track_width_m/2) for i,s in enumerate(sampled.states[:-1])]
    geometry.samples=[CenterlineSample(s.x,s.y,s.heading) for s in sampled.states[:-1]]
    geometry.metrics=profile_metrics(points,geometry.profile)
    metadata.update(generator_version=GENERATOR_VERSION,generation_mode="composite",geometry_family="controlled_composite",
                    maneuvers=annotations,measured=geometry.metrics,difficulty={"label":"unrated"})
    metadata["requested"].update(composite_specification=spec.recipe(),required_primary_families=list(spec.required_families),
        family_exposure_bounds=spec.exposure_bounds,lap_length_range_m=list(spec.lap_length_range_m),
        minimum_useful_length_m=spec.minimum_useful_length_m,clockwise=spec.clockwise,mirrored=spec.mirrored)
    raster=_rasterize_walls(geometry.walls,resolution=spec.resolution_m_per_pixel,padding=spec.padding_m,
                            thickness_px=1,occupancy_mode="corridor")
    validation=metadata["provenance"]["validation"]
    validation.update(exported_global_boundary_separation_m=gap,exported_usable_width_m=usable,
        exported_raster_usable_width_bound_m=raster_bound,
        exported_raster_footprint=validate_raster_footprint(sampled,(*raster,spec.resolution_m_per_pixel),
                                                          spec.vehicle,spec.limits.footprint_margin_m),
        csv_coordinate_precision_m=1e-6)
    validation["feasibility_advisory"] = (feasibility_advisory(sampled,spec.vehicle,speed_m_s=spec.speed_assumption_m_s)
        if spec.speed_assumption_m_s is not None else {"status":"not_requested","physical_drivability":"unassessed"})
    stats=composite_statistics(spec,metadata,sampled,internal)
    primary={a["type"] for a in annotations if a["requested"]["composition_role"]=="primary"}
    if not set(spec.required_families)<=primary:
        raise GeometryError("Final primary inventory is missing a required family")
    for family,(minimum,maximum) in spec.exposure_bounds.items():
        fraction=stats["family_exposure_fractions"][family]
        if not minimum-1e-10<=fraction<=maximum+1e-10:
            raise GeometryError(f"Exposure {family}={fraction:.6f} outside [{minimum}, {maximum}]")
    if stats["supporting_geometry_exposure"]>spec.connectors.maximum_fraction+1e-10:
        raise GeometryError("Supporting connector exposure exceeds requested maximum")
    if not spec.transition_count_range[0]<=stats["primary_family_switch_count"]<=spec.transition_count_range[1]:
        raise GeometryError("Primary family transition count outside requested range")
    symmetry=halfturn_symmetry_error(points)
    if spec.layout=="asymmetric" and symmetry<1e-3:
        raise GeometryError("Asymmetric request produced a point-symmetric layout")
    expected=-math.tau if spec.clockwise else math.tau
    if abs(stats["directional_balance"]["signed_heading_change_rad"]-expected)>1e-7:
        raise GeometryError("Requested winding direction was not preserved")
    stats.update(global_boundary_separation_m=gap,minimum_usable_corridor_width_m=usable,
                 raster_usable_width_lower_bound_m=raster_bound,footprint_margin_m=spec.limits.footprint_margin_m)
    identity=dict(generator=GENERATOR_VERSION,template_version=spec.template_version,
        configuration_sha256=spec.configuration_id,ordered_inventory_sha256=canonical_order_id(spec),
        inventory_multiset_sha256=spec.inventory_id,parent_lineage_id=spec.lineage_id,
        geometry_fingerprint=curvature_profile_fingerprint(items,spec.track_width_m),
        coordinate_fingerprint=coordinate_fingerprint(points,spec.track_width_m),
        candidate_seed=spec.seed,candidate_attempt=spec.attempt,matched_group=spec.matched_group,
        requested_layout=spec.layout,topology="repeated_block" if spec.layout=="symmetric" else "bounded_three_bend_return",
        measured_halfturn_symmetry_error_m=symmetry,vehicle=asdict(spec.vehicle))
    metadata["provenance"].update(experimental_intent={"mode":"composite"},identity=identity,composite_statistics=stats,
        closure_solution=dict(assembly.solution,status="accepted"),closure_attempts=deepcopy(journal),
        lap_seam=dict(requested_offset_m=spec.seam_offset_m,actual_curve_offset_m=states[seam_index].s,
                      actual_csv_offset_m=offset,snapped_to_retained_vertex=True),
        validation_report=f"{spec.track_id}_validation.json",evaluation_csv=f"{spec.track_id}_evaluation.csv",
        evaluation_metadata_only=True,policy_observations_changed=False)
    validate_composite_metadata(metadata)
    return PreparedComposite(settings,geometry,metadata,sampled,assembly,stats)


def canonical_order_id(spec):
    from map_editor.services.specialist_templates import canonical_hash
    return canonical_hash([dict(family=r.family,parameters=r.parameters) for r in spec.inventory])


def prepare_composite(spec: CompositeSpec):
    journal=[]
    try:
        for assembly in assembly_candidates(spec,journal):
            try:
                prepared=_prepare_candidate(spec,assembly,journal)
            except (GeometryError,TrackSpecError) as exc:
                journal[-1].update(status="rejected",reason=str(exc))
                continue
            journal[-1]["status"]="accepted"
            prepared.metadata["provenance"]["closure_attempts"]=deepcopy(journal)
            return prepared
    except (GeometryError,TrackSpecError) as exc:
        raise CompositeGenerationError(str(exc),journal) from exc
    reasons="; ".join(dict.fromkeys(a.get("reason","no solution") for a in journal))
    raise CompositeGenerationError(f"No valid closure within the bounded connector search: {reasons}",journal)


def validate_composite_metadata(metadata):
    validate_geometry_metadata(metadata)
    if metadata["generator_version"]!=GENERATOR_VERSION or metadata["generation_mode"]!="composite":
        raise GeometryError("Composite research intent/version must be explicit")
    stats=metadata["provenance"]["composite_statistics"]
    annotations=metadata["maneuvers"]
    lap=metadata["measured"]["length_m"]
    if abs(sum(a["length_m"] for a in annotations)-lap)>1e-7:
        raise GeometryError("Composite windows must partition the full lap")
    for family,fraction in stats["family_exposure_fractions"].items():
        actual=sum(a["length_m"] for a in annotations if a["type"]==family)/lap
        if abs(actual-fraction)>1e-9:
            raise GeometryError("Composite family exposure disagrees with windows")
    if sum(sum(row.values()) for row in stats["transition_count_matrix"].values())!=len(annotations):
        raise GeometryError("Cyclic transition matrix must count every boundary once")
    ordered=ordered_annotations(annotations)
    label=lambda a:a["type"] if a["requested"]["composition_role"]=="primary" else "connector"
    expected_matrix={a:{b:0 for b in MATRIX_LABELS} for a in MATRIX_LABELS}
    for i,before in enumerate(ordered):
        expected_matrix[label(before)][label(ordered[(i+1)%len(ordered)])]+=1
    if expected_matrix!=stats["transition_count_matrix"] or stats["ordered_maneuver_ids"]!=[a["id"] for a in ordered]:
        raise GeometryError("Transition accounting must match the actual periodic window order")
    if metadata["split"]!="unspecified" or metadata["difficulty"]["label"]!="unrated":
        raise GeometryError("Composite generation does not assign splits or driving ratings")
    for a in annotations:
        children=stats["internal_driving_regions"][a["id"]]
        if abs(sum(r["length_m"] for r in children)-a["length_m"])>1e-7:
            raise GeometryError("Internal driving regions must partition, not add to, a window")
        for child in children:
            if not contains(a,(child["s_start_m"]+child["length_m"]/2)%lap):
                raise GeometryError("Internal driving regions must remain inside their owning maneuver")


def _write_bundle(spec,prepared,directory):
    path=export_track_geometry(prepared.export_settings,prepared.geometry,directory,
        metadata_contract=prepared.metadata,generation_recipe=spec.recipe())
    document=load_map_yaml(path)
    states=prepared.sampled.states
    index=max(0,next((i for i,s in enumerate(states) if s.s>=states[-1].s-1),len(states)-2)-1)
    pose=states[index]
    document.annotations.spawn_points=[SpawnPoint("grid_1",Pose2D(pose.x,pose.y,pose.heading))]
    dump_map_yaml(document,path)
    evaluator=evaluation_rows(prepared.metadata)
    rows=[evaluator(r["s_m"]) for r in prepared.geometry.profile]
    evaluation=directory/f"{spec.track_id}_evaluation.csv"
    with evaluation.open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def generate_composite_bundle(spec,output_dir,*,reference=None,verify_replay=True,prepared=None):
    output_dir=Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite composite directory: {output_dir}")
    prepared=prepared or prepare_composite(spec)
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".composite-",dir=output_dir.parent) as temporary:
        staging=Path(temporary)/"bundle"
        path=_write_bundle(spec,prepared,staging)
        integration=consumer_smoke(path,reference) if reference is not None else {"status":"not_run"}
        names=list(prepared.metadata["artifacts"].values())+[f"{spec.track_id}_evaluation.csv"]
        hashes={name:hashlib.sha256((staging/name).read_bytes()).hexdigest() for name in names}
        replay={"status":"not_run"}
        if verify_replay:
            loaded=load_composite_spec(staging/prepared.metadata["artifacts"]["recipe"])
            regenerated=prepare_composite(loaded)
            replay_dir=Path(temporary)/"replay"
            _write_bundle(loaded,regenerated,replay_dir)
            for name in names:
                if (staging/name).read_bytes()!=(replay_dir/name).read_bytes():
                    raise GeometryError(f"Composite recipe replay changed {name}")
            replay=dict(status="passed",byte_identical=True,artifacts_compared=len(names))
        report=dict(schema_version=1,generator=GENERATOR_VERSION,track_id=spec.track_id,
            geometric_validity="accepted",physical_drivability="unassessed",driving_difficulty="unrated",
            identity=prepared.metadata["provenance"]["identity"],statistics=prepared.statistics,
            validation=prepared.metadata["provenance"]["validation"],
            continuity=prepared.metadata["provenance"]["continuity_residuals"],
            closure_attempts=prepared.metadata["provenance"]["closure_attempts"],
            integration=integration,recipe_replay=replay,artifact_sha256=hashes)
        (staging/f"{spec.track_id}_validation.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
        output_dir.mkdir(exist_ok=False)
        try:
            for artifact in staging.iterdir():
                shutil.move(str(artifact),output_dir/artifact.name)
        except BaseException:
            shutil.rmtree(output_dir)
            raise
    return output_dir/path.name
