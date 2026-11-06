"""Versioned, constrained specialist templates; Phase 1 primitives stay unchanged."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import math
from pathlib import Path
import random

from map_editor.geometry import Frame, GeometryError, Maneuver, straight, hairpin, sweeper, chicane, s_curve
from map_editor.geometry.validation import GeometryLimits, VehicleProfile

GENERATOR_VERSION = "map_editor.specialist_templates.v1"
TEMPLATE_REVISION = "halfturn.v1"
FAMILIES = ("straight", "hairpin", "sweeper", "chicane", "s_curve")
DEFAULT_EXPOSURE = {"straight": .70, "hairpin": .70, "sweeper": .80, "chicane": .60, "s_curve": .65}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def vehicle_kinematic_radius(vehicle):
    steering = min(abs(vehicle.steering_min_rad), vehicle.steering_max_rad)
    return math.hypot((vehicle.lf_m + vehicle.lr_m) / math.tan(steering), vehicle.lr_m)


def default_parameters(family, vehicle):
    if family not in FAMILIES:
        raise GeometryError(f"Unknown specialist family: {family}")
    radius = vehicle_kinematic_radius(vehicle)
    params = dict(approach_length_m=max(1., 2 * vehicle.length_m), exit_length_m=max(1., 2 * vehicle.length_m),
                  connector_radius_m=max(3., 4 * radius), connector_transition_m=1.,
                  track_width_m=max(1.5, vehicle.width_m + .8), spacing_m=.15,
                  resolution_m_per_pixel=.04, padding_m=1.)
    if family == "straight":
        params.update(maneuver_length_m=max(30., 60 * vehicle.length_m))
    elif family in {"hairpin", "sweeper"}:
        params.update(turn_radius_m=max(3. if family == "hairpin" else 7., (5 if family == "hairpin" else 10) * radius),
                      turn_angle_rad=math.pi, transition_length_m=1.)
    elif family == "chicane":
        params.update(turn_radius_m=max(4., 6 * radius), lateral_displacement_m=3., chicane_spacing_m=2.,
                      transition_length_m=1., repetitions=3, inter_maneuver_straight_m=0.)
    else:
        params.update(first_radius_m=max(4., 6 * radius), second_radius_m=max(5., 7 * radius),
                      turn_angle_rad=math.pi/3, transition_length_m=1., repetitions=3,
                      inter_maneuver_straight_m=0.)
    return params


def default_ranges(family, vehicle):
    """Conservative geometry exploration ranges, not a driving-success claim."""
    params = default_parameters(family, vehicle)
    ranges = {}
    keys = {"straight": ("maneuver_length_m",), "hairpin": ("turn_radius_m", "transition_length_m"),
            "sweeper": ("turn_radius_m", "transition_length_m"),
            "chicane": ("turn_radius_m", "lateral_displacement_m", "chicane_spacing_m"),
            "s_curve": ("first_radius_m", "second_radius_m", "turn_angle_rad")}[family]
    for key in keys:
        ranges[key] = [params[key] * .9, params[key] * 1.15]
    return ranges


@dataclass(frozen=True)
class SpecialistSpec:
    target_family: str
    vehicle: VehicleProfile
    parameters: dict = field(default_factory=dict)
    seed: int = 42
    variant_number: int = 1
    minimum_target_exposure: float | None = None
    clockwise: bool = False
    dataset_id: str = "phase2_pilot"
    parent_lineage: str | None = None
    experimental_mode: str = "specialist"
    template_revision: str = TEMPLATE_REVISION
    limits: GeometryLimits = GeometryLimits()

    def __post_init__(self):
        if self.target_family not in FAMILIES or self.experimental_mode != "specialist":
            raise GeometryError("Specialist intent and one supported target family are required")
        if self.template_revision != TEMPLATE_REVISION:
            raise GeometryError("Unsupported specialist template revision")
        if not isinstance(self.vehicle, VehicleProfile):
            raise GeometryError("A resolved vehicle profile is required")
        if type(self.seed) is not int or self.seed < 0 or type(self.variant_number) is not int or self.variant_number < 1:
            raise GeometryError("Seed must be nonnegative and variant number must be positive integers")
        if type(self.clockwise) is not bool or not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise GeometryError("Invalid traversal or dataset identifier")
        if self.parent_lineage is not None and (not isinstance(self.parent_lineage, str) or not self.parent_lineage.strip()):
            raise GeometryError("Parent lineage must be a nonempty string")
        minimum = DEFAULT_EXPOSURE[self.target_family] if self.minimum_target_exposure is None else self.minimum_target_exposure
        if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not math.isfinite(minimum) or not .5 <= minimum <= 1:
            raise GeometryError("Minimum specialist exposure must be in [0.5, 1]")
        object.__setattr__(self, "minimum_target_exposure", float(minimum))
        defaults = default_parameters(self.target_family, self.vehicle)
        if not isinstance(self.parameters, dict):
            raise GeometryError("Parameters must be a mapping")
        permitted = set(defaults) | {"maneuver_length_m"}
        if set(self.parameters) - permitted:
            raise GeometryError(f"Unsupported parameters: {sorted(set(self.parameters)-permitted)}")
        values = dict(defaults, **self.parameters)
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise GeometryError(f"{name} must be a finite numeric value")
            zero_allowed = name in {"approach_length_m", "exit_length_m", "chicane_spacing_m", "inter_maneuver_straight_m", "padding_m"}
            if value < 0 or (value == 0 and not zero_allowed):
                raise GeometryError(f"{name} must be {'nonnegative' if zero_allowed else 'positive'}")
        if "repetitions" in values and (type(values["repetitions"]) is not int or not 1 <= values["repetitions"] <= 12):
            raise GeometryError("Repetitions must be an integer in [1, 12]")
        object.__setattr__(self, "parameters", values)

    @property
    def lineage_id(self):
        return self.parent_lineage or "lineage_" + canonical_hash({"template": self.target_family, "revision": self.template_revision})

    @property
    def shape_id(self):
        geometric = {k: v for k, v in self.parameters.items() if k not in {"spacing_m", "resolution_m_per_pixel", "padding_m"}}
        return "shape_" + canonical_hash({"template": self.target_family, "revision": self.template_revision, "parameters": geometric})

    @property
    def configuration_id(self):
        return canonical_hash({"generator": GENERATOR_VERSION, **asdict(self)})

    @property
    def track_id(self):
        return f"{self.target_family}_{self.variant_number:03d}_{self.configuration_id[:20]}"

    def recipe(self):
        return {"schema_version": 1, "generator": GENERATOR_VERSION, **asdict(self)}


def sample_spec(base: SpecialistSpec, ranges: dict, seed: int):
    rng = random.Random(seed)
    sampled = dict(base.parameters)
    for name, bounds in sorted(ranges.items()):
        if name not in sampled or not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            raise GeometryError(f"Invalid numeric parameter range: {name}")
        lo, hi = bounds
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds) or lo > hi:
            raise GeometryError(f"Invalid finite ordered bounds for {name}")
        if name == "repetitions":
            if type(lo) is not int or type(hi) is not int:
                raise GeometryError("Repetition ranges need integer bounds")
            sampled[name] = rng.randint(lo, hi)
        else:
            sampled[name] = rng.uniform(lo, hi)
    return replace(base, parameters=sampled, seed=seed)


def load_specialist_spec(path: Path):
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return specialist_spec_from_recipe(data)


def specialist_spec_from_recipe(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("generator") != GENERATOR_VERSION:
        raise GeometryError("Unsupported specialist recipe version")
    values = dict(data)
    for key in ("schema_version", "generator", "achieved", "files"):
        values.pop(key, None)
    try:
        values["vehicle"] = VehicleProfile(**values["vehicle"])
        values["limits"] = GeometryLimits(**values.get("limits", {}))
        return SpecialistSpec(**values)
    except (TypeError, KeyError) as exc:
        raise GeometryError(f"Malformed specialist recipe: {exc}") from exc


def reverse_traversal(maneuver):
    """Reverse physical travel, rather than mirroring the circuit's layout."""
    requested = dict(maneuver.requested)
    direction = {"left": "right", "right": "left", "none": "none",
                 "left_right": "left_right", "right_left": "right_left"}[maneuver.direction]
    if "direction" in requested:
        requested["direction"] = direction
    if "entry_transition_m" in requested:
        requested["entry_transition_m"], requested["exit_transition_m"] = requested["exit_transition_m"], requested["entry_transition_m"]
    if requested.get("end_radius_m") is not None:
        requested["radius_m"], requested["end_radius_m"] = requested["end_radius_m"], requested["radius_m"]
    if "radii_m" in requested:
        requested["radii_m"] = list(reversed(requested["radii_m"]))
    return Maneuver(maneuver.type, direction,
                    tuple(replace(s, k_start=-s.k_end, k_end=-s.k_start) for s in reversed(maneuver.segments)), requested)


