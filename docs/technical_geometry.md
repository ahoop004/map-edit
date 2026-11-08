# Technical geometry and layout contract

Phase 3B uses a separate recipe generator, **`map_editor.technical_layout.v1`**,
and layout version **`distributed_connector_projection.v1`**. It does not change
Phase 0–3 recipe interpretation. Technical bundles declare
`generation_mode: composite` and geometry family `technical_distributed_layout`.
Ground-truth labels remain evaluation metadata; no policy observations change.

## Explicit corner vocabulary

The new `geometry.technical.technical_corner` returns a physical-curvature
maneuver assembled from existing `CurvatureSegment` objects. Its parameters are:

| Parameter | Contract |
| --- | --- |
| `radius_m` | Positive initial body radius; 2 m default |
| `end_radius_m` | Positive final body radius; defaults to initial radius |
| `turn_angle_deg` | Positive complete turn angle, including end ramps |
| `direction` | `left` or `right` |
| `transition_m` | Positive entry and exit ramp lengths; 0.65 m default |
| `kind` | `corner`, `kink`, or `compound_corner` |
| `apex_radii_m` | Compound-only ordered positive body radius knots |

`corner` accepts 30–150°, `kink` 5–35°, and `compound_corner` 30–210°.
An ordinary 90° tight corner is explicitly a **corner**, not a hairpin or sweeper.
The overlap at vocabulary endpoints is intentional: experimental intent is
explicit and measured geometry must satisfy its chosen class. Existing hairpin,
chicane, S-curve and straight requests retain their Phase 1 contracts. In
particular, a hairpin still requires a measured 150–210° heading reversal.

A single corner uses a constant, increasing-radius or decreasing-radius body.
Each curvature ramp is smoothstep in physical arclength. For body knots
`k[i] = sign / radius[i]`, all body cells have the same length

```
remaining_angle = requested_angle - transition_m * (|k[0]| + |k[-1]|) / 2
cell_length = remaining_angle / sum((|k[i]| + |k[i+1]|) / 2)
```

Angles too small for the fixed entry/exit transitions are rejected. The body
interpolates **curvature**, not radius, monotonically between knots. Increasing
radius therefore means decreasing curvature magnitude. Compound requests use
at least five knots, with at least two interior curvature maxima each exceeding
both adjacent knots by 0.03 inverse meters. Compound `apex_radii_m` are the
authoritative body radii; the scalar radius arguments are retained in the request
for complete replay. Entry/exit curvature and curvature rate are zero. Curvature
and its first derivative are continuous across these smoothstep cells.

Every annotation records the complete request, measured signed/absolute angle,
length, minimum radius, sampled and coordinate-reconstructed curvature,
curvature rate, achieved body radii, profile classification and tolerances.
Technical acceptance includes existing length/tangent/curvature/direction checks,
angle error ≤0.005 rad, knot curvature error ≤0.002 inverse meters and knot radius
relative error ≤1%. Compound classification also verifies the two achieved
maxima. The configurable `CornerTolerances` applies to direct measurement; the
v1 generator uses its recorded defaults. A short opposing combination can use
the existing S-curve with smaller explicit radii and ramps; it is not relabeled
as a single corner.

## Schema 2 compatibility

[`track-metadata-v2.schema.json`](../src/map_editor/schemas/track-metadata-v2.schema.json)
introduces schema **2.0.0** with `corner`, `kink`, `compound_corner`. The rest of
the closed-track sidecar structure is retained. Schema 1.0.0 and its vocabulary
remain unchanged and are still validated. The validator dispatches explicitly
on version and rejects unknown versions. Old generators keep their original
schema and byte output. The parametric preparation adapter has an explicit
schema-2 option used by this backend; its default recipe serialization omits
that option so legacy recipes remain byte-identical.

## Technical specification

`services.technical_spec.TechnicalSpec` is the native recipe. Recipe envelope
`schema_version: 1` is separate from metadata schema 2.0.0. Saved recipes contain
resolved parameters; there is no replay-time parameter resampling.

