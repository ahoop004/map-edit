# Composite circuit specification and generation contract

The new recipe identifier is **`map_editor.composite_circuits.v1`**, template
**`block_and_bounded_return.v1`**. Phase 0–2 generator implementations, versions,
recipe interpretation and ordinary CSV formats remain unchanged. This layer
uses existing Phase 1 primitives and `GeometrySequence`; it never fits or scales
requested geometry with the old B-spline generator.

The implementation lives in `services/composite_spec.py`, `composite_assembly.py`,
`composite_statistics.py`, `composite_tracks.py` and `composite_pilot.py`.

## Ordered requests and physical parameters

`ManeuverRequest(name, family, parameters, ranges={}, gap_after_m=None)` uses the
existing constructor contract for `straight`, `hairpin`, `sweeper`, `chicane`,
`s_curve`, or an explicitly requested supporting `transition`. Parameters are
normalized to their constructor defaults and saved explicitly. Unknown names,
invalid constructor arguments and invalid numerical ranges reject.

Names are unique within an inventory. They identify requests, not geometry.
`parameters` are exactly the Phase 1 keyword arguments: lengths in meters,
angles in radians, radii in meters, and curvature endpoints in inverse meters.
Directions stay explicit in those parameter mappings. Required families refer
to the five **primary** families; requested transitions are supporting windows.
There must be at least two primary families in a composite request.

Optional `ranges` map numeric parameter names to finite `[minimum,maximum]`
pairs. Indexed S-curve radii use `radii_m.0` and `radii_m.1`. Candidate sampling
uses a local seeded RNG in sorted request-name/parameter-key order, so changing
inventory ordering does not implicitly change parameter draws. `allowed_orders`
may list inventory-index permutations for seeded ordering variation. Direct
`prepare_composite` and native recipe replay use the saved resolved parameters;
they never resample them automatically.

`CompositeSpec` controls:

| Field | Contract / default |
| --- | --- |
| `inventory` | Ordered construction requests, including any requested supporting transitions. |
| `generation_mode` | Explicit `composite`; no intent inference from family count. |
| `layout` | `symmetric` or bounded `asymmetric`. No fallback between strategies. |
| `symmetry_order` | 2 or 4 rotated copies for symmetric construction. |
| `motif_repetitions` | 1–6 inventory repeats inside a construction block/core. |
| `approach_length_m` | Supporting approach before the core; default 3 m. Zero omits it. |
| `gap_length_m` | Supporting distance after each request, default 1 m. Per-request `gap_after_m` overrides it. Zero omits the gap. |
| `required_families` | Defaults to the inventory's primary families; all must survive final measurement. |
| `exposure_bounds` | Optional `{family: [min,max]}` for any primary family or `transition`, in [0,1]. Enforced on the final CSV lap, not predicted parameters. |
| `transition_count_range` | Inclusive range of cyclic **primary-family changes**, default 2–100. Same-family windows and connector boundaries have separate measured counts. |
| `minimum_useful_length_m` | Minimum final primary maneuver window, default 2 m. |
| `lap_length_range_m` | Final exported lap range, default 20–500 m. No lap-length fitting or scaling. |
| `track_width_m` | Normal-offset corridor width, default 1.5 m. |
| `spacing_m` | Maximum curve-sample spacing, default 0.15 m. |
| `resolution_m_per_pixel`, `padding_m` | Default 0.04 m/pixel and 1 m. Binary corridor occupancy, one-pixel walls, no inversion. |
| `clockwise`, `mirrored` | Desired winding and geometric reflection. Actual travel order and transformed directions are recorded. |
| `seam_offset_m` | Requested physical-arc seam offset, modulo lap length. Snap to the nearest retained vertex using periodic distance. |
| `vehicle`, `limits` | Actual resolved vehicle snapshot and Phase 1 geometric policies. Required vehicle provenance is embedded. |
| `seed`, `attempt`, `variant`, `dataset_id` | Candidate identity and experiment provenance; filenames use a safe configuration digest. |
| `parent_lineage`, `matched_group` | Optional explicit lineage and matched-inventory cohort. |
| `speed_assumption_m_s`, `environment_step_s` | Optional, explicit analysis assumptions; no implicit traversal speed. |
| `selection_intervals_steps` | Default [5,10,20], with `default_selection_steps=10`. Analysis only. |
| `physical_change_curvature_inv_m` | Envelope-change threshold used by the documented demand-change indicator; default 0.02 inverse m. |

