# Phase 4B results and review guide

Implemented from clean map-edit HEAD **`35ad6a7`** (`tech maps`). This phase was
entirely offline: no external simulator checkout was accessed, no smoke tests or
controller rollouts were run, and no training, final 60-track dataset, commits
or pushes were performed. Existing Phase 0–3B generator source, recipe versions,
export defaults and golden outputs remain unchanged.

The new backend is **`map_editor.extended_geometry.v1`**, layout method
**`bounded_supporting_turns.v1`**. Recipes explicitly declare composite intent;
metadata retains **schema 2.0.0** and the existing honest corner vocabulary.
See the [new layout/width contract](extended_geometry.md) for all parameters,
optimization, acceptance, periodic-width and offline replay details.

## Twelve accepted circuits

The [pilot manifest](../examples/phase4b_pilot/manifest.json) is complete:
**4 long technical + 4 long irregular mixed + 4 matched width-comparison tracks**.
The [deterministic pilot recipe](../examples/phase4b_pilot/pilot_recipe.json)
records exact requests, topology alternatives, bounds and seeds.

Review:

- [Consistent metric-scale gallery](../examples/phase4b_pilot/plots/overview.png).
- [Diversity statistics](../examples/phase4b_pilot/plots/diversity_statistics.png).
- [Normalized layout distances](../examples/phase4b_pilot/plots/layout_diversity.png).
- [Spatial-scale sensitivity](../examples/phase4b_pilot/plots/scale_sensitivity.png).
- [Width pair 1](../examples/phase4b_pilot/plots/width_pair_1.png) and
  [width pair 2](../examples/phase4b_pilot/plots/width_pair_2.png), including
  bottleneck details, equal curvature and differing corridor profiles.
- [Full numerical multiscale analysis](phase4b_analysis.json).

Every track also has PNG/SVG scientific figures with colored geometry, signed
curvature, measured width/side profiles and primary-family exposure. Standard
occupancy previews, map PNG/PGM, ROS YAML, centerline/wall/profile CSVs, metadata,
native recipe, evaluation CSV and validation JSON are included. Gallery axes
use a common metric scale; per-track geometry is centered without scaling.

The table uses coordinate analysis at sigma **0.4 m** with ≤0.1 m resampling.
Raw lap length is the final exported polygon length; corner/reversal densities
use the smoothed curve length. A significant turning region requires
|κ| >0.025 inverse meters, length ≥0.6 m and accumulated turn ≥15°. These are
geometric regions, separate from maneuver annotation counts.

| Circuit / plot | Lap m | Significant turns | Turns / 100 m | p95 \|κ\| 1/m | Sustained min radius m | Longest straight m | Primary coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [long_technical_1](../examples/phase4b_pilot/plots/long_technical_1.png) | 309.999 | 15 | 4.845 | 0.370 | 1.565 | 40.80 | 60.8% |
| [long_technical_2](../examples/phase4b_pilot/plots/long_technical_2.png) | 344.999 | 15 | 4.353 | 0.336 | 1.905 | 49.00 | 65.4% |
| [long_technical_3](../examples/phase4b_pilot/plots/long_technical_3.png) | 384.998 | 16 | 4.161 | 0.357 | 1.731 | 57.30 | 63.5% |
| [long_technical_4](../examples/phase4b_pilot/plots/long_technical_4.png) | 424.998 | 18 | 4.240 | 0.351 | 1.769 | 40.70 | 62.0% |
| [long_irregular_mixed_1](../examples/phase4b_pilot/plots/long_irregular_mixed_1.png) | 309.999 | 12 | 3.875 | 0.283 | 2.421 | 30.90 | 79.7% |
| [long_irregular_mixed_2](../examples/phase4b_pilot/plots/long_irregular_mixed_2.png) | 344.999 | 13 | 3.771 | 0.221 | 2.873 | 49.30 | 80.5% |
| [long_irregular_mixed_3](../examples/phase4b_pilot/plots/long_irregular_mixed_3.png) | 384.999 | 14 | 3.639 | 0.225 | 1.994 | 57.60 | 80.3% |
| [long_irregular_mixed_4](../examples/phase4b_pilot/plots/long_irregular_mixed_4.png) | 424.999 | 14 | 3.296 | 0.219 | 2.049 | 59.80 | 68.8% |
| [width_pair_1_uniform](../examples/phase4b_pilot/plots/width_pair_1_uniform.png) | 259.999 | 15 | 5.778 | 0.349 | 1.907 | 37.20 | 80.1% |
| [width_pair_1_variable](../examples/phase4b_pilot/plots/width_pair_1_variable.png) | 259.999 | 15 | 5.778 | 0.349 | 1.907 | 37.20 | 80.1% |
| [width_pair_2_uniform](../examples/phase4b_pilot/plots/width_pair_2_uniform.png) | 279.999 | 15 | 5.365 | 0.373 | 1.731 | 41.60 | 79.0% |
| [width_pair_2_variable](../examples/phase4b_pilot/plots/width_pair_2_variable.png) | 279.999 | 15 | 5.365 | 0.373 | 1.731 | 41.60 | 79.0% |

