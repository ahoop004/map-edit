# Phase 1 geometry and parameter contract

This backend is `map_editor.parametric_curvature.v1`. It is independent of
`map_editor.closed_bspline.v1`: no fitting, control-point smoothing, size fitting,
or implicit scaling occurs. All lengths are meters, angles radians, curvature
inverse meters, and curvature-change rate inverse square meters. Coordinates
are X right/Y up with positive curvature left. Primitive placement is a rigid
translation/rotation. Mirroring changes Y, heading, curvature and curvature rate
signs; it does not reverse traversal or change requested positive radii.

## Physical arc length and numerical integration

`CurvatureSegment(length_m, k_start=0, k_end=0, ramp="smoothstep")` defines
`dθ/ds = k(s)`, `dx/ds = cos θ`, `dy/ds = sin θ` on `[0,length_m]`.
`State(s,x,y,heading,curvature,curvature_rate)` exposes all differential fields.
Heading is **unwrapped**, including more than a full revolution. `Frame` supplies
world position and initial heading; angular continuity uses wrapped differences.
A mathematically equivalent initial heading offset by `2π` is normalized at a
join to avoid a false revolution in subsequent measurements.

With `u=s/L`, `Δk=k_end-k_start`:

| Ramp | Curvature | Integrated heading relative to entry | Maximum `abs(dk/ds)` |
| --- | --- | --- | --- |
| `linear` (clothoid) | `k_start + Δk*u` | `k_start*s + Δk*L*u²/2` | `abs(Δk)/L` |
| `smoothstep` (cubic curvature) | `k_start + Δk*(3u²-2u³)` | `k_start*s + Δk*L*(u³-u⁴/2)` | `1.5*abs(Δk)/L` |

Both give G2 curvature continuity when endpoint curvatures match. Smoothstep also
has zero curvature derivative at both endpoints, so it connects to constant
curvature without a steering-rate jump in the static kinematic approximation.
A clothoid has constant curvature rate and a rate jump when joined to a constant
curvature segment. Neither provides a complete actuator or vehicle dynamics
model. Smoothstep is the default for bounded and gradual steering demand.

Constant-curvature segments use analytic line/circle formulas. Other positions
use composite 12-point Gauss–Legendre integration, with panels at most 0.25 m and
0.1 rad under the segment's maximum curvature. These integration settings are
fixed parts of generator version 1. Independent adaptive SciPy integration tests
agree within 2e-12 m on the tested 17 m ramps. This is test evidence, not a global
error bound for arbitrary inputs; panel/sample budgets reject extreme work.

Sampling uses `ceil(L/spacing)` equal subdivisions per low-level segment,
including both endpoints and the midpoint of a varying-curvature segment.
The midpoint ensures peak smoothstep curvature rate is represented. Floating
point near-duplicate midpoints are avoided by subdivision parity. Spacing is an
**upper bound**, not a promise of a constant gap across joins. Each primitive
breakpoint is retained. Evaluation of the underlying curve does not depend on
output spacing. `GeometrySequence.sample` checks increasing arc length, nonzero
chords, chord length within `[0.99*ds, ds+1e-7]`, and at most 0.2 rad of heading
change per sample; coarse geometry rejects rather than silently interpolating.

There are two length coordinates:

- `State.s` and the demonstration differential profiles use physical curve arc
  length, including transitions.
- Simulator CSV profile positions and schema-1.0.0 maneuver intervals use cumulative
  **chord** distance on the final exported centerline, including its closing edge.
  This agrees with the consumer's polyline progress coordinate. Both lengths are
  exported as measurements; refinement makes their difference converge to zero.

## Six constructors

All functions are in `map_editor.geometry`. Constructor values are requests,
not certificates; call `validate_maneuver` on samples to accept a label. Closed
bundle generation and demonstration generation always perform that validation.

