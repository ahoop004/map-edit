"""Eight controlled composite cases, with bounded retries and matched-order auditing."""
from __future__ import annotations
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import platform
import random
from time import perf_counter

from map_editor.geometry import GeometryError
from map_editor.services.composite_spec import CompositeSpec, ManeuverRequest, composite_spec_from_recipe, sample_composite_spec, GENERATOR_VERSION
from map_editor.services.composite_tracks import prepare_composite, generate_composite_bundle


@dataclass(frozen=True)
class CompositePilotRequest:
    category: str
    expected_primary_families: int
    base: CompositeSpec


def default_composite_requests(vehicle):
    def request(name,family,**parameters):
        return ManeuverRequest(name,family,parameters)
    S=request("straight","straight",length_m=15)
    C=request("chicane","chicane",radius_m=4,lateral_displacement_m=3,separation_m=2)
    U=request("s_curve","s_curve",radii_m=[4,5],turn_angle_rad=math.pi/3)
    L=request("sweeper_left","sweeper",radius_m=7,turn_angle_rad=math.pi/4,entry_transition_m=1,exit_transition_m=1)
    R=request("sweeper_right","sweeper",radius_m=7,turn_angle_rad=math.pi/4,direction="right",entry_transition_m=1,exit_transition_m=1)
    H=request("hairpin","hairpin",radius_m=8)
    base=dict(vehicle=vehicle,seam_offset_m=5.,speed_assumption_m_s=2.,environment_step_s=.05)
    definitions=[
        ("two_families",2,CompositeSpec((S,C),variant="two_symmetric",**base)),
        ("two_families",2,CompositeSpec((replace(S,parameters={"length_m":18}),H),layout="asymmetric",variant="two_asymmetric",clockwise=True,approach_length_m=4.,**base)),
        ("three_families",3,CompositeSpec((S,C,U),variant="three_symmetric",approach_length_m=4.,gap_length_m=1.5,**base)),
        ("three_families",3,CompositeSpec((L,S,R,H),layout="asymmetric",variant="three_asymmetric",approach_length_m=6.,gap_length_m=2.,**base)),
        ("five_families",5,CompositeSpec((S,C,U,L,R,H),variant="five_symmetric",gap_length_m=.75,**base)),
        ("five_families",5,CompositeSpec((replace(U,parameters=dict(U.parameters,radii_m=[4.5,6],turn_angle_rad=1.)),
            replace(S,parameters={"length_m":18}),replace(C,parameters=dict(C.parameters,radius_m=4.8,lateral_displacement_m=3.5)),
            replace(L,parameters=dict(L.parameters,radius_m=8,turn_angle_rad=math.pi/3)),
            replace(R,parameters=dict(R.parameters,radius_m=8,turn_angle_rad=math.pi/3)),
            replace(H,parameters=dict(H.parameters,radius_m=9))),layout="asymmetric",variant="five_asymmetric",mirrored=True,approach_length_m=2.5,gap_length_m=1.2,**base)),
    ]
    a=request("straight_a","straight",length_m=8)
    b=request("straight_b","straight",length_m=5)
    c=replace(C,parameters=dict(C.parameters,lateral_displacement_m=2.5))
    u=replace(U,parameters=dict(U.parameters,turn_angle_rad=math.pi/4))
    l=replace(L,parameters=dict(L.parameters,radius_m=6,turn_angle_rad=math.pi/5))
    r=replace(R,parameters=dict(R.parameters,radius_m=6,turn_angle_rad=math.pi/5))
    definitions.extend([
        ("matched_order",5,CompositeSpec((a,c,u,b,l,r,H),variant="matched_order_a",gap_length_m=.8,matched_group="inventory_order_pair_v1",**base)),
        ("matched_order",5,CompositeSpec((b,u,a,c,l,r,H),variant="matched_order_b",gap_length_m=.8,matched_group="inventory_order_pair_v1",**base)),
    ])
    return tuple(CompositePilotRequest(*definition) for definition in definitions)


def pilot_recipe(requests,seed,budget):
    return dict(schema_version=1,generator=GENERATOR_VERSION,kind="composite_pilot",seed=seed,max_attempts_per_request=budget,
                requests=[dict(category=r.category,expected_primary_families=r.expected_primary_families,base=r.base.recipe()) for r in requests])


def load_composite_pilot(path):
    data=json.loads(Path(path).read_text())
    if data.get("schema_version")!=1 or data.get("generator")!=GENERATOR_VERSION or data.get("kind")!="composite_pilot":
        raise GeometryError("Unsupported composite pilot recipe")
    requests=tuple(CompositePilotRequest(r["category"],r["expected_primary_families"],composite_spec_from_recipe(r["base"])) for r in data["requests"])
    return requests,data["seed"],data["max_attempts_per_request"]


