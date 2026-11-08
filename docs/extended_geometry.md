# Extended offline geometry contract

Phase 4B introduces **`map_editor.extended_geometry.v1`**, with layout method
**`bounded_supporting_turns.v1`** and native recipe envelope `schema_version: 1`.
Metadata stays at **2.0.0**: no new maneuver labels are required. Existing Phase
0–3B generators, schemas, recipe versions and default export paths are untouched.

All new generation, acceptance, replay, analysis and plotting are offline. There
is no simulator checkout argument, discovery, smoke test or controller rollout.
The default [local resolved snapshot](../profiles/f110_resolved_phase3b.json) is
copied from the already checked-in Phase 3B recipe. Every native recipe embeds
the resolved vehicle geometry, calibration status and original provenance hash.
A missing external checkout never changes geometric acceptance.

## Specification and length design

`services.extended_spec.ExtendedSpec` stores exact primary requests, explicit
supporting-motion topologies, bounds and measured objectives. Saved recipes are
fully resolved; replay does not resample primary parameters.

| Field | Meaning / default |
| --- | --- |
| `inventory` | 4–32 uniquely named existing `TechnicalRequest` objects |
| Request `family`, `parameters` | Existing Phase 3B constructors and classification |
| Request `straight_after_m` | Fixed requested primary straight; never adjusted |
| `topologies` | Named complete inventory orders and explicit supporting-turn slots |
| `target_lap_length_m` | Source physical-arclength equality, default 350 m |
| `lap_length_range_m` | Accepted final exported chord length, default 300–450 m |
| `connector_length_bounds_m` | Positive min/max for every supporting straight, default 0.4–32 m |
| `candidate_budget` | Deterministic bounded proposal count, 1–64, default 6 |
| `optimization_iterations` | Nonlinear iteration cap, 1–200, default 70 |
| `width` | Periodic independent left/right normal offset profile |
| `spacing_m` | Maximum physical source sample spacing, default 0.08 m |
| `resolution_m_per_pixel` | Corridor raster resolution, default 0.05 m |
| `padding_m` | Raster padding, default 1 m |
| `seam_offset_m` | Seam request snapped to nearest retained physical source vertex, default 1.7 m |
| `maximum_supporting_fraction` | Final supporting exposure cap, default 0.40 |
| `minimum_primary_coverage` | Primary exposure floor, default 0.60 |
| `minimum_useful_corner_m` | Final primary non-straight window floor, default 0.6 m |
| `maximum_offset_curvature` | Conservative inside-offset/radius ratio cap, default 0.95 |
| `objectives` | Hard ranges on measured geometric and width statistics |
| `limits` | Existing explicit radius, rate, usable width, footprint and nonlocal-gap limits |
| `vehicle` | Resolved local geometry snapshot, embedded in recipe |
| `seed` | Nonnegative deterministic candidate seed |
| `variant`, `category`, `dataset_id`, `matched_group` | Explicit experiment identity and pair membership |
| `generation_mode`, `layout_version` | Fixed composite intent and version declarations |

`LENGTH_PRESETS` supplies short **70–140 m**, medium **140–260 m**, and long
**260–450 m** design ranges. These are initial dataset design choices, not
universal validity limits; a recipe supplies its own positive target and range.
A regression demonstrates a valid 120 m configuration using the same backend.
The pilot's long circuits target 310, 345, 385 and 425 m; measured significant
turn counts must lie in 12–20. Requested source length and final polygon length
are distinct. Sampling does not stretch the curve to repair a chord-length
acceptance failure.

Primary families are the existing Phase 3B `corner`, `kink`, `compound_corner`,
`hairpin`, `straight`, `chicane` and `s_curve`. Their radius, angle, internal
transition and achieved-classification contracts remain unchanged. This layout
method requires zero-curvature primary endpoints. Fixed end ramps must belong
to the requested primary feature. It constructs CCW circuits with exactly one
positive full-lap winding; earlier APIs retain their own reflection/travel modes.

## Supporting motion and nonlinear closure

A `LayoutTopology` has a name, a complete inventory permutation and zero or more
`SupportingTurn` slots. Each slot identifies the inventory item after which a
supporting bend is inserted, following any fixed primary straight. It records:

| Field | Contract |
| --- | --- |
| `after_index` | Unique valid primary inventory index |
| `angle_bounds_deg` | Same-sign finite min/max, at most 150° absolute |
| `radius_m` | Positive fixed supporting radius, default 5 m |
| `transition_m` | Positive fixed entry/exit smoothstep ramp, default 0.7 m |

Angle bounds exclude zero and must allow the fixed ramp's heading budget.
Alternative topologies can add/remove or relocate slots instead of crossing
through a degenerate zero-length bend. Both positive and negative supporting
turns are supported and tested. The pilot uses positive turns in alternative
cluster-exit, in-cluster and reordered-cluster arrangements. Here topology means
ordered geometric placement; all accepted tracks remain single simple cycles.