| Constructor | Parameters and achieved geometry |
| --- | --- |
| `straight(length_m)` | Positive physical length; zero curvature. |
| `hairpin(radius_m, turn_angle_rad=π, direction="left", entry_transition_m=1, exit_transition_m=1)` | Smooth entry from zero curvature, constant-radius body, smooth exit to zero. Entry/exit contribute `length/(2*radius)` heading each. The body length is `radius*angle - (entry+exit)/2`; nonpositive body budgets reject. Accepted heading reversal defaults to 150–210 degrees, configurable in measurement tolerances. |
| `sweeper(radius_m, turn_angle_rad, direction="left", entry_transition_m=0, exit_transition_m=0, end_radius_m=None)` | Constant or smoothstep-varying body curvature, with optional smooth transitions to/from zero. Body length solves the requested angle after transition contributions. Positive start/end radii; curvature retains its sign. Zero entry/exit lengths deliberately omit transitions, so a G2 join to a straight must be supplied separately. |
| `chicane(radius_m, lateral_displacement_m, separation_m=0, transition_length_m=1, direction="left_right")` | Two equal-radius opposing bends, each with smooth entry/exit, separated by the specified straight length. A deterministic 60-step bisection solves the shared lobe angle in `(transition_length/radius, π/2]` for the **magnitude** of the requested lateral displacement. Exit heading equals entry heading. Radius/separation/transitions never change. Infeasible displacements reject. `right_left` mirrors the displacement sign. |
| `s_curve(radii_m=(5,7), turn_angle_rad=π/3, transition_length_m=1, direction="left_right")` | Sustained opposing bends, each with its own radius and equal requested angle, joined at zero curvature. Each bend has entry/exit transitions of the given length. No separation straight; exit heading equals entry heading. |
| `transition(length_m, k_start_inv_m, k_end_inv_m, ramp="smoothstep")` | Monotone curvature ramp, including crossing through zero. Direction derives from endpoint signs; it may be `none`, left/right, or either ordered opposing pair. |

A requested zero-length **transition segment** is invalid. A zero entry/exit
transition length on a turn means “omit the transition,” not “make a degenerate
segment.” Hairpin/sweeper radii must be positive; direction chooses the sign.
`maneuver.mirrored()` is available for every family.

Chicane and S-curve are intent-based definitions with measured acceptance
criteria, not mutually exclusive shape clusters. A suitable curve might meet
both vocabularies under different requests. Labels come from the explicit
construction plus independent acceptance of its features; there is no heuristic
that guesses a label from a spline control polygon.

Deterministic range sampling is separate from layout and dataset creation:

```python
from map_editor.geometry import hairpin, sample_parameters

params = sample_parameters({"radius_m": (3.0, 6.0),
                            "turn_angle_rad": (2.8, 3.4)}, seed=42)
left = hairpin(**params)
right = left.mirrored()
```

Ranges are finite ordered numeric pairs, sampled in sorted-key order by a local
seeded `random.Random`. The actual parameter values are recorded in recipes;
replay does not need to recreate earlier RNG calls. `ParametricTrackSpec.random_seed`
is provenance and does not independently perturb explicitly supplied geometry.

## Sequence and tolerance contracts

`GeometrySequence([...], frame=Frame(), require_g2=True, tolerances=...)` places
each maneuver exactly at the previous endpoint and tangent. `append(maneuver,
frame=...)` permits explicit placement and rejects joins beyond tolerances.
Low-level segments within a maneuver must match curvature. Optional G1 assembly
can omit curvature continuity (`require_g2=False`), but the hard validity checker
rejects curvature jumps because their curvature-change rate is unbounded.

`ContinuityTolerances` defaults:

| Quantity | Default |
| --- | ---: |
| Position | 1e-7 m |
| Wrapped heading | 1e-7 rad |
| Curvature when G2 required | 1e-7 inverse m |

`sample(spacing, closed=True)` checks the terminal-to-initial join, including
heading modulo `2π` and curvature. It does not solve a closure error. Internal
sample storage includes the terminal vertex so interval measurements include
all edges; closed CSV export removes the duplicate. Self-intersection tests
include the closing edge and reject adjacent backtracking as well as nonadjacent
contacts. No automatic closure optimizer or configurable composite-circuit
layout system is included in Phase 1.

`MeasurementTolerances` is configurable and stored in closed metadata:

