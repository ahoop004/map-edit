"""Constrained assembly: repeated SE(2) blocks or a bounded analytic return search."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, replace
import math
import numpy as np

from map_editor.geometry import Frame, GeometryError, Maneuver, straight, sweeper, transition
from map_editor.services.specialist_templates import reverse_traversal


@dataclass(frozen=True)
class AssemblyItem:
    maneuver: Maneuver
    role: str
    request_name: str | None = None
    inventory_index: int | None = None
    motif_instance: int = 0
    block_instance: int = 0
    adjustable: bool = False


@dataclass(frozen=True)
class Assembly:
    items: tuple[AssemblyItem, ...]
    frame: Frame
    solution: dict


def connector(source, purpose, *, adjustable=False):
    """A supporting window is annotated as transition, retaining its source geometry."""
    p = dict(length_m=source.length_m, k_start_inv_m=source.segments[0].k_start,
             k_end_inv_m=source.segments[-1].k_end, source_type=source.type,
             source_parameters=deepcopy(source.requested), connector_purpose=purpose, adjustable=adjustable)
    return AssemblyItem(Maneuver("transition", source.direction, source.segments, p), purpose, adjustable=adjustable)


def end_state(items, frame=Frame()):
    state = None
    for item in items:
        state = item.maneuver.at(item.maneuver.length_m, frame)
        frame = state.frame
    return state


def make_core(spec):
    items = []
    def append(item):
        k0 = items[-1].maneuver.segments[-1].k_end if items else 0.
        k1 = item.maneuver.segments[0].k_start
        if abs(k0-k1) > 1e-10:
            items.append(connector(transition(spec.connectors.join_ramp_length_m, k0, k1), "join_ramp"))
        items.append(item)
    if spec.approach_length_m:
        append(connector(straight(spec.approach_length_m), "approach"))
    for repeat in range(spec.motif_repetitions):
        for index, request in enumerate(spec.inventory):
            maneuver = request.build()
            role = "requested_connector" if request.family == "transition" else "primary"
            if role == "primary" and maneuver.length_m < spec.minimum_useful_length_m:
                raise GeometryError(f"Primary maneuver {request.name} is shorter than the useful-window minimum")
            append(AssemblyItem(maneuver, role, request.name, index, repeat))
            gap = spec.gap_length_m if request.gap_after_m is None else request.gap_after_m
            if gap:
                append(connector(straight(gap), "gap"))
    k = items[-1].maneuver.segments[-1].k_end
    if abs(k) > 1e-10:
        items.append(connector(transition(spec.connectors.join_ramp_length_m, k, 0), "exit_ramp"))
    return items


def _arc(angle, radius, constraints, purpose):
    if abs(angle) < 1e-10:
        return None
    if abs(angle) > constraints.maximum_turn_angle_rad+1e-10:
        raise GeometryError("Closure angle exceeds the designated connector bound")
    return connector(sweeper(radius, abs(angle), "left" if angle > 0 else "right",
                              constraints.transition_length_m, constraints.transition_length_m), purpose, adjustable=True)


def _check_lengths(items, constraints):
    for item in items:
        if item.role != "primary" and not constraints.minimum_length_m <= item.maneuver.length_m <= constraints.maximum_length_m:
            raise GeometryError(f"Connector {item.role} length outside designated bounds")


def _transform(spec, items, solution):
    if spec.mirrored:
        items = [replace(item, maneuver=item.maneuver.mirrored()) for item in items]
    frame = Frame()
    if spec.clockwise != spec.mirrored:
        result = []
        for item in reversed(items):
            maneuver = reverse_traversal(item.maneuver)
            if maneuver.type == "transition":
                requested = dict(maneuver.requested)
                requested["k_start_inv_m"] = -item.maneuver.segments[-1].k_end
                requested["k_end_inv_m"] = -item.maneuver.segments[0].k_start
                maneuver = replace(maneuver, requested=requested)
            result.append(replace(item, maneuver=maneuver))
        items = result
        frame = Frame(heading=math.pi)
    return Assembly(tuple(items), frame, solution)


def assembly_candidates(spec, journal):
    core = make_core(spec)
    state = end_state(core)
    constraints = spec.connectors
    radii = list(dict.fromkeys([constraints.radius_range_m[0], sum(constraints.radius_range_m)/2, constraints.radius_range_m[1]]))
    if spec.layout == "symmetric":
        remaining = math.tau/spec.symmetry_order-state.heading
        if abs(remaining) < 1e-10:
            radii = radii[:1]
        for radius in radii:
            record = dict(index=len(journal)+1, strategy="symmetric", radius_m=radius, correction_angle_rad=remaining)
            journal.append(record)
            try:
                arc = _arc(remaining, radius, constraints, "block_heading")
                block = core + ([arc] if arc else [])
                _check_lengths(block, constraints)
                items = [replace(item, block_instance=block_id) for block_id in range(spec.symmetry_order) for item in block]
                record["status"] = "candidate"
                yield _transform(spec, items, dict(record, symmetry_order=spec.symmetry_order))
            except GeometryError as exc:
                record.update(status="rejected", reason=str(exc))
        return
    # Each trial fixes three smooth bends. Two orthogonal, explicitly adjustable
    # straight lengths solve the remaining position error in a 2x2 linear system.
    headings = [math.pi, math.pi/2, 0., 3*math.pi/2, math.pi/4, 3*math.pi/4, 5*math.pi/4, 7*math.pi/4]
    for radius in radii:
        for heading in headings:
            for middle_sign in (1, -1):
                if len(journal) >= constraints.solver_budget:
                    return
                record = dict(index=len(journal)+1, strategy="asymmetric", radius_m=radius,
                              leg_heading_rad=heading, middle_sign=middle_sign)
                journal.append(record)
                try:
                    first = math.atan2(math.sin(heading-state.heading), math.cos(heading-state.heading))
                    if abs(abs(first)-math.pi) < 1e-10:
                        first = math.pi
                    middle = middle_sign*math.pi/2
                    last = math.tau-state.heading-first-middle
                    arcs = [_arc(a, radius, constraints, f"return_bend_{i+1}") for i, a in enumerate((first, middle, last))]
                    fixed = core + [a for a in arcs if a]
                    finish = end_state(fixed)
                    h1, h2 = state.heading+first, state.heading+first+middle
                    matrix = np.array([[math.cos(h1), math.cos(h2)], [math.sin(h1), math.sin(h2)]])
                    lengths = np.linalg.solve(matrix, -np.array([finish.x, finish.y]))
                    lo, hi = constraints.straight_range_m
                    for value in lengths:
                        if not lo-1e-9 <= value <= hi+1e-9:
                            raise GeometryError(f"Return straight length {value:.6f} m outside [{lo}, {hi}] bounds")
                    # Values indistinguishable from exact zero are omitted, never
                    # replaced by an arbitrary positive connector or geometry fit.
                    lengths = [0. if abs(float(v)) < 1e-9 else float(v) for v in lengths]
                    items = list(core)
                    if arcs[0]:
                        items.append(arcs[0])
                    if lengths[0]:
                        items.append(connector(straight(lengths[0]), "return_leg_1", adjustable=True))
                    if arcs[1]:
                        items.append(arcs[1])
                    if lengths[1]:
                        items.append(connector(straight(lengths[1]), "return_leg_2", adjustable=True))
                    if arcs[2]:
                        items.append(arcs[2])
                    _check_lengths(items, constraints)
                    final = end_state(items)
                    if math.hypot(final.x, final.y) > 1e-7 or abs(final.heading-math.tau) > 1e-7:
                        raise GeometryError("Bounded return solver did not achieve closure tolerance")
                    record.update(status="candidate", straight_lengths_m=lengths,
                                  bend_angles_rad=[first, middle, last], residual_position_m=math.hypot(final.x, final.y))
                    yield _transform(spec, items, dict(record))
                except (GeometryError, np.linalg.LinAlgError) as exc:
                    record.update(status="rejected", reason=str(exc))