Each supporting bend uses the existing parametric-curvature sweeper construction
but is honestly annotated as a supporting `transition`. Its source primitive,
optimized angle, fixed radius, ramps, actual length and measured acceptance are
retained. Curvature is bounded by `1 / radius_m`; entry/exit curvature and rate
are zero. A separately designated supporting straight follows every primary
item/optional supporting turn. Only these straight lengths and supporting bend
angles are optimization variables. Primary curves and primary straights are
rigid, with no parameter scaling, fitting or deformation.

The solver caches fixed local SE(2) primary motions and supporting endpoint
quadratures. It first projects sampled supporting angles onto the bounded
heading-sum equality. If the fixed primary heading deficit cannot fit the
supporting bounds, that topology is rejected immediately. Primary heading is
**not required to sum to 2π**.

For variables `z = [supporting straight lengths, supporting angles]`, the
nonlinear residual is:

```
r(z) = [end_x, end_y, 10 * (end_heading - 2*pi),
        total_source_length - target_lap_length]
```

A finite-difference Jacobian uses 0.0001 m length probes and 0.00001 rad angle
probes. Damped minimum-norm Gauss–Newton steps solve a 4×4 system. Variables at
a bound whose proposed step points outward are removed from the free set and
the correction is re-solved. Eight bounded damping attempts and four line-search
scales per iteration bound the work. Every accepted step decreases residual
squared norm; variables remain within their explicit bounds. Convergence
requires maximum scaled residual below **2e-9**, followed by existing source
G2/closure validation. No tolerance, radius, angle or corridor limit is relaxed
on failure. There is no global optimality, universal feasibility or guaranteed
closure claim.

Every candidate records its topology, primary heading, initial and final
supporting variables, angle bounds, iteration residual/damping history,
function-evaluation count and closure decision. Every budgeted proposal is
considered; first-valid acceptance is not used. Source and quantized centerline
checks precede expensive corridor work. Among accepted centerlines, ranking uses
mean squared normalized objective-center distance plus the repetition proxy,
minus 0.03 times reversal density and 0.01 times halfturn asymmetry residual
capped at 30 m. Ties select the earlier proposal. This is an explicit geometric
candidate-selection score, never physical difficulty or controller success.

## Width profiles and controlled comparisons

`geometry.width_profile.WidthProfile` stores `left` and `right` sequences of
`(lap_fraction, positive_offset_m)` knots plus `maximum_gradient` (0.12 default).
Fractions strictly increase from 0 to 1; endpoint offsets must agree on each
side. Two equal knots give a constant width. `WidthProfile.constant(width,
left_fraction=.5)` supports a constant asymmetric corridor as well.

On each interval, offsets interpolate with `3t² - 2t³`. Values and first
derivatives are continuous, including at the lap seam; second derivatives may
jump. Each interval's analytic peak side gradient is checked against the bound.
Widths use physical source arclength measured from the final exported seam.
Boundary width is C1; source centerline G2 remains independently enforced.

At a pose with heading `h`, boundaries are:

```
left_wall  = center + left_offset  * [-sin(h), cos(h)]
right_wall = center - right_offset * [-sin(h), cos(h)]
```

Inside offsets must satisfy `curvature * left_offset < cap` and
`-curvature * right_offset < cap`. This conservative cusp guard is explicit even
when a nonzero width derivative could mathematically avoid a cusp. No corner
radius changes when width changes. Boundary coordinates are quantized to six
decimal places before final checks, just as centerline coordinates are.

Centerline candidate scoring excludes width. After the winning centerline is
fixed, its requested width profile undergoes full acceptance. A failed corridor
rejects the request; it cannot silently select a different centerline. This
policy preserves matched experiments. `centerline_configuration_sha256` omits
width-specific identity/targets; actual profile and polygon fingerprints
independently identify geometry without width. Corridor identity includes the
width specification. Matched-pair publication preflights centerline CSV hashes
and requires distinct width specifications. The final manifest verifies actual
centerline bytes, not just requested parameters or an approximate shape score.
Exact centerline duplicates outside explicit matched groups are rejected.

Final profile rows contain normal-ray distances to the nearest actual wall on
each side, not merely requested offsets. Rays use an indexed exact segment
intersection search. Standard profile columns remain unchanged. Metadata's
existing mean-width field is the profile-row mean; extended width statistics
also report chord-length-weighted sample mean and standard deviation. Independent
side minima, minimum/maximum total width and raster width remain separate.

## Hard objectives and scale analysis

Each objective is a finite ordered `[minimum, maximum]` range. Geometry targets
and width targets are evaluated separately, with requested ranges, measured
outcomes and a structured failure list preserved in the decision journal.
Mandatory lap and coverage bounds intersect optional targets; one cannot weaken
the other.

Geometry keys include the Phase 3B metrics plus `corner_count`,
`minimum_sustained_radius_m` and `left_turn_fraction`:

- Raw lap length, significant corner count/density, reversals and near-straight fraction.
- Maximum and p95 absolute curvature, sustained minimum radius, longest straight,
  shortest significant corner and significant turn-angle min/max/median/p90/std.
- Primary/supporting fractions, left-turn fraction of absolute significant heading,
  halfturn residual and repetition proxy.
- The existing long-straight-to-tight-corner count objective remains available.