| Test | Default |
| --- | ---: |
| Chord/physical length agreement | max(1e-4 m, 0.002 × physical length) |
| Requested turn/net exit heading/lobe angle | 0.005 rad |
| Curvature/radius-feature agreement | 0.002 inverse m |
| Straight deviation from endpoint chord | 0.001 m |
| Turn-sign threshold | 1e-5 inverse m |
| Hairpin reversal range | 150–210 degrees |
| Minimum opposing lobe heading change | 0.05 rad |
| Chicane lateral displacement | 0.002 m |

Measurements include chord and physical lengths, signed and absolute heading
change, signed curvature extrema, minimum radius, finite-difference and sampled
peak curvature-change rate, endpoint heading/curvature, straightness deviation,
turn-sign sequence/reversal count, lobe angles, lateral displacement and corridor
width. Tangents and curvature are sampled differential fields of the final curve;
heading totals use their unwrapped values. Independent three-position signed
circumcircle curvature is also reconstructed, with its radius and maximum error
reported. Interior curvature disagreement above `0.002 + spacing*peak_rate`
rejects. This accounts for finite-difference error near transitions; it is not an
analytic certification. Chord directions are also checked against the mean
endpoint tangent, with a bound of `angle_tolerance + spacing²*peak_rate`;
the maximum wrapped tangent discrepancy is reported. Position curvature also drives the ordinary closed
track-profile curvature and minimum radius metrics.

Acceptance checks radius and angle against requests, hairpin reversal, straight
length/deviation, ordered opposing lobes and their radii, S-curve lobe angles,
chicane displacement, and transition endpoint curvature. Wrong measured labels
raise `GeometryError`; generated artifacts never contain an accepted label that
failed these checks. Unknown type/direction combinations reject.

## Geometric validity and vehicle feasibility

`GeometryLimits` defaults are explicit generation policy, not universal F110
limits: minimum radius 0.5 m, minimum usable width 0.7 m, peak curvature-change
rate 2 inverse square m, footprint margin 0.02 m, and nonlocal boundary gap 0.1 m.
Hard checks include:

1. Sampled centerline and offset-wall intersections. Offsets reject
   `abs(curvature)*half_width >= 1`, where the offset becomes singular.
2. Global segment-to-segment distance between **all opposing boundary segments**,
   including noncorresponding and distant track portions. Usable width subtracts
   two footprint margins from this distance. It is not nearest-vertex width.
3. A lower-bound certificate for all boundary pairs (including same-wall pairs)
   farther apart than `3*track_width` in centerline arc length. Periodic distance
   is used on closed tracks. Adjacent neighborhoods are excluded because nearby
   same-wall edges naturally have arbitrarily small distances. This certificate
   reports the configured bound and exclusion; it does not pretend to measure
   the exact global same-wall minimum.
4. Sampled curvature/rate constraints and rejection of curvature jumps.
5. If a `VehicleProfile` is supplied, the entire expanded rectangular body is
   checked against vector walls at each sampled pose, including walls contained
   in the body. Open demonstrations explicitly report unassessed endpoint poses
   where the body extends beyond the defined corridor.
6. For closed bundles, corridor rasterization, half-cell centerline checks, a
   conservative usable-width lower bound `vector_usable_width - 4*sqrt(2)*resolution`,
   and (with vehicle supplied) SAT overlap tests between the full rectangular
   body area and every candidate occupied cell. This catches interior obstacles
   that a corners-only check misses. New bundles use one-pixel walls, binary
   corridor occupancy, no inversion, and the Phase 0 coordinate convention.

A conservative width bound may reject a coarse raster that would pass a more
precise clearance solver. Use finer cells or explicitly change the generation
policy; the backend does not silently widen, resize, or relabel a maneuver.

The uniform-grid broad phase conservatively enumerates segment AABB cells.
Narrow-phase predicates reuse the existing floating-point intersection logic;
global distance uses segment projections/intersections. Grid and exhaustive
results are compared on randomized and adversarial tests. Footprint AABB
filtering removes irrelevant walls before exact intersection checks. The legacy
quadratic checks are not changed.

