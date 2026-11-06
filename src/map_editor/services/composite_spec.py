"""Versioned ordered composite requests; no Phase 0–2 recipe reinterpretation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import math
from pathlib import Path
import random

import yaml
from map_editor.geometry import GeometryError, straight, hairpin, sweeper, chicane, s_curve, transition
from map_editor.geometry.validation import GeometryLimits, VehicleProfile
from map_editor.services.specialist_templates import canonical_hash, FAMILIES

GENERATOR_VERSION = "map_editor.composite_circuits.v1"
TEMPLATE_VERSION = "block_and_bounded_return.v1"
CONSTRUCTORS = dict(straight=straight, hairpin=hairpin, sweeper=sweeper, chicane=chicane, s_curve=s_curve, transition=transition)


def numeric(value, name, minimum=0., *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum or (positive and value == minimum):
        raise GeometryError(f"Invalid finite numeric value for {name}")


def parameter_location(parameters, key):
    parts = key.split(".")
    if len(parts) == 1:
        if key not in parameters:
            raise GeometryError(f"Unknown parameter range: {key}")
        return parameters, key
    if len(parts) == 2 and parts[0] in parameters and isinstance(parameters[parts[0]], (list, tuple)) and parts[1].isdigit():
        parameters[parts[0]] = list(parameters[parts[0]])
        index = int(parts[1])
        if index < len(parameters[parts[0]]):
            return parameters[parts[0]], index
    raise GeometryError(f"Unknown indexed parameter range: {key}")


@dataclass(frozen=True)
class ManeuverRequest:
    name: str
    family: str
    parameters: dict
    ranges: dict = field(default_factory=dict)
    gap_after_m: float | None = None

    def __post_init__(self):
        if self.gap_after_m is not None:
            numeric(self.gap_after_m, "gap_after_m")
        if not isinstance(self.name, str) or not self.name.strip() or self.family not in CONSTRUCTORS:
            raise GeometryError("A named supported maneuver request is required")
        if not isinstance(self.parameters, dict) or not isinstance(self.ranges, dict):
            raise GeometryError("Maneuver parameters and ranges must be mappings")
        try:
            maneuver = CONSTRUCTORS[self.family](**self.parameters)
        except (TypeError, ValueError) as exc:
            raise GeometryError(f"Invalid request {self.name}: {exc}") from exc
        parameters = deepcopy(maneuver.requested)
        for key, bounds in self.ranges.items():
            parameter_location(parameters, key)
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise GeometryError(f"Invalid range for {self.name}.{key}")
            for value in bounds:
                numeric(value, key, minimum=-1e10)
            if bounds[0] > bounds[1]:
                raise GeometryError(f"Reversed range for {self.name}.{key}")
        object.__setattr__(self, "parameters", parameters)

    def build(self):
        return CONSTRUCTORS[self.family](**deepcopy(self.parameters))


@dataclass(frozen=True)
class ConnectorConstraints:
    radius_range_m: tuple = (3.5, 7.)
    straight_range_m: tuple = (0., 100.)
    transition_length_m: float = 1.
    join_ramp_length_m: float = 1.
    maximum_turn_angle_rad: float = math.pi
    minimum_length_m: float = .5
    maximum_length_m: float = 100.
    maximum_fraction: float = .65
    solver_budget: int = 48

    def __post_init__(self):
        for name in ("radius_range_m", "straight_range_m"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or len(values) != 2:
                raise GeometryError(f"{name} must contain two bounds")
            for value in values:
                numeric(value, name, positive=name == "radius_range_m")
            if values[0] > values[1]:
                raise GeometryError(f"Reversed connector bounds: {name}")
            object.__setattr__(self, name, tuple(values))
        for name in ("transition_length_m", "join_ramp_length_m", "maximum_turn_angle_rad", "minimum_length_m", "maximum_length_m"):
            numeric(getattr(self, name), name, positive=True)
        if self.maximum_turn_angle_rad > math.tau or self.minimum_length_m > self.maximum_length_m:
            raise GeometryError("Invalid connector angle/length limits")
        numeric(self.maximum_fraction, "maximum_fraction")
        if self.maximum_fraction > 1 or type(self.solver_budget) is not int or not 1 <= self.solver_budget <= 256:
            raise GeometryError("Invalid connector fraction or solver budget")


@dataclass(frozen=True)
class CompositeSpec:
    inventory: tuple[ManeuverRequest, ...]
    vehicle: VehicleProfile
    layout: str = "symmetric"
    symmetry_order: int = 2
    motif_repetitions: int = 1
    gap_length_m: float = 1.
    approach_length_m: float = 3.
    connectors: ConnectorConstraints = ConnectorConstraints()
    required_families: tuple = ()
    exposure_bounds: dict = field(default_factory=dict)
    transition_count_range: tuple = (2, 100)
    minimum_useful_length_m: float = 2.
    lap_length_range_m: tuple = (20., 500.)
    track_width_m: float = 1.5
    spacing_m: float = .15
    resolution_m_per_pixel: float = .04
    padding_m: float = 1.
    clockwise: bool = False
    mirrored: bool = False
    seam_offset_m: float = 0.
    speed_assumption_m_s: float | None = None
    environment_step_s: float | None = None
    selection_intervals_steps: tuple = (5, 10, 20)
    default_selection_steps: int = 10
    physical_change_curvature_inv_m: float = .02
    seed: int = 42
    attempt: int = 1
    variant: str = "composite"
    dataset_id: str = "phase3_pilot"
    parent_lineage: str | None = None
    matched_group: str | None = None
    allowed_orders: tuple = ()
    template_version: str = TEMPLATE_VERSION
    generation_mode: str = "composite"
    limits: GeometryLimits = GeometryLimits()

    def __post_init__(self):
        if self.generation_mode != "composite" or self.template_version != TEMPLATE_VERSION:
            raise GeometryError("Unsupported composite intent or template version")
        inventory = tuple(self.inventory)
        if not inventory or len(inventory) > 32 or not all(isinstance(r, ManeuverRequest) for r in inventory):
            raise GeometryError("Composite inventory needs 1..32 named requests")
        if len({r.name for r in inventory}) != len(inventory):
            raise GeometryError("Maneuver request names must be unique")
        primary = {r.family for r in inventory if r.family in FAMILIES}
        if len(primary) < 2:
            raise GeometryError("A composite needs at least two primary maneuver families")
        required = tuple(self.required_families) or tuple(sorted(primary))
        if not set(required) <= primary:
            raise GeometryError("Required primary families are absent from the inventory")
        if not isinstance(self.vehicle, VehicleProfile) or not isinstance(self.connectors, ConnectorConstraints):
            raise GeometryError("A resolved vehicle profile and connector constraints are required")
        if self.layout not in {"symmetric", "asymmetric"} or self.symmetry_order not in (2, 4):
            raise GeometryError("Use a symmetric 2/4-block layout or bounded asymmetric return")
        if type(self.motif_repetitions) is not int or not 1 <= self.motif_repetitions <= 6:
            raise GeometryError("Motif repetitions must be in 1..6")
        for name in ("gap_length_m", "approach_length_m", "padding_m", "seam_offset_m", "physical_change_curvature_inv_m"):
            numeric(getattr(self, name), name)
        for name in ("track_width_m", "spacing_m", "resolution_m_per_pixel", "minimum_useful_length_m"):
            numeric(getattr(self, name), name, positive=True)
        for name in ("transition_count_range", "lap_length_range_m"):
            values = getattr(self, name)
            if len(values) != 2:
                raise GeometryError(f"{name} needs two bounds")
            for value in values:
                numeric(value, name)
            if values[0] > values[1]:
                raise GeometryError(f"Reversed bounds for {name}")
            object.__setattr__(self, name, tuple(values))
        if not all(type(v) is int for v in self.transition_count_range):
            raise GeometryError("Transition counts must be integer bounds")
        for family, bounds in self.exposure_bounds.items():
            if family not in (*FAMILIES, "transition") or len(bounds) != 2:
                raise GeometryError("Invalid family exposure bound")
            if not 0 <= bounds[0] <= bounds[1] <= 1:
                raise GeometryError("Exposure bounds must lie in [0,1]")
        if sum(bounds[0] for bounds in self.exposure_bounds.values()) > 1+1e-12:
            raise GeometryError("Minimum family exposure bounds cannot sum above one")
        if type(self.seed) is not int or self.seed < 0 or type(self.attempt) is not int or self.attempt < 1:
            raise GeometryError("Seed and attempt must be nonnegative/positive integers")
        if type(self.clockwise) is not bool or type(self.mirrored) is not bool:
            raise GeometryError("Traversal and reflection flags must be booleans")
        if not self.variant or not isinstance(self.variant, str) or not self.dataset_id:
            raise GeometryError("Composite variant and dataset identity are required")
        if self.variant in {".", ".."} or any(c in self.variant for c in "/\\\x00"):
            raise GeometryError("Variant names must be safe single filename components")
        for name in ("speed_assumption_m_s", "environment_step_s"):
            if getattr(self, name) is not None:
                numeric(getattr(self, name), name, positive=True)
        steps = tuple(self.selection_intervals_steps)
        if not steps or any(type(s) is not int or s <= 0 for s in steps) or self.default_selection_steps not in steps:
            raise GeometryError("Selection intervals must be positive steps containing the declared default")
        for order in self.allowed_orders:
            if sorted(order) != list(range(len(inventory))):
                raise GeometryError("Allowed orders must be inventory permutations")
        object.__setattr__(self, "inventory", inventory)
        object.__setattr__(self, "required_families", required)
        object.__setattr__(self, "selection_intervals_steps", steps)
        object.__setattr__(self, "allowed_orders", tuple(tuple(p) for p in self.allowed_orders))

    @property
    def configuration_id(self):
        return canonical_hash({"generator": GENERATOR_VERSION, **asdict(self)})

    @property
    def track_id(self):
        return "composite_" + self.configuration_id[:24]

    @property
    def inventory_id(self):
        values = sorted(canonical_hash({"family": r.family, "parameters": r.parameters}) for r in self.inventory)
        return canonical_hash(values)

    @property
    def lineage_id(self):
        return self.parent_lineage or "lineage_" + canonical_hash({"template": self.template_version, "inventory": self.inventory_id})

    def recipe(self):
        return {"schema_version": 1, "generator": GENERATOR_VERSION, **asdict(self)}


def sample_composite_spec(base, seed, attempt=1):
    rng = random.Random(seed)
    requests = {}
    for request in sorted(base.inventory, key=lambda r: r.name):
        parameters = deepcopy(request.parameters)
        for key, bounds in sorted(request.ranges.items()):
            target, index = parameter_location(parameters, key)
            target[index] = rng.uniform(*bounds)
        requests[request.name] = replace(request, parameters=parameters)
    inventory = tuple(requests[r.name] for r in base.inventory)
    if base.allowed_orders:
        order = rng.choice(base.allowed_orders)
        inventory = tuple(inventory[i] for i in order)
    return replace(base, inventory=inventory, seed=seed, attempt=attempt)


def composite_spec_from_recipe(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("generator") != GENERATOR_VERSION:
        raise GeometryError("Unsupported composite recipe version")
    values = dict(data)
    for key in ("schema_version", "generator", "achieved", "files"):
        values.pop(key, None)
    try:
        values["inventory"] = tuple(ManeuverRequest(**r) for r in values["inventory"])
        values["vehicle"] = VehicleProfile(**values["vehicle"])
        values["connectors"] = ConnectorConstraints(**values.get("connectors", {}))
        values["limits"] = GeometryLimits(**values.get("limits", {}))
        return CompositeSpec(**values)
    except (KeyError, TypeError) as exc:
        raise GeometryError(f"Malformed composite recipe: {exc}") from exc


def load_composite_spec(path: Path):
    return composite_spec_from_recipe(yaml.safe_load(path.read_text(encoding="utf-8")))
