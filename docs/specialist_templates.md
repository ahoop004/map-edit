# Specialist template and variation contract

Phase 2 adds `map_editor.specialist_templates.v1`, with template revision
`halfturn.v1`. This is a separate recipe contract. Neither the legacy spline
version nor `map_editor.parametric_curvature.v1` changes. The underlying Phase 1
primitive constructors, numerical integration, measured acceptance and geometric
validation are reused unchanged.

## Experimental intent and geometric composition

`SpecialistSpec` requires a target family and a resolved `VehicleProfile`.
`experimental_mode` is explicitly `specialist`, independent of supporting geometry.
A circuit containing a chicane region, straights and closure hairpins remains a
chicane specialist when it meets its requested chicane exposure.

Metadata still uses schema **1.0.0**:

| Location | Meaning |
| --- | --- |
| `generation_mode` | Explicit `specialist`. |
| `geometry_family` | `specialist_<target_family>`. |
| `requested.target_family` | One of `straight`, `hairpin`, `sweeper`, `chicane`, `s_curve`. |
| `requested.minimum_target_exposure_fraction` | Requested minimum, never reduced after rejection. |
| `requested.specialist_parameters` | Complete resolved physical and sampling parameter configuration. |
| `maneuvers[].requested.template_role` | `target`, `approach`, `exit`, `heading_connector`, `closure_connector`, or `repetition_connector`. |
| `provenance.specialist_statistics` | Measured family/role exposure, counts, distributions, directional balance and clearance. |
| `provenance.experimental_intent` | Experimental role and target, distinct from composition. |
| `provenance.identity` | Versioned template, lineage, variant, seed, exact configuration hash and vehicle provenance. |
| `provenance.geometric_difficulty` | Separate requested and measured difficulty dimensions; no scalar difficulty score. |
| `provenance.validation_report` | Relative path to the additional per-track validation report. The fixed nine-artifact schema is preserved. |

A target family includes every validated interval of that family. For example,
straight approaches contribute to a straight specialist's family exposure.
The report **also** distinguishes primary target-role exposure from supporting
roles. A sweeper-shaped heading connector is counted as sweeper family geometry,
but is explicitly recorded as a connector rather than a primary target feature.
Thus composition and construction purpose can be analyzed independently.

Exposure means **maneuver-window coverage**, not necessarily nonzero curvature.
Chicane windows include their internal separation straight and curvature ramps.
Ramps remain inside their owning maneuver's interval and are never counted again
as independent transition exposure. Embedded transition length and the fraction
of lap with active target curvature are reported separately. These definitions
avoid double counting and make long separation straights visible.

## Exact closure without fitting

All templates construct a half-lap block whose terminal tangent turns exactly
180 degrees and whose endpoint curvature is zero. Repeating the identical block
makes the second copy's displacement the negative of the first. If the block
has rigid transform `(D, π)`, the full transform is `(D + Rπ D, 2π) = identity`.
This establishes closure without changing a requested radius, angle, displacement
or length. Global validation still rejects self-intersections or insufficient
clearance: exact closure alone does not establish a valid corridor.

| Family | Half-lap construction |
| --- | --- |
| Straight | Approach + requested long straight + exit + smooth 180-degree closure hairpin. |
| Hairpin | Approach + requested hairpin + any required heading correction + exit. |
| Sweeper | Approach + requested sustained sweeper + any required heading correction + exit. |
| Chicane | Approach + repeated same-oriented chicanes with optional intervening straights + exit + closure hairpin. |
| S-curve | Approach + repeated same-oriented S-curves with optional intervening straights + exit + closure hairpin. |

For a requested single bend of angle `θ`, a supporting sweeper of signed angle
`π-θ` supplies the heading correction when needed. Its radius and entry/exit
transition lengths are explicit connector parameters. Very small corrections may
be infeasible with a given transition length; they reject with the Phase 1 angle
budget error. The generator does not shorten a transition automatically. Requested
hairpins also retain Phase 1's measured 150–210 degree reversal requirement.

`clockwise=True` reverses physical traversal of the same constructed course.
It reverses maneuver/segment order, negates reversed curvature, swaps entry/exit
transitions and ordered S-curve radii, and starts with the opposite tangent.
This is not a reflected layout. Tests compare CW samples against the reversed
CCW coordinate sequence. Topological winding must be -2π for CW and +2π for CCW.

## Parameter inputs

Lengths are meters, angles radians, and all parameters must be finite. Unknown
keys reject. Optional approach/exit, padding, internal spacing and repetition-gap
lengths may be zero; required dimensions and transition lengths must be positive.