`VehicleProfile.from_yaml(path)` requires actual resolved dimensions, axle
distances and steering limits. It reads classic `s_min/s_max/sv_min/sv_max` or
`wheel_actuators` bounds, records the filename, SHA-256 and calibration status,
and has no silent universal vehicle fallback. Both the reference default and
combined-slip configs are tested. Demonstrations use the inspected
`marl_race/configs/vehicle/combined_slip.yaml`: 0.50 × 0.27 m centered body,
`lf=0.15875`, `lr=0.17145`, steering ±0.523599 rad, and rate ±3.2 rad/s. This
matches the reference's centered `VehicleGeometry.from_params` convention.
Unresolved development/Hydra compositions must be resolved before import.

`feasibility_advisory` is separate from hard geometric acceptance. At an explicit
speed it reports static kinematic steering demand (including the rear-axle
reference offset), its rate, and required lateral acceleration `v²*max(abs(k))`.
Only a caller-supplied lateral-acceleration assumption produces a curvature
speed bound `sqrt(a_lat/max(abs(k)))`. No friction coefficient is guessed.
These are steady/quasi-static estimates; transient sideslip, tire forces,
actuator lag, braking and controller tracking are not modeled. Calibration
remains `uncalibrated` for the supplied combined-slip configuration. Reports
always retain `physical_drivability: unassessed`.

Neither sampled vector nor raster footprint checks are a continuous swept-body
certificate between poses. Refinement and convergence tests reduce discretization
error; eventual continuous clearance and controller evaluation remain separate
work. Supplying no vehicle leaves footprint checks explicitly unassessed.

## Bundle and metadata integration

`ParametricTrackSpec` and `generate_parametric_bundle` are in
`map_editor.services.parametric_track`. The backend supplies an already measured
`TrackGeometry` to `procedural_track.export_track_geometry`; the old sampler is
never called. A regression makes the legacy sampler raise to prove this path.
The existing `TrackSpec` type adapts common export settings using the actual
sampled points; those points are never refitted or rescaled.

For example, run Python with `PYTHONPATH=src` from the repository root:

```python
from pathlib import Path
from map_editor.geometry import straight, hairpin
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.parametric_track import ParametricTrackSpec, generate_parametric_bundle

vehicle = VehicleProfile.from_yaml(Path("../marl_race/configs/vehicle/combined_slip.yaml"))
spec = ParametricTrackSpec(
    "stadium", (straight(12), hairpin(4), straight(12), hairpin(4)),
    spacing_m=0.1, width_m=1.5, vehicle=vehicle,
)
generate_parametric_bundle(spec, Path("generated_maps/stadium"))
```

Metadata remains schema **1.0.0**, including periodic half-open intervals and
controlled vocabulary. Annotations are derived from the final sample spans and
chord arc positions. A final segment ending at the seam uses endpoint zero and
`wraps_seam: true`; a single full-lap primitive uses equal zero endpoints with
lap length. Difficulty is `unrated`, with measured indicators only. Width fields
in ordinary profile rows describe local normal offsets; the provenance
validation report separately records global gap, margins and raster checks.

New generation recipes have schema integer 1 and the distinct parametric
**generator** identifier. They retain low-level curvature segments, explicit
maneuver requests/directions, rigid start pose, sampling/export settings,
tolerances, limits, seed/split IDs and a complete vehicle snapshot. Unknown
versions reject. The new CLI is `scripts/generate_parametric.py`; the old CLI,
GUI recipe handling, old generator ID and old sampler retain their behavior.
Closed metadata artifacts and centerline/wall CSV headers are unchanged.
`export_walls_csv(..., closed=False)` is added for open demonstration polylines;
its default still closes walls exactly as before.

Schema 1.0.0 describes closed laps. Open primitives are therefore exported as
labeled geometry demonstrations, measurement JSON, differential profiles and
ordinary CSVs, **not** as simulator maps or falsely closed metadata. The closed
stadium is a proper schema-1.0.0 map bundle.

The checked-in Phase 0 bundle replays byte for byte in its original standalone
CLI context. Qt embeds context-dependent physical-DPI information in PNGs after
GUI initialization; the golden regression reproduces the original CLI context
instead of changing legacy image bytes. Geometry/CSV replay is deterministic;
byte identity across different Qt versions/GUI application contexts is not a
new portability guarantee.