| Field | Meaning / default |
| --- | --- |
| `inventory` | 4–24 uniquely named `TechnicalRequest` objects |
| Request `family`, `parameters` | Exact constructor vocabulary and arguments |
| Request `straight_after_m` | Fixed **primary** straight after that feature; default 0 |
| `topology_orders` | Explicit full inventory permutations, default original order |
| `candidate_budget` | 1–64 candidate proposals, default 6 |
| `optimization_iterations` | 1–10,000 projection iterations/proposal, default 2,000 |
| `connector_bounds_m` | Positive min/max for **every** adjustable straight, default 0.4–18 m |
| `target_lap_length_m` | Fixed source-curve total length equality, default 120 m |
| `lap_length_range_m` | Final exported chord-length acceptance, default 110–130 m |
| `objectives` | Hard measured target ranges; also guide candidate ranking |
| `maximum_supporting_fraction` | Final supporting exposure cap, default 0.45 |
| `minimum_primary_coverage` | Final primary exposure floor, default 0.55 |
| `minimum_useful_corner_m` | Minimum final primary non-straight window, default 0.6 m |
| `track_width_m` | Uniform corridor width, default 1.5 m |
| `spacing_m` | Maximum physical sample spacing, default 0.1 m |
| `resolution_m_per_pixel` | Corridor occupancy resolution, default 0.04 m |
| `padding_m` | Raster padding, default 1 m |
| `seam_offset_m` | Periodic seam request snapped to nearest retained source vertex, default 1.7 m |
| `vehicle`, `limits` | Resolved actual vehicle and explicit existing `GeometryLimits` |
| `seed` | Nonnegative integer controlling candidate length targets |
| `variant`, `category`, `dataset_id` | Explicit identity and experimental intent |
| `generation_mode`, `layout_version` | Fixed version/intent declarations |

A request has a name, family, constructor parameters and optional fixed following
straight. Allowed primary families are the three new corner types plus the
existing hairpin, straight, chicane and S-curve. The v1 distributed-straight
layout requires zero-curvature feature endpoints. It rejects a request whose
fixed signed headings do not sum to +360°. The old generators still provide
mirroring, reversed travel, repeated blocks and bounded return layouts; this
new layout backend constructs CCW circuits and does not reinterpret those
existing APIs. It has no free-curve heading correction.

## Distributed connector optimization

A candidate selects an explicitly allowed inventory permutation. Place all
primary curves and fixed primary straights rigidly, with no deformation. The
remaining displacement `d` and connector headings `h[i]` are then known.
Connector lengths `l` solve three affine equalities:

```
sum(l[i] * cos(h[i])) = -d.x
sum(l[i] * sin(h[i])) = -d.y
sum(l[i]) = target_lap_length - fixed_primary_length
lower <= every l[i] <= upper
```

For each candidate, deterministic seeded desired lengths are sampled around the
remaining-length mean. Dykstra projection minimizes squared distance from those
desired lengths over the intersection of the affine subspace and box bounds.
It alternates an exact 3×3 affine projection and a box projection with correction
vectors. Both feasibility residual and iterate change must converge to 1e-9;
a final roundoff-sized affine correction is rechecked against bounds. Rank
deficiency, impossible total connector length or exhausted iteration budgets
produce explicit rejections with residual histories. This is constrained convex
geometric optimization for a fixed turn word, not a general nonlinear track
planner or proof of global feasibility.

Only designated supporting straight lengths adjust. Every connector is an
explicit `transition` annotation recording its straight source primitive,
length, zero endpoint curvature and adjustable role. Requested corner radii,
angles, end ramps, body knots and primary straights never change. Alternatives
vary placement/order and connector lengths. A complete closed simple circuit
always has cycle topology; here “candidate topology” means the ordered turn and
placement arrangement, not different graph connectivity.

All budgeted candidates are evaluated, rather than stopping at the first valid
closure. Invalid geometry and failed hard objectives are rejected. Valid
candidates are ranked by mean squared normalized target-center distance,
plus the measured repetition proxy, minus 0.03 times reversal density and 0.01
times halfturn asymmetry residual capped at 20 m. Lowest score wins; ties choose
the earliest candidate. This is a **geometric candidate-selection score**, never
a scalar physical difficulty or drivability rating. Every selected, rejected
and valid-unselected candidate, target length vector, optimized lengths,
optimization history, residual and decision is retained in metadata.

## Measured complexity targets

`objectives` accepts finite ordered `[min,max]` ranges for:

- `corner_density_per_100m`, `maximum_curvature_inv_m`, `p95_curvature_inv_m`.
- `curvature_reversals`, `near_straight_fraction`, `longest_straight_m`.
- `minimum_corner_angle_deg`, `maximum_corner_angle_deg`,
  `median_corner_angle_deg`, `p90_corner_angle_deg`, `corner_angle_std_deg`.