The eight long circuits span **310–425 m**, with **12–18 significant turning
regions** and **3,917–5,371** retained centerline samples. The width comparisons
have **260 m** and **280 m** centerlines with 3,303 and 3,541 samples. Short,
medium and long design presets are 70–140, 140–260 and 260–450 m; a separate
regression validates a 120 m request using the same backend.

All layouts are asymmetric: measured halfturn residuals range from **4.43 to
37.87 m** across the pilot. Primary coverage is **60.8–80.5%**, with supporting
coverage **19.5–39.2%**, inside the explicit 60% floor and 40% cap. The long
technical tracks have p95 curvature about **0.336–0.370 inverse meters**; the
mixed tracks span **0.219–0.283**. Reversal density, left/right balance,
angle/radius distributions, shortest significant turn, corner spacing, near-
straight exposure and all four analysis scales are in the numerical report.
Family diversity is recorded separately from these geometric demand dimensions.

The pilot deliberately varies global turn budgets and fixed straight lengths,
including elongated routes, unequal cluster angles and a returning mixed layout.
All three candidate placement arrangements contribute winners. There are **ten
unique centerline fingerprints** and twelve corridor identities: the two
intentional width-pair duplicates account for the difference. The independent
polygon fingerprints agree about the matched pairs. Layouts are not counted
again by seam, reflection or travel reversal.

Normalized coordinate RMS distances remove translation, scale, rotation, seam,
reflection and reversed traversal. Among unmatched tracks they range about
**0.05875–0.35553**. The closest pair is long technical 1 / width-pair 1, and the
largest separation is mixed 4 / width-pair 2. Early balanced-cluster candidates
had a much narrower upper distance (about 0.137); unequal primary turn budgets
and straight lengths expanded the actual route shapes. Some local feature and
route similarities remain. These distances are approximate diagnostics without
a validated near-duplicate threshold, not proof that all future samples are
sufficiently independent. Exact duplicate centerlines outside explicit width
pairs are rejected by the pilot workflow.

## Matched width experiments

Both pairs preserve the **complete centerline CSV byte for byte**, including
positions and travel headings. Their primary maneuvers, supporting geometry,
selection journal and curvature are identical within each pair. Width cannot
change the candidate winner; an invalid requested corridor rejects the request.
The manifest records actual centerline SHA-256 hashes and distinct width hashes.

| Pair member | Vector min / mean / max m | Width std m | Minimum raster normal width m |
| --- | --- | ---: | ---: |
| Pair 1 uniform | 1.500 / 1.500 / 1.500 | <0.000001 | 1.3856 |
| Pair 1 variable | 1.200 / 1.716 / 2.150 | 0.333 | 1.1013 |
| Pair 2 uniform | 1.500 / 1.500 / 1.500 | <0.000001 | 1.3883 |
| Pair 2 variable | 1.150 / 1.716 / 2.150 | 0.379 | 1.0508 |