def build_template(spec: SpecialistSpec):
    p, family = spec.parameters, spec.target_family
    block, roles = [], []
    def add(maneuver, role):
        block.append(maneuver)
        roles.append(role)
    def line(length, role):
        if length:
            add(straight(length), role)
    line(p["approach_length_m"], "approach")
    if family == "straight":
        add(straight(p["maneuver_length_m"]), "target")
    elif family in {"hairpin", "sweeper"}:
        constructor = hairpin if family == "hairpin" else sweeper
        add(constructor(p["turn_radius_m"], p["turn_angle_rad"],
                        entry_transition_m=p["transition_length_m"], exit_transition_m=p["transition_length_m"]), "target")
        delta = math.pi-p["turn_angle_rad"]
        if abs(delta) > 1e-12:
            add(sweeper(p["connector_radius_m"], abs(delta), "left" if delta > 0 else "right",
                        p["connector_transition_m"], p["connector_transition_m"]), "heading_connector")
    else:
        target = (chicane(p["turn_radius_m"], p["lateral_displacement_m"], p["chicane_spacing_m"], p["transition_length_m"])
                  if family == "chicane" else s_curve((p["first_radius_m"], p["second_radius_m"]),
                                                      p["turn_angle_rad"], p["transition_length_m"]))
        for i in range(p["repetitions"]):
            if i:
                line(p["inter_maneuver_straight_m"], "repetition_connector")
            add(target, "target")
    line(p["exit_length_m"], "exit")
    if family in {"straight", "chicane", "s_curve"}:
        add(hairpin(p["connector_radius_m"], entry_transition_m=p["connector_transition_m"],
                    exit_transition_m=p["connector_transition_m"]), "closure_connector")
    target_lengths = [m.length_m for m, role in zip(block, roles) if role == "target"]
    if family != "straight" and "maneuver_length_m" in p and any(not math.isclose(length, p["maneuver_length_m"], abs_tol=1e-7, rel_tol=1e-8) for length in target_lengths):
        raise GeometryError("Requested maneuver length conflicts with the specified radii, angles and transitions")
    maneuvers, roles = block*2, roles*2
    frame = Frame()
    if spec.clockwise:
        maneuvers = [reverse_traversal(m) for m in reversed(maneuvers)]
        roles = list(reversed(roles))
        frame = Frame(heading=math.pi)
    return tuple(maneuvers), tuple(roles), frame
