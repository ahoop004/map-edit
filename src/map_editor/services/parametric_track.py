"""New geometry backend → shared Phase 0 bundle writer, without spline fitting."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from pathlib import Path
import numpy as np
import yaml

from map_editor.exporters.centerline import CenterlineSample
from map_editor.geometry import GENERATOR_VERSION, CurvatureSegment, Frame, GeometryError, GeometrySequence, Maneuver
from map_editor.geometry.sequence import ContinuityTolerances
from map_editor.geometry.measurement import MeasurementTolerances, position_curvatures, validate_maneuver
from map_editor.geometry.validation import (
    GeometryLimits, VehicleProfile, feasibility_advisory, validate_geometry, validate_raster_footprint,
)
from map_editor.services.geometry_metadata import build_geometry_metadata, validate_geometry_metadata
from map_editor.services.procedural_track import (
    TrackGeometry, TrackSpec, _rasterize_walls, _validate_corridor_raster, _validate_spec, export_track_geometry,
)
from map_editor.services.track_profile import profile_metrics


@dataclass(frozen=True)
class ParametricTrackSpec:
    stem: str
    maneuvers: tuple[Maneuver,...]
    spacing_m: float = .1
    width_m: float = 1.5
    resolution: float = .03
    padding: float = 1.
    frame: Frame = Frame()
    require_g2: bool = True
    continuity: ContinuityTolerances = ContinuityTolerances()
    measurements: MeasurementTolerances = MeasurementTolerances()
    limits: GeometryLimits = GeometryLimits()
    vehicle: VehicleProfile | None = None
    random_seed: int | None = None
    dataset_id: str | None = None
    split: str = "unspecified"

    def recipe(self):
        return dict(schema_version=1,generator=GENERATOR_VERSION,closed=True,**asdict(self))


def load_parametric_spec(path: Path):
    data=yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("schema_version")!=1 or data.get("generator")!=GENERATOR_VERSION or data.get("closed") is not True:
        raise GeometryError("Unsupported parametric closed-track recipe")
    data=dict(data)
    for key in ("schema_version","generator","closed","achieved","files"):
        data.pop(key,None)
    try:
        data["maneuvers"]=tuple(Maneuver(type=m["type"],direction=m["direction"],requested=m["requested"],
                                segments=tuple(CurvatureSegment(**s) for s in m["segments"])) for m in data["maneuvers"])
        for key,cls in [("frame",Frame),("continuity",ContinuityTolerances),("measurements",MeasurementTolerances),
                        ("limits",GeometryLimits),("vehicle",VehicleProfile)]:
            if key in data and data[key] is not None:
                data[key]=cls(**data[key])
        return ParametricTrackSpec(**data)
    except (KeyError,TypeError) as exc:
        raise GeometryError(f"Malformed parametric recipe: {exc}") from exc


def periodic_interval(start,end,length):
    """Map ordered [start,end] chord distances into schema 1.0.0 intervals."""
    if not 0 <= start < end <= length:
        raise GeometryError("Invalid ordered lap interval")
    s_end=0. if math.isclose(end,length,abs_tol=1e-10,rel_tol=0.) else end
    return dict(s_start_m=start,s_end_m=s_end,length_m=end-start,wraps_seam=s_end<=start)


def prepare_parametric_track(spec: ParametricTrackSpec):
    sampled=GeometrySequence(spec.maneuvers,frame=spec.frame,require_g2=spec.require_g2,tolerances=spec.continuity).sample(spec.spacing_m,closed=True)
    # Validate export settings with the existing checks, without invoking fitting.
    proxy=TrackSpec(stem=spec.stem,control_points=sampled.points,
        track_width=spec.width_m,centerline_spacing=spec.spacing_m,resolution=spec.resolution,padding=spec.padding,
        wall_thickness_px=1,min_curvature_radius=spec.limits.minimum_radius_m,
        min_wall_separation=spec.limits.minimum_usable_width_m,occupancy_mode="corridor",
        target_length=sampled.length_m,provenance={"family":"parametric_sequence"})
    _validate_spec(proxy)
    measured=[]
    for maneuver,(start,end) in zip(sampled.maneuvers,sampled.spans):
        measured.append(validate_maneuver(maneuver,sampled.states[start:end+1],width_m=spec.width_m,tolerances=spec.measurements))
    walls,validation=validate_geometry(sampled,spec.width_m,limits=spec.limits,vehicle=spec.vehicle)
    pixels,width,height,ox,oy=_rasterize_walls(walls,resolution=spec.resolution,padding=spec.padding,thickness_px=1,occupancy_mode="corridor")
    _validate_corridor_raster(sampled.points,pixels,width,height,ox,oy,spec.resolution)
    # Conservative allowance for endpoint flooring, the Bresenham cell stroke,
    # and cell area on both sides of a vector corridor (one-pixel walls only).
    raster_width_bound=validation["minimum_usable_corridor_width_m"]-4*math.sqrt(2)*spec.resolution
    if raster_width_bound<spec.limits.minimum_usable_width_m:
        raise GeometryError("Conservative raster usable-width bound is below the configured minimum")
    validation["raster_usable_width_lower_bound_m"]=raster_width_bound
    if spec.vehicle:
        validation["raster_footprint"]=validate_raster_footprint(sampled,(pixels,width,height,ox,oy,spec.resolution),
                                                               spec.vehicle,spec.limits.footprint_margin_m)
        validation["feasibility_advisory"]=feasibility_advisory(sampled,spec.vehicle)
    states=sampled.states
    distances=np.r_[0.,np.cumsum([math.hypot(b.x-a.x,b.y-a.y) for a,b in zip(states,states[1:])])]
    # Reconstruct curvature independently on the actual exported closed polygon.
    curvature=position_curvatures((states[-2],*states[:-1],states[1]))[1:-1]
    profile=[dict(s_m=float(distances[i]),x_m=p.x,y_m=p.y,heading_rad=p.heading,
                  curvature_inv_m=float(curvature[i]),width_m=spec.width_m,
                  left_width_m=spec.width_m/2,right_width_m=spec.width_m/2) for i,p in enumerate(states[:-1])]
    metrics=profile_metrics(sampled.points,profile)
    geometry=TrackGeometry([CenterlineSample(p.x,p.y,p.heading) for p in states[:-1]],walls,profile,metrics)
    metadata=build_geometry_metadata(proxy,metrics)
    metadata.update(generator_version=GENERATOR_VERSION,dataset_id=spec.dataset_id,random_seed=spec.random_seed,split=spec.split,
                    generation_mode="composite" if len({m.type for m in spec.maneuvers})>1 else "specialist",
                    difficulty={"label":"unrated"})
    metadata["requested"].update(curve_arc_length_m=sampled.length_m)
    metadata["provenance"].update(validation=validation,continuity_residuals=list(sampled.joints),
                                  measurement_tolerances=asdict(spec.measurements),continuity_tolerances=asdict(spec.continuity))
    metadata["maneuvers"]=[dict(id=f"{m.type}_{i+1}",type=m.type,direction=m.direction,
        **periodic_interval(float(distances[start]),float(distances[end]),float(distances[-1])),
        requested=dict(m.requested),measured=measured[i],
        difficulty={"label":"unrated","indicators":{"absolute_heading_change_rad":measured[i]["absolute_heading_change_rad"]}})
        for i,(m,(start,end)) in enumerate(zip(sampled.maneuvers,sampled.spans))]
    validate_geometry_metadata(metadata)
    return proxy,geometry,metadata,sampled


def generate_parametric_bundle(spec: ParametricTrackSpec,output_dir: Path):
    proxy,geometry,metadata,_=prepare_parametric_track(spec)
    return export_track_geometry(proxy,geometry,output_dir,metadata_contract=metadata,generation_recipe=spec.recipe())