def generate_composite_pilot(requests,output_dir,*,reference,seed=42,max_attempts=4,profile_path=None,progress=None):
    if type(seed) is not int or seed<0 or type(max_attempts) is not int or not 1<=max_attempts<=100:
        raise GeometryError("Invalid composite pilot seed or bounded candidate budget")
    output_dir=Path(output_dir)
    if output_dir.exists() or (profile_path is not None and Path(profile_path).exists()):
        raise FileExistsError("Composite output/evidence paths must be fresh")
    if not (Path(reference)/"src/utils/map_loader.py").is_file():
        raise GeometryError("A local marl_race checkout is required for composite pilot acceptance")
    if len({r.base.variant for r in requests})!=len(requests):
        raise GeometryError("Composite pilot variants must be unique")
    output_dir.mkdir(parents=True,exist_ok=False)
    (output_dir/"pilot_recipe.json").write_text(json.dumps(pilot_recipe(requests,seed,max_attempts),indent=2)+"\n")
    report=dict(schema_version=1,generator=GENERATOR_VERSION,requested_tracks=len(requests),seed=seed,max_attempts_per_request=max_attempts,
                complete=False,accepted=[],rejected=[],incomplete_requests=[],matched_comparisons=[])
    def save():
        (output_dir/"manifest.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    save()
    rng=random.Random(seed)
    fingerprints,coordinates,identifiers=set(),set(),set()
    matched={}
    timings=[]
    started=perf_counter()
    for request in requests:
        success=False
        for attempt in range(1,max_attempts+1):
            candidate_seed=rng.getrandbits(63)
            candidate=None
            start=perf_counter()
            try:
                candidate=sample_composite_spec(request.base,candidate_seed,attempt)
                prepared=prepare_composite(candidate)
                identity=prepared.metadata["provenance"]["identity"]
                if candidate.track_id in identifiers or identity["geometry_fingerprint"] in fingerprints or identity["coordinate_fingerprint"] in coordinates:
                    raise GeometryError("Duplicate/cyclic-equivalent geometry is not an independent layout")
                if prepared.statistics["primary_distinct_families"]!=request.expected_primary_families:
                    raise GeometryError("Pilot primary-family inventory does not match its declared category")
                group=candidate.matched_group
                comparison=None
                if group and group in matched:
                    prior=matched[group]
                    if identity["inventory_multiset_sha256"]!=prior["identity"]["inventory_multiset_sha256"]:
                        raise GeometryError("Matched-order comparison changed the requested parameter inventory")
                    if prepared.statistics["maneuver_counts"]!=prior["statistics"]["maneuver_counts"]:
                        raise GeometryError("Matched-order comparison changed maneuver counts")
                    delta=max(abs(prepared.statistics["family_exposure_fractions"][f]-prior["statistics"]["family_exposure_fractions"][f])
                              for f in prepared.statistics["family_exposure_fractions"])
                    if delta>1e-5:
                        raise GeometryError("Matched-order family exposure changed beyond numerical tolerance")
                    if identity["ordered_inventory_sha256"]==prior["identity"]["ordered_inventory_sha256"]:
                        raise GeometryError("Matched-order comparison did not change ordering")
                    comparison=dict(group=group,first_id=prior["track_id"],second_id=candidate.track_id,
                                    inventory_equal=True,maneuver_counts_equal=True,maximum_family_exposure_delta=delta)
                prepare_seconds=perf_counter()-start
                publish_start=perf_counter()
                path=generate_composite_bundle(candidate,output_dir/candidate.track_id,reference=reference,prepared=prepared)
                publish_seconds=perf_counter()-publish_start
            except GeometryError as exc:
                report["rejected"].append(dict(category=request.category,variant=request.base.variant,attempt=attempt,seed=candidate_seed,
                    reason=str(exc),recipe=candidate.recipe() if candidate else request.base.recipe(),closure_attempts=getattr(exc,"attempts",[])))
                timings.append(dict(variant=request.base.variant,attempt=attempt,status="rejected",seconds=perf_counter()-start))
                if progress:
                    progress(f"Rejected {request.base.variant} attempt {attempt}: {exc}")
                save()
                continue
            fingerprints.add(identity["geometry_fingerprint"])
            coordinates.add(identity["coordinate_fingerprint"])
            identifiers.add(candidate.track_id)
            entry=dict(track_id=candidate.track_id,category=request.category,variant=candidate.variant,
                seed=candidate.seed,attempt=attempt,map=str(path.relative_to(output_dir)),
                metadata=f"{candidate.track_id}/{candidate.track_id}_metadata.json",recipe=f"{candidate.track_id}/{candidate.track_id}_generation.yaml",
                validation_report=f"{candidate.track_id}/{candidate.track_id}_validation.json",identity=identity,
                statistics=prepared.statistics,integration="passed",recipe_replay="passed",physical_drivability="unassessed",difficulty="unrated",split="unspecified")
            report["accepted"].append(entry)
            if group:
                if comparison:
                    report["matched_comparisons"].append(comparison)
                matched[group]=entry
            timings.append(dict(variant=candidate.variant,status="accepted",prepare_seconds=prepare_seconds,
                                publish_replay_smoke_seconds=publish_seconds,closure_trials=len(prepared.metadata["provenance"]["closure_attempts"])))
            if progress:
                progress(f"Accepted {candidate.variant}: {prepared.statistics['primary_distinct_families']} primary families, {prepared.statistics['length_m']:.2f} m, {candidate.layout}")
            success=True
            save()
            break
        if not success:
            report["incomplete_requests"].append(dict(variant=request.base.variant,attempts_exhausted=max_attempts))
    report["complete"]=len(report["accepted"])==len(requests)
    save()
    if profile_path is not None:
        Path(profile_path).parent.mkdir(parents=True,exist_ok=True)
        Path(profile_path).write_text(json.dumps(dict(python=platform.python_version(),platform=platform.platform(),
            total_seconds=perf_counter()-started,attempts=timings,note="Timing is separate from deterministic track artifacts; publication includes native recipe replay and actual consumer smoke."),indent=2)+"\n")
    return report