Inventory order is the canonical construction order. Reflection/traversal
transformations can reverse travel, so metadata separately records the actual
cyclic travel sequence. Clockwise mode reverses physical travel around the
constructed course rather than inventing a different layout through relabeling.
Reflection flips geometric handedness; traversal is reversed when necessary to
retain the requested final winding. Comparisons intended to isolate ordering
should hold these flags fixed, as the pilot matched pair does.

## Only designated connectors can adjust

`ConnectorConstraints` exposes radius and straight-length bounds, fixed internal
ramp length, fixed automatic join-ramp length, minimum/maximum connector-window
length, maximum turn angle, maximum supporting exposure, and a bounded solver
budget. Defaults are:

- Radius proposals: 3.5, 5.25 and 7 m (lower, midpoint and upper bounds).
- Return straight bounds: 0–100 m; numerical zeros are omitted.
- Smooth bend entry/exit and automatic join ramps: 1 m.
- Turn magnitude at most π; connector-window length 0.5–100 m.
- Supporting geometry at most 65% of the lap.
- At most 48 asymmetric search trials (configurable 1–256).

A primitive whose initial curvature differs from the preceding endpoint receives
an explicit supporting ramp of the configured length. Likewise, core entry/exit
curvature is connected to zero where needed. Existing maneuver radii, angles,
internal ramps, lengths and displacement constraints do not change. Ramps and
all nonzero connectors are separate measured windows; no zero-length annotation
is fabricated. Connector bounds may make a request infeasible, and that request
is rejected rather than silently shortened, enlarged or distorted.

Supporting geometry is annotated with controlled type `transition` and its
construction purpose. Its `source_type` and full `source_parameters` retain the
underlying straight, sweep or curvature ramp. Both the supporting window and
its source primitive undergo measured acceptance. This keeps a primary-family
inventory honest: an inserted closure bend is not presented as an additional
requested hairpin or sweeper. Required-family checks apply to primary requests.

### Guaranteed repeated-block closure

After the ordered core, a signed supporting bend supplies any missing heading
`2π/symmetry_order - core_heading`. The resulting block is copied and rotated by
its own terminal tangent. The sum of its rotated displacements is zero, closing
the track without a position fit. Curvature starts/ends at zero, and the existing
G2 checks validate every join, including the seam. Supporting bend radii may be
tried within their explicitly designated bounds. If the angular budget cannot
contain their fixed ramps, the candidate rejects.

Exact algebraic closure is not sufficient for acceptance: every candidate still
passes global centerline/wall intersection, separation, useful-window, exposure,
full sampled vehicle footprint and raster checks.

### Bounded asymmetric return solver

The asymmetric strategy appends up to three fixed smooth bends and two adjustable
straight legs to the requested core. It enumerates three allowed radius proposals,
eight leg headings and either ±π/2 middle bend, stopping at the stated budget.
For core heading `θ`, selected first-leg heading `ψ`, and middle bend `b`:

```text
a = wrapped(ψ - θ)
b = +π/2 or -π/2
c = 2π - θ - a - b
```

Zero end bends are omitted. All nonzero angles and lengths must satisfy the
connector bounds. The fixed bends are evaluated with the existing geometry
backend. Let their endpoint residual (with the core and without straight legs)
be `q`, and the two leg unit vectors be `u1` and `u2`. They are orthogonal, so
solve the nonsingular 2×2 system:

```text
[u1 u2] [leg1, leg2]^T = -q
```

Only those designated straight lengths and the enumerated connector bend
parameters adjust. Negative/out-of-range legs reject. Position, heading and
curvature closure are checked again by `GeometrySequence`, and every candidate
undergoes the complete geometric/feature/raster acceptance pipeline. All trials,
including rejected bounds or geometry, are recorded with reasons. No primary
maneuver is mutated to repair a return path.