- `shortest_significant_corner_m`, `raw_lap_length_m`.
- `primary_coverage`, `supporting_fraction`.
- `symmetry_error_m`, `repetition_fraction`.
- `long_straight_to_tight_corner_count`: ≥20 m exactly zero-curvature approach
  immediately before a primary turn with peak curvature ≥0.4 inverse meters.

User targets intersect the mandatory lap/coverage bounds; neither can override
or weaken the other. Family count/exposure is recorded separately from these
geometric demand measurements. All arc exposure uses final CSV chord lengths.
The ordinary centerline remains the same consumer schema. A separate evaluation
CSV provides each vertex's maneuver ID, family, role and distance to the next
window boundary. Windows partition the periodic lap, including seam-crossing
windows; existing Phase 3 nine-decimal boundary tie handling is reused.

## Scale-explicit measurements and validation

Coordinate analysis ignores CSV theta and velocity fields. It removes duplicate
closing/consecutive points, resamples the periodic polygon at ≤0.1 m and applies
a periodic Gaussian in physical source arclength with sigma 0, 0.15, 0.4 or 0.8 m.
Curvature is the signed turn between neighboring polygon edges divided by their
mean length. Curvature rate uses periodic central differences. Percentiles are
uniform source-arclength sample percentiles; smoothing slightly shortens the
curve, and both raw and smoothed lap lengths are recorded. The v1 complexity
acceptance uses **sigma 0.4 m**. Raw peaks and analytic source limits are still
checked independently, so smoothing cannot hide invalid generated geometry.

Near-straight means |curvature| ≤0.025 inverse meters. Significant turning
regions are contiguous same-sign above-threshold runs with ≥0.6 m smoothed
length and ≥15° accumulated heading change. Straight gaps remain separate;
short corner lobes are not counted as significant regions. Reversals count
cyclic changes between significant turning directions. Region counts differ
from requested annotation counts. The sustained radius is the inverse of the
largest mean |curvature| over a 1 m **source-resampling** window. All definitions,
thresholds, per-region values and distributions are in the comparison JSON.

Halfturn symmetry uses the existing arclength-sampled coordinate residual.
Repetition is the maximum positive normalized signed-curvature autocorrelation
at 1/2, 1/3 or 1/4 lap. These are targeted diagnostics, not an exhaustive symmetry
group analysis. Exact profile and polygon fingerprints remove seam shifts,
reflection and reversed traversal. The comparison report adds approximate
normalized coordinate RMS distances after optimal rotation, cyclic seam,
reflection, reverse traversal and scaling; those supplement exact fingerprints
and do not constitute a universal near-duplicate classifier.

All existing centerline, wall intersection, global separation, nonlocal gap,
source radius/rate, full-vehicle sampled footprint, corridor raster, full-area
raster footprint and quantized six-decimal CSV checks apply. Required geometric
steering angles are checked against the resolved vehicle snapshot. No speed is
assumed and no steering-rate-at-speed or controller performance claim is made.
Reference widths are sampled normal-ray estimates and nearest-wall distances,
not certified vehicle clearances. Generated validation reports retain their
separate full-vehicle checks.

Publication refuses existing output directories, writes through staging, adds
compatible finish/named spawn geometry, executes the actual consumer smoke,
loads the saved native recipe, reruns the complete candidate selection and
compares the nine standard artifacts plus evaluation CSV byte for byte. A
mismatched prepared result cannot be published under another recipe. Duplicate
winning geometry is rejected; duplicate filters cannot silently choose a
different native winner. Validation reports include hashes, geometric checks,
consumer evidence and replay results. Splits remain `unspecified` and physical
drivability remains `unassessed`.

```bash
python3 scripts/generate_technical.py pilot --output generated_maps/technical_review \
  --profile generated_maps/technical_runtime.json --marl-race-root ../marl_race
python3 scripts/analyze_technical_geometry.py --pilot generated_maps/technical_review \
  --output generated_maps/technical_comparison.json
python3 scripts/plot_technical_pilot.py --pilot generated_maps/technical_review \
  --analysis generated_maps/technical_comparison.json
python3 scripts/generate_technical.py replay PATH_TO_GENERATION_YAML \
  --output generated_maps/technical_replay --marl-race-root ../marl_race
```

NumPy supplies the optimizer; there is no new runtime dependency. Matplotlib is
needed for the scientific plots, as in earlier phases. Use fresh evidence paths.
See [Phase 3B results](phase3b_results.md) for the accepted pilot and limitations.
