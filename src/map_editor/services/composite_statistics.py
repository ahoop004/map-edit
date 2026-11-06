"""Periodic composition and evaluation-only switching geometry, not policy observations."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import asdict
import math
import numpy as np
from map_editor.geometry import GeometryError
from map_editor.services.specialist_templates import canonical_hash, FAMILIES

MATRIX_LABELS = (*FAMILIES, "connector")


def _rounded(value, places):
    value = round(float(value), places)
    return 0. if value == 0 else value


def contains(interval, s):
    # Use the exported profile's nanometer arc precision for boundary ties.
    # Rotating/re-summing a lap can otherwise move a shared endpoint by one ULP.
    s = round(s, 9)
    start, end = round(interval["s_start_m"], 9), round(interval["s_end_m"], 9)
    return (s >= start or s < end) if interval["wraps_seam"] else start <= s < end


def interval(start, length, lap):
    if length <= 0 or length > lap+1e-7:
        raise GeometryError("Invalid periodic interval length")
    start = start % lap
    if abs(start-lap) < 1e-9 or abs(start) < 1e-12:
        start = 0.
    end = (start+length) % lap
    if abs(length-lap) < 1e-9:
        end = start
    if abs(end-lap) < 1e-9 or abs(end) < 1e-9:
        end = 0.
    return dict(s_start_m=float(start), s_end_m=float(end), length_m=float(length), wraps_seam=end <= start)


def _minimal_cycle(values):
    n = len(values)
    if n <= 1:
        return list(values)
    doubled = list(values)*2
    i, j, k = 0, 1, 0
    while i < n and j < n and k < n:
        a, b = doubled[i+k], doubled[j+k]
        if a == b:
            k += 1
            continue
        if a > b:
            i += k+1
            if i <= j:
                i = j+1
        else:
            j += k+1
            if j <= i:
                j = i+1
        k = 0
    begin = min(i, j)
    return doubled[begin:begin+n]


def curvature_profile_fingerprint(items, width):
    segments = []
    for item in items:
        for s in item.maneuver.segments:
            constant = abs(s.k_start-s.k_end) < 1e-12
            value = [s.length_m, s.k_start, s.k_end, "constant" if constant else s.ramp]
            if segments and constant and segments[-1][3] == "constant" and abs(segments[-1][1]-s.k_start) < 1e-12:
                segments[-1][0] += s.length_m
            else:
                segments.append(value)
    if len(segments) > 1 and segments[0][3] == segments[-1][3] == "constant" and abs(segments[0][1]-segments[-1][1]) < 1e-12:
        segments[0][0] += segments[-1][0]
        segments.pop()
    variants = []
    for reverse in (False, True):
        for mirror in (False, True):
            sign = (-1 if reverse else 1)*(-1 if mirror else 1)
            ordered = list(reversed(segments)) if reverse else segments
            tokens = [(_rounded(s[0], 9), _rounded(sign*(s[2] if reverse else s[1]), 9),
                       _rounded(sign*(s[1] if reverse else s[2]), 9), s[3]) for s in ordered]
            variants.append(_minimal_cycle(tokens))
    return canonical_hash({"curvature_profile": min(variants), "width_m": round(width, 9)})


def coordinate_fingerprint(points, width):
    xy = np.array([(p.x, p.y) for p in points])
    variants = []
    for reverse in (False, True):
        p = xy[::-1] if reverse else xy
        edge = np.roll(p, -1, axis=0)-p
        previous = np.roll(edge, 1, axis=0)
        turn = np.arctan2(previous[:, 0]*edge[:, 1]-previous[:, 1]*edge[:, 0], np.sum(previous*edge, axis=1))
        lengths = np.linalg.norm(edge, axis=1)
        for sign in (1, -1):
            tokens = [(_rounded(a, 4), _rounded(float(b)*sign, 4)) for a, b in zip(lengths, turn)]
            variants.append(_minimal_cycle(tokens))
    return canonical_hash({"polygon_signature": min(variants), "width_m": round(width, 5)})


def halfturn_symmetry_error(points):
    xy = np.array([(p.x, p.y) for p in points])
    edges = np.linalg.norm(np.roll(xy, -1, axis=0)-xy, axis=1)
    s = np.r_[0., np.cumsum(edges)]
    position = np.vstack([xy, xy[0]])
    locations = np.linspace(0., s[-1], 256, endpoint=False)
    sampled = np.column_stack([np.interp(locations, s, position[:, i]) for i in (0, 1)])
    center = sampled.mean(axis=0)
    return float(np.max(np.linalg.norm(sampled+np.roll(sampled, 128, axis=0)-2*center, axis=1)))


def ordered_annotations(annotations):
    ordered = sorted(annotations, key=lambda a: a["s_start_m"])
    start = next((i for i, a in enumerate(ordered) if contains(a, 0.)), 0)
    return ordered[start:]+ordered[:start]


def _matrix(labels):
    return {a: {b: 0 for b in labels} for a in labels}


def _region_groups(ordered, label):
    n = len(ordered)
    first = next((i for i in range(n) if label(ordered[i]) != label(ordered[i-1])), 0)
    values = ordered[first:]+ordered[:first]
    groups = []
    for value in values:
        if groups and label(groups[-1][-1]) == label(value):
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def composite_statistics(spec, metadata, sampled, internal_regions):
    annotations = metadata["maneuvers"]
    ordered = ordered_annotations(annotations)
    lap = metadata["measured"]["length_m"]
    label = lambda a: a["type"] if a["requested"]["composition_role"] == "primary" else "connector"
    lengths, primary_lengths, active = defaultdict(float), defaultdict(float), defaultdict(float)
    for a in annotations:
        lengths[a["type"]] += a["length_m"]
        if label(a) != "connector":
            primary_lengths[a["type"]] += a["length_m"]
        active[a["type"]] += sum(r["length_m"] for r in internal_regions[a["id"]] if r["driving_demand"] != "straight")
    fractions = {f: lengths[f]/lap for f in (*FAMILIES, "transition")}
    primary = [a for a in ordered if label(a) != "connector"]
    matrix, projected = _matrix(MATRIX_LABELS), _matrix(FAMILIES)
    events = []
    for i, before in enumerate(ordered):
        after = ordered[(i+1) % len(ordered)]
        matrix[label(before)][label(after)] += 1
        b, a = before["measured"], after["measured"]
        peak_b = max(abs(b["minimum_curvature_inv_m"]), abs(b["maximum_curvature_inv_m"]))
        peak_a = max(abs(a["minimum_curvature_inv_m"]), abs(a["maximum_curvature_inv_m"]))
        significant = (abs(peak_a-peak_b) >= spec.physical_change_curvature_inv_m
                       or (b["turn_signs"] and a["turn_signs"] and b["turn_signs"][-1] != a["turn_signs"][0]))
        events.append(dict(from_id=before["id"], to_id=after["id"], s_m=after["s_start_m"],
            from_label=label(before), to_label=label(after), annotation_label_changed=label(before) != label(after),
            physical_demand_changed=bool(significant), curvature_jump_inv_m=a["start_curvature_inv_m"]-b["end_curvature_inv_m"],
            distance_to_next_boundary_m=after["length_m"],
            curvature_rate_jump_inv_m2=a["start_curvature_rate_inv_m2"]-b["end_curvature_rate_inv_m2"],
            peak_curvature_change_inv_m=peak_a-peak_b,
            peak_curvature_rate_change_inv_m2=a["maximum_sampled_curvature_rate_inv_m2"]-b["maximum_sampled_curvature_rate_inv_m2"]))
    bridges = []
    switches = 0
    for i, before in enumerate(primary):
        after = primary[(i+1) % len(primary)]
        projected[before["type"]][after["type"]] += 1
        switches += before["type"] != after["type"]
        start = ordered.index(before)
        chain = []
        for delta in range(1, len(ordered)):
            value = ordered[(start+delta) % len(ordered)]
            if value["id"] == after["id"]:
                break
            chain.append(value)
        bridges.append(dict(from_id=before["id"], to_id=after["id"],
                            connector_ids=[a["id"] for a in chain], connector_distance_m=sum(a["length_m"] for a in chain)))
    regions = []
    for i, group in enumerate(_region_groups(ordered, label)):
        regions.append(dict(id=f"region_{i+1}", label=label(group[0]), maneuver_ids=[a["id"] for a in group],
                            **interval(group[0]["s_start_m"], sum(a["length_m"] for a in group), lap)))
    primary_switches = [dict(from_id=primary[i]["id"], to_id=primary[(i+1)%len(primary)]["id"],
                             s_m=primary[(i+1)%len(primary)]["s_start_m"])
                        for i in range(len(primary)) if primary[i]["type"] != primary[(i+1)%len(primary)]["type"]]
    for i, event in enumerate(primary_switches):
        event["distance_to_next_primary_switch_m"] = (primary_switches[(i+1)%len(primary_switches)]["s_m"]-event["s_m"]) % lap
    timing = dict(status="not_estimated", speed_assumption_m_s=spec.speed_assumption_m_s,
                  environment_step_s=spec.environment_step_s, selection_intervals_steps=list(spec.selection_intervals_steps),
                  default_selection_steps=spec.default_selection_steps, evaluation_only=True)
    if spec.speed_assumption_m_s is not None:
        timing["status"] = "constant_speed_estimate_only"
        def estimate(length):
            result={"length_m":length,"traversal_time_s":length/spec.speed_assumption_m_s}
            if spec.environment_step_s is not None:
                result["selection_opportunities"]={str(steps):math.floor(length/(spec.speed_assumption_m_s*spec.environment_step_s*steps))
                                                    for steps in spec.selection_intervals_steps}
            return result
        timing["window_estimates"] = {a["id"]:estimate(a["length_m"]) for a in annotations}
        timing["contiguous_region_estimates"]={r["id"]:estimate(r["length_m"]) for r in regions}
        timing["internal_demand_estimates"]={key:[dict(driving_demand=r["driving_demand"],**estimate(r["length_m"])) for r in values]
                                             for key,values in internal_regions.items()}
    changes = np.diff([p.heading for p in sampled.states])
    left, right = float(sum(np.maximum(changes, 0))), float(sum(np.maximum(-changes, 0)))
    signs = [1 if value > 0 else -1 for value in changes if abs(value) > 1e-10]
    alternations = sum(signs[i] != signs[i-1] for i in range(len(signs)))
    return dict(length_m=lap, family_exposure_fractions=fractions,
        primary_exposure_fractions={f: primary_lengths[f]/lap for f in FAMILIES},
        primary_total_exposure=sum(primary_lengths.values())/lap,
        supporting_geometry_exposure=1-sum(primary_lengths.values())/lap,
        active_curvature_exposure_by_family={f: active[f]/lap for f in (*FAMILIES, "transition")},
        primary_distinct_families=len({a["type"] for a in primary}),
        geometric_distinct_families=len({a["type"] for a in annotations}),
        maneuver_counts=dict(Counter(a["type"] for a in primary)),
        ordered_maneuver_ids=[a["id"] for a in ordered], ordered_labels=[label(a) for a in ordered],
        ordered_primary_families=[a["type"] for a in primary],
        transition_matrix_labels=list(MATRIX_LABELS), transition_count_matrix=matrix,
        projected_primary_order_matrix=projected, projected_primary_bridges=bridges,
        annotation_boundary_count=len(ordered), primary_family_switch_count=switches,
        annotation_label_change_count=sum(e["annotation_label_changed"] for e in events),
        physical_demand_change_count=sum(e["physical_demand_changed"] for e in events),
        primary_switch_density_per_100m=100*switches/lap,
        annotation_boundary_density_per_100m=100*len(ordered)/lap,
        physical_demand_change_density_per_100m=100*sum(e["physical_demand_changed"] for e in events)/lap,
        boundary_events=events, contiguous_maneuver_regions=regions,
        primary_switch_events=primary_switches,
        individual_windows=[dict(id=a["id"], label=label(a), **{k: a[k] for k in ("s_start_m", "s_end_m", "length_m", "wraps_seam")}) for a in ordered],
        minimum_primary_window_m=min(a["length_m"] for a in primary), maximum_primary_window_m=max(a["length_m"] for a in primary),
        internal_driving_regions=internal_regions, internal_region_accounting="nested partitions; not additional family exposure",
        directional_balance=dict(left_heading_change_rad=left, right_heading_change_rad=right,
                                 left_fraction=left/(left+right), right_fraction=right/(left+right), signed_heading_change_rad=left-right),
        directional_alternations=alternations,
        total_absolute_heading_change_rad=left+right,
        peak_curvature_inv_m=max(abs(s.curvature) for s in sampled.states),
        peak_curvature_rate_inv_m2=max(abs(s.curvature_rate) for s in sampled.states),
        selector_window_analysis=timing)


def evaluation_rows(metadata):
    """Vertex labels go in a dedicated evaluation CSV, never centerline columns."""
    annotations = metadata["maneuvers"]
    regions = metadata["provenance"]["composite_statistics"]["contiguous_maneuver_regions"]
    lap = metadata["measured"]["length_m"]
    def row(s):
        windows = [a for a in annotations if contains(a, s)]
        groups = [r for r in regions if contains(r, s)]
        if len(windows) != 1 or len(groups) != 1:
            raise GeometryError("Evaluation labels must uniquely partition every lap vertex")
        a, r = windows[0], groups[0]
        return dict(s_m=s, maneuver_id=a["id"], family=a["type"], role=a["requested"]["composition_role"],
                    distance_to_next_maneuver_boundary_m=(a["s_end_m"]-s) % lap,
                    region_id=r["id"], distance_to_next_region_boundary_m=(r["s_end_m"]-s) % lap)
    return row