This is a bounded search in one explicit return topology, not a general layout
optimizer or a proof that no other feasible closure exists. A failed search is
reported as failure within the chosen strategy and bounds. The asymmetric
acceptance check also rejects layouts that are accidentally point-symmetric:
its measured half-lap rotation residual must exceed 1 mm. This does not claim
absence of every possible reflection symmetry.

## Final measurement, periodicity and geometric acceptance

The Phase 1 validation pipeline is retained, including source maneuver identity,
G2 continuity, minimum radius and curvature-change rate, offset singularities,
centerline/boundary intersections, global opposing-wall distance, nonlocal gap
policy, and sampled rectangular vehicle footprint. After text-CSV coordinate
quantization, centerline/walls and global clearance are checked again, along with
full-area raster-cell overlap against every sampled vehicle pose. CSV positions
retain six decimal places; profiles retain their existing nine-decimal arc
format. No ordinary centerline or wall columns change.

Maneuver intervals are computed from those final centerline coordinates.
Schema **1.0.0** remains unchanged: periodic, half-open `[start,end)` windows,
with explicit wrap flags and length. Ramps inside a primary primitive belong to
that primitive and are not double-counted. Supporting connector windows have
their own disjoint intervals. Windows partition the full lap.

Moving the map seam never splits a maneuver into multiple counted instances.
An interval may cross through arc zero, and its entry/exit positions retain that
fact. Source differential measurements are preserved; headings compare modulo
`2π` after seam rebasing. At a rotated shared endpoint, evaluation lookup uses
the exported profile's 1e-9 m arc precision to resolve one-ULP accumulation ties.
This avoids overlaps or gaps caused solely by re-summing a circular polyline.
A seam close to the lap end can correctly snap to vertex zero using circular
nearest-vertex distance.

## Composition and transition accounting

`provenance.composite_statistics` includes:

- Family-window fractions, primary versus supporting exposure, active-curvature
  exposure by family, primary and geometric family counts, family counts and
  the actual ordered IDs/labels.
- Entry, exit, length and seam flag for every window; longest/shortest primary
  windows and contiguous same-label regions.
- Full cyclic boundary events, including the last-to-first event even when the
  map's finish line lies inside a window.
- Actual endpoint curvature **and curvature-rate jumps**, along with changes in
  window peak curvature/rate. G2 does not imply G3: an explicitly requested
  clothoid may have a curvature-rate jump against a constant-curvature segment.
- Left/right heading balance, directional alternation, absolute heading change,
  global clearance and reserved footprint margin.
- A six-state direct transition matrix: the five primary families **plus an
  explicit connector state**. Every annotation boundary contributes once.
- A five-family projected order matrix, accompanied by an explicit connector-ID
  chain and distance for every projected edge. It must not be interpreted as
  direct adjacency with the connectors silently removed.
- Cyclic primary-family switches, annotation boundaries, and their densities per
  100 m. Same-family directional reversals can matter physically without being
  a family-label switch.

A separate physically significant envelope-change indicator compares neighboring
window peak curvature against the declared threshold, or observes a reversal
of nonzero turn signs. It is a geometric indicator, **not** a measured driving
success metric. Counts of labels, annotation boundaries and demand changes stay
separate; all can differ.

Nested `internal_driving_regions` partition each window into straight, left curve,
right curve or curvature-reversal regions. They are not added to family exposure.
For example, a chicane's long internal separation straight stays visible rather
than disappearing inside a generic chicane label. Supporting straight return
legs are likewise visible inside connector windows. Actual zero-curvature
coverage is `1 - sum(active_curvature_exposure_by_family.values())`, and need not
equal the primary `straight` window fraction.

## Selector-window analysis is evaluation-only

A dedicated `<stem>_evaluation.csv` stores each centerline vertex's maneuver ID,
family/role, distance to its next maneuver boundary, region ID and distance to
the next region boundary. Its path is in `provenance.evaluation_csv`, outside the
fixed nine-artifact schema. Ground-truth labels are **not** appended to the
ordinary centerline CSV and are **not** added to simulator policy observations.
No selector, adapter loading or training code is implemented.