Means/std are chord-length-weighted profile measurements. Variable sides are
independently specified, with smooth narrowing/widening and sustained
bottlenecks. Left/right endpoint offsets agree at the seam and gradients stay
within the explicit 0.12 bound. Pair 2 includes a 0.55 m left / 0.60 m right
bottleneck and asymmetrically widened sections. Both members of each pair pass
independent vector, full-vehicle and raster checks. No radius changes to make
space for width. The raster values measure first occupied-cell intersections
along both normals at every retained pose; they are distinct from nominal
widths and from global opposing-wall distance.

## Generalized closure and rejection evidence

The primary signed headings in the pilot total **260°, 280° or 300°**, rather
than the old method's required 360°. Explicit supporting bends supply the
remaining heading while a bounded nonlinear solve adjusts their angles and
supporting straight lengths jointly. Fixed primary radii, angles, body knots,
end transitions and primary straights are preserved. Each bend has a fixed
radius, bounded same-sign angle and smooth zero-curvature endpoints.

The solver uses a cached SE(2) motion model and finite-difference damped
Gauss–Newton steps, with active-bound re-solves and bounded line search. Source
x/y closure, heading and target length must satisfy maximum scaled residual
**2e-9**; existing geometric checks then apply independently. This is a local,
bounded search, without a global optimum or guaranteed-closure claim. A
regression also demonstrates both left and right supporting bends at their
bounds, closing in three iterations without primary deformation.

The final pilot evaluated **72 candidates**: **63 valid centerlines (87.5%)**,
**9 rejected (12.5%)**, **12 selected (16.7% of all proposals)** and **51 valid
but unselected**. Eleven of the twelve winners were later than the first proposal.
The same six-proposal budget applies to every request. Source geometry and
objective checks evaluate all proposals before expensive corridor work on the
fixed winner. Every accepted, rejected and valid-unselected decision remains in
the native metadata and validation report.

The nine pilot rejections comprise **six bounded closure failures** and **three
quantized centerline intersection failures**. All residuals, iteration histories,
initial/final variables, topologies, objective outcomes and reasons are retained.
The two pair-2 intersection failures are the same rejected centerline under two
independent width specifications; they are two candidate evaluations, not two
independent geometric discoveries. No rejection weakens bounds or changes a
requested primary maneuver.

[Additional rejection evidence](phase4b_rejections.json) records seven explicit
requests: an impossible supporting heading budget, a one-iteration solver cap,
insufficient corridor width, inside-offset singularity, excessive width
gradient, unreachable significant-corner count and a configured minimum-radius
violation. Requested ranges, measured objective failures and failure stages are
stored separately. These are bounded observations, not universal infeasibility
proofs. Earlier development exports and numerical experiments remain under
ignored `generated_maps`; the checked-in review pilot uses the final saved
requests and solver.

## Standalone validation and replay

All source/quantized centerlines, global winding, G2 joins, individual maneuver
measurements, source radius/rate limits, saved-profile steering-angle bounds,
wall intersections, opposing-wall separation, nonlocal gap, full-vehicle
sampled rectangle checks, corridor occupancy and full-area raster footprint
checks pass. Variable widths use the same analytic centerline; only final
normal offsets and occupancy change.

The local resolved F110 snapshot has 0.5 m length, 0.27 m width and 0.3302 m
wheelbase, with original source hash
`fb8bab7a7c49cb913c6adafbec84d4560e02d927087ff61956be0145f6288016`.
It is copied from a saved map-edit Phase 3B recipe and remains marked
uncalibrated. Its steering bounds are checked geometrically. No external
vehicle/configuration files, simulator dependencies, speed assumptions or
controller outcomes are consulted.

Across all twelve circuits:

- Maximum source join residual: **8.16e-10 m** position, **2.10e-13 rad** wrapped
  heading and **1.12e-16 inverse meters** curvature.
- Maximum analytic/sample curvature rate: **1.25 inverse square meters**, within
  the explicit 2.0 limit. Minimum requested primary radius is **1.6 m**.
- Minimum global exported opposing-wall separation: **1.14986903 m**, with
  **0.02 m footprint margin per side**; nonlocal gap certificate retained.
- Every retained vehicle pose passes exact segment/rectangle and full-area
  occupied-cell SAT checks. The minimum raster normal width is **1.05080316 m**,
  retaining more than the configured 0.7 m usable width after margins.
- Maximum physical source spacing **0.08 m**, raster resolution **0.05 m/pixel**,
  six-decimal CSV coordinates. All maneuver intervals partition the periodic
  lap, including a real seam-crossing feature.

Every bundle has geometric directional finish and `grid_1` spawn annotations.
**No simulator compatibility or physical drivability is claimed for this phase.**
Integration reports explicitly say `not_run / offline_geometry_scope`; physical
drivability is `unassessed`, difficulty `unrated` and split `unspecified`.
Labels and IDs are evaluation metadata, not policy observations.

**All twelve native recipe replays compare ten artifacts byte for byte**,
including all nine standard bundle files and the evaluation CSV. Recipe reload
repeats the whole optimizer, candidate ranking, width/raster validation and
export. Validation reports store SHA-256 hashes for all 120 deterministic
artifacts. Two additional fresh-process golden regressions forbid external
checkout file access and subprocess launches while rebuilding saved tracks.

## Profiling and regression results

[Final pilot profiling](phase4b_runtime.json) records **84.13 s** for all twelve
requests, full native replays and exports, without simulator work:

- Initial preparation: **30.96 s** total, **1.95–3.35 s per track**.
- Initial export: **10.87 s** total, **0.67–1.21 s per track**.
- Independent replay preparation/export: **41.92 s** total,
  **2.80–4.62 s per track**.
- Initial closure search: **0.73 s**; centerline analysis **13.32 s**; corridor
  validation **7.95 s**; measured width profiles **4.31 s**; raster validation
  **4.18 s**. Remaining time is metadata/publication overhead.

[Long-track cProfile and equivalence benchmark](phase4b_profile.json) covers a
**5,371-sample, 425 m** circuit and records the major call counts/times. For its
**2,495 × 2,453** raster, legacy fill took **1.240 s** and active-edge fill
**0.113 s**: approximately **10.98× faster with exactly identical pixels**.
Validated pixels are reused for export and previews. No centerline, wall or
footprint samples are removed. Supporting endpoint quadratures are cached
across Jacobian length probes. A NumPy distance-batching experiment was slower
(**0.912 s** versus **0.483 s**) and agrees exactly about global separation;
the existing indexed scalar method is therefore retained for acceptance.
These are host-specific timings, not guaranteed throughput. Plotting, analysis,
rejection audits, development trials and tests are outside pilot timings.

The offline baseline passed **308 tests, with five skipped**. The new module
adds **50 tests**, including long/short generation, bounded joint closure,
active-bound opposing turns, primary preservation, all-candidate ranking,
width periodicity/gradients, pair invariance, exact segment/raster equivalence,
crossings/overlaps, full-area footprints, raster widths, objective failures,
schema/identity integrity, immutable publication, partial manifests, duplicate
rejection, published evidence and guarded fresh-process replay.

The final full suite passed **358 tests, with five skipped, in 99.73 s**.
The five skipped legacy
tests inspect or execute an external checkout and are skipped before their
bodies under explicit `--offline-geometry`. Their normal behavior is preserved
when that option is absent; Phase 4B does not run them.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q --offline-geometry
python3 scripts/generate_extended.py pilot \
  --recipe examples/phase4b_pilot/pilot_recipe.json \
  --output generated_maps/phase4b_reproduction \
  --profile generated_maps/phase4b_reproduction_runtime.json