| Parameters | Applicability |
| --- | --- |
| `approach_length_m`, `exit_length_m` | Every family. Both are explicit, even where adjacent straight annotations form one physical run. |
| `connector_radius_m`, `connector_transition_m` | Supporting closure or heading-correction geometry. A connector is omitted only when no heading correction is needed. |
| `maneuver_length_m` | Requested main straight length. For other families it is an optional **consistency constraint**: the radius/angle/transition-derived feature length must match or the request rejects. Overdetermined values are not fitted. |
| `turn_radius_m` | Hairpin, sweeper and chicane target radius. |
| `turn_angle_rad` | Hairpin/sweeper requested bend angle; S-curve per-lobe angle/severity. Chicane angle is solved by the existing displacement-constrained primitive. |
| `transition_length_m` | Target entry/exit ramp length, including each compound turn lobe. |
| `chicane_spacing_m`, `lateral_displacement_m` | Chicane separation straight and positive displacement magnitude. |
| `first_radius_m`, `second_radius_m` | S-curve ordered CCW-construction radii; traversal reversal preserves physical geometry and swaps traversal order. |
| `repetitions` | Chicane/S-curve repetitions **per half-lap**; integer 1–12. Full-lap count is twice this. |
| `inter_maneuver_straight_m` | Straight between repeated chicane/S-curve windows, owned by the supporting straight family. |
| `track_width_m` | Requested normal-offset corridor width. Global usable clearance is measured separately. |
| `spacing_m` | Upper bound on physical sample spacing, with Phase 1 breakpoints/midpoints retained. |
| `resolution_m_per_pixel`, `padding_m` | Occupancy raster resolution and padding. Binary corridor occupancy, one-pixel walls and `negate: 0` are fixed compatibility choices. |

`SpecialistSpec` also has `seed`, `variant_number`, `minimum_target_exposure`,
`clockwise`, `dataset_id`, optional `parent_lineage`, `template_revision`, and
`GeometryLimits`. Metadata dataset split is always `unspecified`; no final
train/validation/test assignment is implemented.

### Defaults and vehicle provenance

Defaults are derived from an actual supplied vehicle configuration, not a hidden
universal F110 model. The static reference-point kinematic radius is
`sqrt(((lf+lr)/tan(min_abs_steering_bound))² + lr²)`, about **0.597069 m** for the
reference combined-slip profile. Target radius defaults are at least 5× this
value for hairpins, 10× for sweepers, 6× for chicanes/first S lobes and 7× for
second S lobes, with additional conservative absolute floors. Connector radius
is at least 4× the reference radius. Corridor width is at least the body width
plus 0.8 m, with a 1.5 m floor. Approach/exit lengths are at least twice body
length, with a 1 m floor. These are conservative **geometric** defaults; static
steering calculations do not establish physical driving success.

For the inspected 0.50 × 0.27 m combined-slip vehicle, defaults are:

| Family | Primary parameters | Minimum family exposure |
| --- | --- | ---: |
| Straight | 30 m feature, 1 m approach/exit, 3 m closure radius | 0.70 |
| Hairpin | 3 m radius, π angle, 1 m ramps | 0.70 |
| Sweeper | 7 m radius, π angle, 1 m ramps | 0.80 |
| Chicane | 4 m radius, 3 m displacement, 2 m spacing, 1 m ramps, 3 repetitions | 0.60 |
| S-curve | 4/5 m radii, π/3 per lobe, 1 m ramps, 3 repetitions | 0.65 |

Numerical sampling defaults to 0.15 m and raster resolution to 0.04 m/pixel.
The Phase 1 hard limits remain explicit: 0.5 m minimum radius, 0.7 m minimum
usable width, 2 inverse-square-meters peak curvature rate, 0.02 m footprint margin
and 0.1 m nonlocal boundary gap. All limits and the full vehicle snapshot,
source filename and SHA-256 are recorded. The imported tire profile is
`uncalibrated`; successful geometry does not change that status.

`default_ranges(family, vehicle)` provides a small conservative starting range
(0.9–1.15 times selected default radii, lengths, displacement or severity).
They are proposal ranges, **not** an unconditional acceptance guarantee. Coupled
constraints and dominance can reject even an otherwise well-formed sampled
request. User-defined ranges can override any applicable numeric parameter;
repetition bounds must be integers and use uniform integer sampling. Other
parameters use a local seeded uniform sampler in sorted key order.

## Measurement, thresholds and difficulty

The new layer quantizes positions/walls to the actual six-decimal CSV precision
before computing lap and interval distances. It measures family exposure from
these final text-CSV coordinates in double precision. The simulator's float32
loading can introduce a further small length difference. Curvature/feature
acceptance is repeated on the quantized centerline; exported walls and raster
footprints are checked again. The existing primitive geometry itself is not
refitted. Source G2 residuals and the CSV quantization precision are both recorded.

Intervals partition the entire lap, using schema-1.0.0 periodic half-open
semantics. A terminal interval ends at zero with `wraps_seam: true`. The exposure
validator checks coverage, no overlaps, family fractions, counts and intent.
Minimum specialist exposure is configurable in **[0.5, 1]**. The default
threshold differs by family and is supported by the geometric sweep in
[`phase2_thresholds.json`](phase2_thresholds.json), not a universal percentage.
An unmet minimum rejects the candidate; retries never lower it.