Metadata also records all boundary-to-boundary distances, contiguous region
lengths, projected primary switch distances and optional timing estimates for
whole windows, contiguous regions and internal driving regions. Without an
explicit speed assumption, traversal time is not estimated. With speed `v`, the
estimate is `length/v`; with explicit environment step duration `dt`, the nominal
number of selection periods of `n` steps is `floor(length/(v*dt*n))`.

The pilot explicitly assumes **2 m/s** and **0.05 s per environment step** for
analysis. The latter matches the inspected reference simulation default with
`action_repeat: 1`; it is not forced into any environment. Selection periods
5/10/20 steps therefore correspond to assumed travel distances 0.5/1/2 m, with
10 steps the declared initial default. These constant-speed opportunity counts
are estimates, not evidence that a controller maintains that speed or can switch
successfully. All difficulty ratings stay `unrated`, vehicle calibration stays
as recorded, and physical drivability stays `unassessed`.

## Identities, duplicates, lineage and native replay

Each native recipe records explicit ordered requests, resolved parameters and
ranges, construction/connector constraints, candidate seed/attempt, flags, seam,
vehicle snapshot, experiment ID and analysis assumptions. Its generator ID is
new and unknown versions reject. A full canonical configuration SHA-256 produces
the readable `composite_<digest>` filename stem. Recipe replay uses the saved
resolved requests and never samples ranges again.

Separate identity fields record requested-order hash, parameter-inventory
multiset hash, layout topology, measured symmetry, parent lineage and two layout
fingerprints. The principal fingerprint canonicalizes the closed continuous
curvature-segment profile under circular shifts, reflection and traversal
reversal, merging adjacent constant-curvature segments (including across the
seam). A polygon edge/turn fingerprint independently normalizes sampled layout
translation/rotation, reflection and cyclic start. Quantization tolerances are
explicit implementation choices, not a universal proof of equivalence between
arbitrary curve representations. Common cyclic/reversed/reflected and split-
straight representations are not counted as independent geometry.

Configuration IDs can differ when labels, seam, seed or representation differ,
while the layout fingerprint remains the same. Pilot acceptance checks both
fingerprints and track IDs. Lineage defaults group the same versioned parameter
inventory regardless of ordering; the matched pair shares lineage. No final
train/validation/test split is assigned.

Pilot candidate budgets are bounded and rejected seeds, exact requests, closure
trials and reasons are retained. Missing cases produce an explicit incomplete
manifest. There is no threshold relaxation, strategy fallback or overwrite of
existing bundles. Publication stages the data, runs the real consumer smoke,
reconstructs the native recipe and compares the nine standard artifacts plus
evaluation CSV before reserving a fresh destination. Timings remain separate
from deterministic artifacts.

## Commands

```bash
python3 scripts/generate_composites.py pilot \
  --recipe examples/phase3_pilot/pilot_recipe.json \
  --output generated_maps/phase3_reproduction --marl-race-root ../marl_race \
  --profile generated_maps/phase3_reproduction_runtime.json
python3 scripts/plot_composite_pilot.py generated_maps/phase3_reproduction
python3 scripts/generate_composites.py replay \
  examples/phase3_pilot/<track-id>/<track-id>_generation.yaml \
  --output generated_maps/composite_replay --marl-race-root ../marl_race
python3 scripts/audit_composite_rejections.py --output generated_maps/phase3_rejection_reproduction.json
```

Use fresh paths: immutable output and evidence protection is intentional. The
saved pilot recipe owns its recorded seed and per-request budget. Without a saved
pilot recipe, `--seed`, `--max-attempts`, and an actual `--vehicle` YAML construct
the default eight requests. For custom Python use, put `src` on `PYTHONPATH`,
construct `ManeuverRequest`/`CompositeSpec`, then call `generate_composite_bundle`.
The old generator CLIs keep their original recipe contracts.
