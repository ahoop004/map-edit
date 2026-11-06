"""Analytic, adversarial, convergent and independent-consumer Phase 1 tests."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import pytest
import yaml

from map_editor.geometry import (
    CurvatureSegment, Frame, GeometryError, GeometrySequence,
    straight, hairpin, sweeper, chicane, s_curve, transition, sample_parameters,
)
from map_editor.geometry.measurement import MeasurementTolerances, measure, validate_maneuver
from map_editor.geometry.spatial import self_intersects, minimum_boundary_separation
from map_editor.geometry.validation import (
    GeometryLimits,VehicleProfile,validate_geometry,validate_raster_footprint,feasibility_advisory,
)
from map_editor.models.annotations import Point2D
from map_editor.services.geometry_metadata import load_geometry_metadata
from map_editor.services.parametric_track import (
    ParametricTrackSpec,generate_parametric_bundle,load_parametric_spec,prepare_parametric_track,
)
from map_editor.services import procedural_track

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT.parent/"marl_race"


def vehicle():
    # Replay snapshot from the inspected real combined_slip config, independent
    # of whether another developer has the reference checkout installed.
    return VehicleProfile(.5,.27,.15875,.17145,-.523599,.523599,-3.2,3.2,
                          "combined_slip.yaml","test_snapshot","uncalibrated")


def stadium(**kwargs):
    return ParametricTrackSpec("stadium",(straight(12),hairpin(4),straight(12),hairpin(4)),**kwargs)


@pytest.mark.parametrize("spacing",[.2,.1,.025])
def test_analytic_straight_and_circle(spacing):
    line=CurvatureSegment(12).sample(spacing)
    assert all(p.x==pytest.approx(p.s) and p.y==0 and p.curvature==0 for p in line)
    r,angle=4.,1.3
    arc=CurvatureSegment(r*angle,1/r,1/r).sample(spacing)
    for p in arc:
        assert p.x==pytest.approx(r*math.sin(p.s/r),abs=1e-12)
        assert p.y==pytest.approx(r*(1-math.cos(p.s/r)),abs=1e-12)
        assert p.heading==pytest.approx(p.s/r)
        assert p.curvature==1/r
    m=measure(arc)
    assert m["signed_heading_change_rad"]==pytest.approx(angle)
    assert m["geometric_minimum_radius_m"]==pytest.approx(r,abs=1e-9)
    assert abs(m["length_m"]-r*angle)<.003


@pytest.mark.parametrize("ramp",["smoothstep","linear"])
def test_transition_heading_integral_and_derivatives(ramp):
    primitive=CurvatureSegment(3,-.1,.25,ramp)
    start,end=primitive.at(0),primitive.at(3)
    assert end.heading==pytest.approx(3*(.25-.1)/2)
    assert start.curvature==-.1 and end.curvature==pytest.approx(.25)
    if ramp=="smoothstep":
        assert start.curvature_rate==end.curvature_rate==0
        assert primitive.at(1.5).curvature_rate==pytest.approx(1.5*.35/3)
    else:
        assert start.curvature_rate==end.curvature_rate==pytest.approx(.35/3)
    sampled=primitive.sample(.17)
    assert any(p.s==1.5 for p in sampled)
    assert max(b.s-a.s for a,b in zip(sampled,sampled[1:]))<=.17+1e-12


@pytest.mark.parametrize("ramp",["smoothstep","linear"])
def test_position_quadrature_agrees_with_independent_adaptive_integrator(ramp):
    from scipy.integrate import quad
    length,k0,k1=17.,-.4,.8
    primitive=CurvatureSegment(length,k0,k1,ramp)
    def angle(s):
        u=s/length
        integral=u*u/2 if ramp=="linear" else u**3-u**4/2
        return k0*s+(k1-k0)*length*integral
    expected=(quad(lambda s:math.cos(angle(s)),0,length,epsabs=1e-12)[0],
              quad(lambda s:math.sin(angle(s)),0,length,epsabs=1e-12)[0])
    actual=primitive.at(length)
    assert (actual.x,actual.y)==pytest.approx(expected,abs=2e-12)


@pytest.mark.parametrize("constructor",[
    lambda:hairpin(4),lambda:sweeper(6,1.3,end_radius_m=8,entry_transition_m=1,exit_transition_m=1),
    lambda:chicane(4,3,separation_m=2),lambda:s_curve((5,7)),lambda:transition(3,0,.15),
])
def test_deterministic_mirror_and_rigid_transform(constructor):
    maneuver=constructor()
    original=maneuver.sample(.07)
    assert original==maneuver.sample(.07)
    reflected=maneuver.mirrored().sample(.07)
    frame=Frame(10,-3,1.2)
    transformed=maneuver.sample(.07,frame)
    for a,b,c in zip(original,reflected,transformed):
        assert (b.x,b.y,b.heading,b.curvature)==pytest.approx((a.x,-a.y,-a.heading,-a.curvature),abs=1e-11)
        assert (c.x,c.y)==pytest.approx((10+math.cos(1.2)*a.x-math.sin(1.2)*a.y,
                                      -3+math.sin(1.2)*a.x+math.cos(1.2)*a.y),abs=1e-10)
    assert validate_maneuver(maneuver,original)
    assert validate_maneuver(maneuver.mirrored(),reflected)


@pytest.mark.parametrize("spacing",[.2,.1,.025])
@pytest.mark.parametrize("maneuver",[
    straight(40),hairpin(4),hairpin(4,direction="right"),sweeper(7,1.4),
    chicane(4,3,separation_m=2),s_curve((5,7)),transition(3,.1,-.1),
])
def test_feature_classification_and_requested_measurements(maneuver,spacing):
    states=maneuver.sample(spacing)
    measured=validate_maneuver(maneuver,states,width_m=1.5)
    assert measured["curve_arc_length_m"]==pytest.approx(maneuver.length_m)
    assert measured["corridor_width_m"]==1.5
    assert measured["geometric_curvature_error_inv_m"]<.02
    if maneuver.type=="hairpin":
        assert abs(measured["signed_heading_change_rad"])==pytest.approx(math.pi)
        assert measured["minimum_radius_m"]==4
    if maneuver.type in {"chicane","s_curve"}:
        assert measured["turn_signs"]==[1,-1]
        assert measured["direction_reversals"]==1
    if maneuver.type=="chicane":
        assert measured["lateral_displacement_m"]==pytest.approx(3,abs=1e-9)


def test_requested_failures_cannot_be_silently_mislabeled():
    small_turn=hairpin(4,turn_angle_rad=math.pi/2)
    with pytest.raises(GeometryError,match="heading-reversal"):
        validate_maneuver(small_turn,small_turn.sample(.1))
    permissive=MeasurementTolerances(hairpin_min_angle_rad=1.,hairpin_max_angle_rad=2.)
    assert validate_maneuver(small_turn,small_turn.sample(.1),tolerances=permissive)
    turn=hairpin(4)
    with pytest.raises(GeometryError,match="requested radius"):
        validate_maneuver(replace(turn,requested=dict(turn.requested,radius_m=8)),turn.sample(.1))
    line=straight(10)
    with pytest.raises(GeometryError,match="requested length"):
        validate_maneuver(replace(line,requested={"length_m":20}),line.sample(.1))
    compound=s_curve((5,7))
    with pytest.raises(GeometryError,match="opposing radii"):
        validate_maneuver(replace(compound,requested=dict(compound.requested,radii_m=[10,10])),compound.sample(.1))
    with pytest.raises(GeometryError,match="Lateral displacement"):
        chicane(4,.01,separation_m=2,transition_length_m=2)
    with pytest.raises(GeometryError,match="too small"):
        hairpin(2,turn_angle_rad=.1,entry_transition_m=2,exit_transition_m=2)


def test_measurements_converge_as_spacing_decreases():
    primitive=hairpin(4,entry_transition_m=1.3,exit_transition_m=1.7)
    values=[measure(primitive.sample(h)) for h in [.2,.1,.025]]
    errors=[abs(v["length_m"]-primitive.length_m) for v in values]
    assert errors[2]<errors[1]<errors[0]
    assert errors[2]<2e-5
    assert values[2]["geometric_curvature_error_inv_m"]<values[0]["geometric_curvature_error_inv_m"]
    assert all(v["maximum_sampled_curvature_rate_inv_m2"]==pytest.approx(1.5/(4*1.3)) for v in values)
    # Evaluated curve geometry itself is independent of output spacing.
    assert primitive.at(3)==primitive.at(3)


def test_user_ranges_are_seeded_and_order_independent():
    ranges={"radius_m":(3.,8.),"turn_angle_rad":(2.8,3.4)}
    first=sample_parameters(ranges,42)
    assert first==sample_parameters(dict(reversed(list(ranges.items()))),42)
    assert first!=sample_parameters(ranges,43)
    assert all(lo<=first[key]<=hi for key,(lo,hi) in ranges.items())
    with pytest.raises(GeometryError):
        sample_parameters({"radius_m":(2,1)},42)


@pytest.mark.parametrize("kwargs",[{"length_m":0},{"length_m":-1},{"length_m":float("nan")},
                                    {"length_m":1,"k_start":float("inf")},{"length_m":1,"ramp":"unknown"}])
def test_degenerate_segments_reject(kwargs):
    with pytest.raises(GeometryError):
        CurvatureSegment(**kwargs)


def test_connections_check_position_heading_curvature_and_wraparound():
    sequence=GeometrySequence([straight(4)])
    with pytest.raises(GeometryError,match="Position/tangent"):
        sequence.append(straight(3),frame=Frame(4.01,0,0))
    with pytest.raises(GeometryError,match="Position/tangent"):
        sequence.append(straight(3),frame=Frame(4,0,.01))
    sequence.append(straight(3),frame=Frame(4,0,math.tau))
    assert sequence.joints[-1]["heading_rad"]<1e-12
    assert sequence.sample(.1).states[-1].heading==pytest.approx(0)
    with pytest.raises(GeometryError,match="Curvature"):
        sequence.append(sweeper(4,1))
    with pytest.raises(GeometryError,match="Position/tangent"):
        sequence.sample(.1,closed=True)
    smooth=GeometrySequence([straight(4),transition(2,0,.2),sweeper(5,1),transition(2,.2,0),straight(4)]).sample(.1)
    assert max(j["curvature_inv_m"] for j in smooth.joints)==0
    g1=GeometrySequence([straight(4),sweeper(4,1)],require_g2=False).sample(.1)
    with pytest.raises(GeometryError,match="unbounded"):
        validate_geometry(g1,1.5)


def test_self_intersections_and_coarse_sampling_reject():
    with pytest.raises(GeometryError,match="self-intersects"):
        GeometrySequence([sweeper(4,4*math.pi)]).sample(.1,closed=True)
    with pytest.raises(GeometryError,match="resolution|0.2 rad"):
        GeometrySequence([sweeper(1,math.pi)]).sample(1.)
    bowtie=[Point2D(*p) for p in [(0,0),(3,3),(0,3),(3,0)]]
    assert self_intersects(bowtie)
    assert self_intersects(bowtie,use_grid=False)
    assert self_intersects([Point2D(0,0),Point2D(2,0),Point2D(1,0)])


def test_spatial_broad_phase_matches_exhaustive_exact_checks():
    rng=random.Random(42)
    for _ in range(12):
        a=[Point2D(rng.uniform(-5,5),rng.uniform(-5,5)) for _ in range(15)]
        b=[Point2D(rng.uniform(6,10),rng.uniform(-5,5)) for _ in range(12)]
        for closed in [False,True]:
            assert self_intersects(a,closed=closed)==self_intersects(a,closed=closed,use_grid=False)
            assert minimum_boundary_separation(a,b,closed=closed)==pytest.approx(
                minimum_boundary_separation(a,b,closed=closed,use_grid=False),abs=1e-12)
    # A nonpaired pinch must determine separation, even across a long first edge.
    a=[Point2D(0,0),Point2D(10,0)]
    b=[Point2D(10,2),Point2D(5,.1),Point2D(0,2)]
    assert minimum_boundary_separation(a,b)==pytest.approx(.1)


def test_hard_geometry_and_full_footprint_checks():
    sampled=GeometrySequence([hairpin(4)]).sample(.1)
    walls,report=validate_geometry(sampled,1.5,vehicle=vehicle())
    assert 1.49<report["global_boundary_separation_m"]<=1.5
    assert report["footprint"]=="passed_at_sampled_poses"
    assert report["open_endpoint_poses_unassessed"]>0
    with pytest.raises(GeometryError,match="separation"):
        validate_geometry(sampled,.5)
    with pytest.raises(GeometryError,match="footprint"):
        validate_geometry(sampled,1.5,vehicle=replace(vehicle(),width_m=2))
    with pytest.raises(GeometryError,match="radius"):
        validate_geometry(sampled,1.5,limits=GeometryLimits(minimum_radius_m=5))
    with pytest.raises(GeometryError,match="rate"):
        validate_geometry(sampled,1.5,limits=GeometryLimits(maximum_curvature_rate_inv_m2=.1))
    with pytest.raises(GeometryError,match="singularity"):
        validate_geometry(sampled,8.1)


def test_nonlocal_same_wall_clearance_and_raster_width_reject(tmp_path):
    tight=GeometrySequence([straight(4),hairpin(.7,entry_transition_m=.2,exit_transition_m=.2),straight(4)]).sample(.03)
    with pytest.raises(GeometryError,match="Nonlocal boundary gap"):
        validate_geometry(tight,.8,limits=GeometryLimits(minimum_usable_width_m=.5,
            maximum_curvature_rate_inv_m2=20,minimum_nonlocal_boundary_gap_m=.7))
    with pytest.raises(GeometryError,match="raster usable-width"):
        generate_parametric_bundle(replace(stadium(),resolution=.3),tmp_path/"coarse")
    assert not (tmp_path/"coarse").exists()


def test_nonfinite_measurement_and_bad_vehicle_input_reject(tmp_path):
    samples=list(straight(3).sample(.1))
    samples[4]=replace(samples[4],x=float("nan"))
    with pytest.raises(GeometryError,match="finite"):
        measure(samples)
    line=straight(3)
    inconsistent=[replace(p,heading=.2) for p in line.sample(.1)]
    with pytest.raises(GeometryError,match="position/tangent"):
        validate_maneuver(line,inconsistent)
    path=tmp_path/"bad_vehicle.yaml"
    path.write_text("length: 0.5\nwidth: 0.27\n")
    with pytest.raises(GeometryError,match="resolved vehicle"):
        VehicleProfile.from_yaml(path)
    path.write_text("[]\n")
    with pytest.raises(GeometryError,match="resolved vehicle"):
        VehicleProfile.from_yaml(path)


def test_raster_checks_entire_footprint_not_only_corners():
    sampled=GeometrySequence([straight(3)]).sample(.1)
    width,height,resolution=50,30,.1
    pixels=bytearray([255]*(width*height))
    # Obstacle under the center of the body; its four corners are free.
    col,row=15,15
    pixels[(height-1-row)*width+col]=0
    with pytest.raises(GeometryError,match="occupied cell"):
        validate_raster_footprint(sampled,(bytes(pixels),width,height,-1.,-1.5,resolution),vehicle())


def test_vehicle_sources_and_advisory_are_separate_from_validity():
    sampled=GeometrySequence([hairpin(4)]).sample(.1)
    low=feasibility_advisory(sampled,vehicle(),speed_m_s=2)
    high=feasibility_advisory(sampled,vehicle(),speed_m_s=20,lateral_acceleration_limit_m_s2=3)
    assert low["required_lateral_acceleration_m_s2"]==pytest.approx(1.)
    assert high["required_lateral_acceleration_m_s2"]==pytest.approx(100.)
    assert high["curvature_speed_limit_m_s"]==pytest.approx(math.sqrt(12))
    assert high["physical_drivability"]=="unassessed"
    if (REFERENCE/"configs/vehicle/combined_slip.yaml").is_file():
        for name in ["default","combined_slip"]:
            path=REFERENCE/f"configs/vehicle/{name}.yaml"
            actual=VehicleProfile.from_yaml(path)
            assert actual.source_sha256==hashlib.sha256(path.read_bytes()).hexdigest()
        assert VehicleProfile.from_yaml(REFERENCE/"configs/vehicle/default.yaml").width_m!=vehicle().width_m


def test_closed_bundle_bypasses_legacy_fit_replays_metadata_and_seam(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):
        pytest.fail("New geometry passed through legacy sampler")
    monkeypatch.setattr(procedural_track,"_sample_closed_bspline",forbidden)
    spec=stadium(vehicle=vehicle(),random_seed=42)
    first=generate_parametric_bundle(spec,tmp_path/"first")
    metadata=load_geometry_metadata(first.with_name("stadium_metadata.json"))
    assert metadata["schema_version"]=="1.0.0"
    assert metadata["generator_version"]=="map_editor.parametric_curvature.v1"
    assert metadata["generation_mode"]=="composite"
    assert metadata["difficulty"]["label"]=="unrated"
    assert [m["type"] for m in metadata["maneuvers"]]==["straight","hairpin","straight","hairpin"]
    assert metadata["maneuvers"][-1]["wraps_seam"]
    assert metadata["maneuvers"][-1]["s_end_m"]==0
    assert max(j["position_m"] for j in metadata["provenance"]["continuity_residuals"])<1e-12
    replay=load_parametric_spec(first.with_name("stadium_generation.yaml"))
    assert replay==spec
    generate_parametric_bundle(replay,tmp_path/"second")
    for artifact in first.parent.iterdir():
        assert artifact.read_bytes()==(tmp_path/"second"/artifact.name).read_bytes(),artifact.name
    circle=ParametricTrackSpec("circle",(sweeper(4,math.tau),))
    _,_,full_lap,_=prepare_parametric_track(circle)
    only=full_lap["maneuvers"][0]
    assert only["wraps_seam"] and only["s_start_m"]==only["s_end_m"]==0


def test_invalid_new_recipe_or_geometry_writes_nothing(tmp_path):
    path=tmp_path/"recipe.yaml"
    data=stadium().recipe()
    data["generator"]="unknown.v2"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(GeometryError,match="Unsupported"):
        load_parametric_spec(path)
    with pytest.raises(GeometryError):
        generate_parametric_bundle(replace(stadium(),maneuvers=(straight(5),)),tmp_path/"invalid")
    assert not (tmp_path/"invalid").exists()


def test_phase0_checked_in_bundle_still_replays_byte_for_byte(tmp_path):
    golden=ROOT/"sample_maps/phase0_reference"
    recipe=golden/"paper_l_reference_generation.yaml"
    # The checked-in reference was generated by the CLI without QApplication.
    # Qt embeds different default physical-DPI PNG metadata after GUI startup;
    # reproduce the original process context rather than changing legacy output.
    result=subprocess.run([sys.executable,str(ROOT/"scripts/generate_track.py"),str(recipe),
                           "--output",str(tmp_path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    for artifact in golden.iterdir():
        assert artifact.read_bytes()==(tmp_path/artifact.name).read_bytes(),artifact.name


def test_actual_marl_race_loads_new_backend_bundle(tmp_path):
    if not (REFERENCE/"src/utils/map_loader.py").is_file():
        pytest.skip("marl_race checkout unavailable; run scripts/smoke_marl_race.py on closed_stadium bundle")
    path=generate_parametric_bundle(stadium(vehicle=vehicle()),tmp_path/"stadium")
    result=subprocess.run([sys.executable,str(ROOT/"scripts/smoke_marl_race.py"),str(path),
                           "--marl-race-root",str(REFERENCE)],capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)["mpc_clearance_mask_agreement"]=="passed"