Width keys are `minimum_width_m`, `maximum_width_m`, `mean_width_m`, `width_std_m`
and `minimum_raster_width_m`.
Segment ordering is controlled through the allowed topology permutations;
annotation order and primary-family exposure/count are recorded separately.

The existing Phase 3B coordinate-only periodic analysis is reused unchanged at
sigma **0 / 0.15 / 0.4 / 0.8 m**, with ≤0.1 m analysis resampling. Acceptance
uses sigma **0.4 m**. Near-straight means |κ| ≤0.025 inverse meters; significant
turns require ≥0.6 m and ≥15° above that threshold. Analytic source radius/rate
checks remain unsmoothed, so analysis smoothing cannot hide invalid geometry.
Family diversity and geometric demand are separate statistics. Halfturn residual
and curvature autocorrelation at half/third/quarter lap are diagnostics, not an
exhaustive symmetry test. The offline analysis also reports normalized coordinate
RMS distances removing translation, scale, rotation, seam, reflection and reverse
traversal. These are approximate diversity diagnostics without a certified
near-duplicate cutoff; zeros are expected within matched width pairs.

## Validation and performance

The source and quantized centerline must pass closed position/heading/curvature,
full-lap winding, intersection, analytic minimum-radius/maximum-rate and saved
vehicle steering-angle checks. No speed or controller envelope is assumed.
Both final walls must be simple, with global opposing-wall separation and the
existing nonlocal gap certificate. The full vehicle rectangle plus margin is
checked against nearby wall segments at every retained pose.

Corridor occupancy uses the same cell-center even-odd fill and one-pixel wall
stroke as previous generators. A new active-edge scanline implementation avoids
scanning every wall edge for every raster row. Shared CSV/PNG/PGM encoders,
finish-line construction and ROS metadata conventions are reused. Exact
byte-equivalence tests and a long-track benchmark compare the new fill against
the existing implementation. The legacy exporter itself is unchanged. Validated
pixels are reused for export and occupancy preview rather than rasterized again.
An explicit 64-million-cell raster budget prevents runaway allocations.

Raster acceptance tests every centerline segment at half-cell spacing, every
sampled full vehicle rectangle against **all occupied cells overlapping its
area** with the existing SAT test, and exact left/right normal ray traversal of
occupied cell rectangles at every retained pose. Ray ties include cells touched
at grid corners. Reported minimum raster normal width must retain the configured
usable width after the per-side footprint margins. This is an actual sampled
raster measurement, not a nominal-width claim. It does not prove a continuous
minimum over every possible pose or continuous swept-body clearance.

Profiling also compares scalar and NumPy-batched opposing-wall segment distance.
The existing indexed scalar implementation is retained for production acceptance
because it is faster at these spacings; the experimental batched implementation
remains benchmarkable. Both use the same global all-edge distance metric. No
clearance sampling is dropped for speed.

## Publication, replay and tests

The standalone exporter stages files and refuses any existing destination.
Bundles contain the nine standard artifacts, evaluation CSV and validation JSON.
Labels/IDs remain evaluation-only. Periodic maneuver windows partition the full
lap, including a seam-crossing interval. The ordinary centerline schema is
unchanged; it receives no maneuver labels. Named spawn and directional finish
annotations use the actual centerline travel geometry and final wall distances.
They are geometric annotations with no Phase 4B simulator integration claim.

Publication reloads the saved native recipe, independently repeats optimization,
selection, width/raster validation and export, and compares **ten deterministic
artifacts byte for byte**. Reports contain artifact hashes, measured statistics,
validation and all candidate decisions. Integration is explicitly
`not_run / offline_geometry_scope`, physical drivability `unassessed`, driving
difficulty `unrated`, split `unspecified`. Profile wall times stay outside
deterministic artifacts. Partial manifests record request failures and rejection
stages; no retry broadens constraints.

```bash
python3 scripts/generate_extended.py pilot --output generated_maps/phase4b_review \
  --profile generated_maps/phase4b_review_runtime.json
python3 scripts/analyze_extended_geometry.py --pilot generated_maps/phase4b_review \
  --output generated_maps/phase4b_review_analysis.json
python3 scripts/plot_extended_pilot.py --pilot generated_maps/phase4b_review \
  --analysis generated_maps/phase4b_review_analysis.json
python3 scripts/generate_extended.py replay PATH_TO_GENERATION_YAML \
  --output generated_maps/phase4b_replay
python3 scripts/audit_extended_rejections.py --output generated_maps/phase4b_rejections.json
python3 scripts/profile_extended.py --output generated_maps/phase4b_profile.json
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q --offline-geometry
```

The explicit pytest option skips five existing tests that inspect/run an external
checkout, before their bodies execute. Default legacy test behavior is unchanged.
All remaining legacy regression and golden-replay checks run. New fresh-process
replay tests forbid external checkout file access and subprocess launches.
Dependencies remain the existing NumPy, PySide6, PyYAML and JSON Schema; scientific
plots use Matplotlib. See [Phase 4B results](phase4b_results.md) for final evidence,
limitations and Phase 5 recommendations.