python3 scripts/analyze_extended_geometry.py --pilot generated_maps/phase4b_reproduction \
  --output generated_maps/phase4b_reproduction_analysis.json
python3 scripts/plot_extended_pilot.py --pilot generated_maps/phase4b_reproduction \
  --analysis generated_maps/phase4b_reproduction_analysis.json
python3 scripts/audit_extended_rejections.py \
  --output generated_maps/phase4b_reproduction_rejections.json
python3 scripts/profile_extended.py --output generated_maps/phase4b_reproduction_profile.json
```

Use fresh paths. No runtime dependency was added. Scientific plots use existing
Matplotlib; this host's unavailable-3D warning does not affect the 2D PNG/SVG
artifacts.

## Modified files and Phase 5 recommendations

New implementation:

- `geometry/width_profile.py`: periodic independent C1 side offsets and gradient bounds.
- `geometry/corridor.py`: variable walls, all-edge vector/footprint checks,
  indexed normal widths, raster ray widths and a benchmarkable distance prototype.
- `services/extended_spec.py`: independent native version, snapshot loading,
  topology/constraint contract and centerline/corridor identities.
- `services/extended_layout.py`: cached supporting motion, bounded joint nonlinear
  closure, active-bound steps and decision journals.
- `services/extended_tracks.py`: geometric objectives/ranking, full corridor and
  raster acceptance, periodic evaluation metadata, publication and exact replay.
- `services/extended_pilot.py`: twelve varied requests, duplicate handling,
  matched-pair hash checks, partial manifests and stage profiling.
- `services/offline_export.py`: active-edge corridor raster and shared-format
  export from already validated pixels.
- `services/extended_analysis.py`: offline multiscale/shape/width comparison.
- `scripts/generate_extended.py`, `analyze_extended_geometry.py`,
  `plot_extended_pilot.py`, `audit_extended_rejections.py`, `profile_extended.py`.
- `profiles/f110_resolved_phase3b.json`: local saved geometry snapshot.
- `tests/test_extended_geometry.py`: 50 new cases.

Existing files changed: `tests/conftest.py` adds the opt-in offline test mode;
README and the metadata guide link this phase. New documentation/evidence is
this report, the [contract](extended_geometry.md), analysis/runtime/profile/
rejection JSON, and `examples/phase4b_pilot` with twelve complete bundles,
manifest, exact pilot recipe and scientific plots. No legacy generator or
schema source was modified.

The method remains a bounded local geometric search over requested turn words,
slot placements and fixed supporting radii. It cannot optimize arbitrary
free-form routes, guarantee a feasible corridor for every centerline, or claim
global optimum. Pilot proposals use three placement arrangements and four
feature clusters; future topology coverage should be broader. Some unmatched
routes remain geometrically close. A near-duplicate cutoff and joint diversity
targets need validation before sampling at dataset scale.

Widths are C1 normal-offset profiles with an explicit gradient/cusp guard.
Footprints and raster minima are checked at retained poses, not continuously
through all inter-sample motions or all possible randomized spawns. Narrowing
on this saved centerline is geometric evidence only. Steering-rate-at-speed,
vehicle/surface calibration, braking transitions, dynamic traffic and controller
success are unassessed. Map annotations have not been tested in the simulator
in this phase, as required by scope.

For Phase 5, stratify the design across short/medium/long lengths, corner counts,
radius/angle distributions, asymmetric turn budgets, straight lengths and widths.
Retain matched centerlines in the same lineage/split group. Group near-duplicates
using both physical curvature fingerprints and normalized shape diagnostics;
choose thresholds with held-out geometric inspection. Add independent topology
families and controlled negative supporting-turn layouts, vary width placement
relative to corner clusters, and examine long-track memory/raster budgets before
larger generation. Assign final dataset splits only after those lineage rules
are explicit. Any later controller/integration evaluation should be separately
authorized and recorded. **Stopped after Phase 4B; final dataset not started.**