Statistics include:

- Target and supporting-family fractions; primary-target and supporting-role fractions.
- Family and direction counts, annotated straight lengths and merged physical
  straight runs, including across the seam.
- Actual straight-run length immediately before each turn; short adjacent
  annotations are merged instead of understating an approach.
- Turn-lobe radius distribution, including supporting turns, and directional
  balance weighted by left/right absolute heading change.
- Total absolute heading change, peak curvature and curvature-change rate,
  final exported global gap, usable width and conservative raster clearance.
- Requested versus measured geometric features and dimensions affecting
  difficulty, such as target frequency, approach distance, radius, ramp length
  and available clearance.

No arbitrary difficulty score or categorical driving rating is calculated.
Ratings remain `unrated`; dynamic drivability remains `unassessed`. A large
approach, tight supporting connector or short ramp can increase demands even
when the target family covers most of the lap. Supporting geometry is never
hidden from radius, clearance or curvature statistics.

## Identities, bounded proposals and publication

`configuration_id` is SHA-256 of canonical sorted JSON containing the exact
versioned specification, including seed, variant, vehicle snapshot and limits.
`track_id` is a readable family/variant prefix plus its first 20 hexadecimal
characters; the full digest is stored for audit. Identical inputs yield the same
ID. Seeds and variants change IDs but are not evidence of a new layout.

The default parent lineage is a full hash of family and template revision, shared
by siblings regardless of seed, traversal or dimensions. Users may supply an
explicit parent lineage. A parameter shape ID excludes seed/traversal/sampling
and a 1e-5 m rounded cyclic/reversal-invariant coordinate fingerprint detects
additional duplicates. These are practical duplicate checks, not a proof of
arbitrary geometric equivalence. A pilot also requires at least 5% relative
change in one measured feature dimension between variants of a family; changing
only the seed, resolution or traversal is insufficient.

Lineage groups are intentionally conservative. They support future leakage-aware
split design; they do not implement or certify a final split policy.

A pilot recipe records root seed, exact requests/ranges and a per-request budget.
Candidate seeds come from a local seeded RNG. Each failed candidate retains its
seed, attempt, full sampled recipe when available, ranges and reason. Failed
requests produce an explicit partial manifest; thresholds/parameters are not
relaxed. The default pilot uses eight attempts per request; the contract permits
1–100. I/O/overwrite errors propagate instead of being disguised as geometry
rejections.

A publication stages its files, runs actual consumer checks when requested,
regenerates all nine bundle artifacts from the saved recipe, and compares their
bytes before reserving a new destination directory. Existing directories and
runtime-evidence files are never overwritten. Bundle directories contain nine
standard artifacts plus a validation report with SHA-256 hashes, source checks,
replay evidence, and a named `grid_1` pose at least about one meter before the
finish. Independent geometric publication can explicitly record consumer checks
as `not_run`; **pilot acceptance always requires the actual consumer smoke**.

Timing evidence is stored separately from deterministic bundles and manifest.
No timestamps, absolute output paths or timing noise enter stable identities.
As in previous phases, byte comparisons use the same Qt/software context; old
CLI reference bytes are retained and tested.

## Use and replay

From the repository root, install `requirements-dev.txt`. The application paths
are available to Python with `PYTHONPATH=src`:

```python
from pathlib import Path
from map_editor.geometry.validation import VehicleProfile
from map_editor.services.specialist_templates import SpecialistSpec
from map_editor.services.specialist_tracks import generate_specialist_bundle

vehicle = VehicleProfile.from_yaml(Path("../marl_race/configs/vehicle/combined_slip.yaml"))
spec = SpecialistSpec(
    target_family="chicane", vehicle=vehicle, seed=123, variant_number=1,
    parameters={"repetitions": 3, "lateral_displacement_m": 3.5},
    minimum_target_exposure=0.60,
)
generate_specialist_bundle(spec, Path("generated_maps/my_chicane"),
                           reference=Path("../marl_race"))
```

Generate a fresh ten-track pilot or replay the supplied manifest requests:

```bash
python3 scripts/generate_specialists.py pilot --output generated_maps/phase2_reproduction \
  --recipe examples/phase2_pilot/pilot_recipe.json \
  --marl-race-root ../marl_race --profile generated_maps/phase2_reproduction_runtime.json
python3 scripts/plot_specialist_pilot.py generated_maps/phase2_reproduction
```

A supplied pilot recipe owns its recorded seed and budget; `--seed` and
`--max-attempts` apply when constructing the default requests instead. To replay
one native specialist recipe:

```bash
python3 scripts/generate_specialists.py replay \
  examples/phase2_pilot/<track-id>/<track-id>_generation.yaml \
  --output generated_maps/specialist_replay --marl-race-root ../marl_race
```

The old CLIs still handle their original recipes. Wrong generator/version
identifiers reject rather than being reinterpreted as another backend. No
arbitrary composite layout optimizer or training workflow is included.
