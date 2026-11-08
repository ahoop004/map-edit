# Phase 3B results and review guide

Implemented from clean map-edit `1913172` (`composits`). The read-only reference
remains `marl_race`, branch `physics-correctness`, commit
`8a4bddf97c6de7740263b962a74ae4ae88fec0da`. No simulator modifications, training,
60-track collection, commits or pushes were made. Phase 0–3 generator outputs
and deterministic recipe interpretation are preserved.

The new generator is **`map_editor.technical_layout.v1`**, layout
**`distributed_connector_projection.v1`**. Its explicitly declared composite
intent is separate from its family count. Technical metadata uses **schema
2.0.0** for honest `corner`, `kink` and `compound_corner` labels. Schema 1 remains
available unchanged. See the [full parameter and layout contract](technical_geometry.md).

## Pilot and review artifacts

The [pilot manifest](../examples/phase3b_pilot/manifest.json) contains **12/12
accepted circuits**: three compact technical, three irregular mixed, three
hairpin/corner-dense and three long-straight/turn-transition cases. Each has nine
standard map assets, a separate evaluation CSV and a validation report. The
[pilot recipe](../examples/phase3b_pilot/pilot_recipe.json) records every exact
request, topology alternative, bound, objective and seed.

- [Consistent metric-scale gallery](../examples/phase3b_pilot/plots/overview.png),
  including Budapest and Hockenheim on the same **129 m × 129 m** axes.
- [Reference comparison](../examples/phase3b_pilot/plots/reference_comparison.png)
  across both references, five Phase 2, four Phase 3 and twelve Phase 3B examples.
- [Spatial-scale sensitivity](../examples/phase3b_pilot/plots/scale_sensitivity.png).
- [Curvature and corner-angle distributions](../examples/phase3b_pilot/plots/distributions.png).
- [Layout shape distance matrix](../examples/phase3b_pilot/plots/layout_diversity.png).
- [Full numerical comparison](phase3b_comparison.json), with all four smoothing
  scales, straight/corner/radius distributions, individual regions, spacing,
  reversals, heading variation, curvature rate and sampled wall measurements.

All plots also have standalone SVG versions. Each track has a PNG/SVG review
figure with the same metric geometry scale, signed curvature at three scales,
turn-angle sequence and family exposure. Standard bundle occupancy previews
retain their original metric resolution. Geometry is centered for plotting;
coordinates and dimensions are not scaled to fit individual panels.

All values in the next tables use coordinate analysis at Gaussian **sigma
0.4 m**, uniformly resampled at ≤0.1 m. Lap length is the raw exported polygon
length; densities use smoothed curve length. A significant turning region has
|curvature| >0.025 inverse meters, length ≥0.6 m and accumulated turn ≥15°.
The sustained minimum radius uses a 1 m source-resampling window. Counts are
measured geometric regions, not counts of family labels.

| Circuit / plot | Lap m | Corners | Corners / 100 m | p95 \|κ\| 1/m | Sustained min radius m | Longest straight m | Reversals / 100 m | Primary coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [Compact 1](../examples/phase3b_pilot/plots/compact_technical_1.png) | 86.417 | 8 | 9.301 | 0.594 | 1.342 | 13.49 | 4.650 | 67.6% |
| [Compact 2](../examples/phase3b_pilot/plots/compact_technical_2.png) | 112.718 | 10 | 8.905 | 0.540 | 1.560 | 18.99 | 5.343 | 71.6% |
| [Compact 3](../examples/phase3b_pilot/plots/compact_technical_3.png) | 95.465 | 8 | 8.414 | 0.548 | 1.345 | 10.50 | 4.207 | 62.3% |
| [Mixed 1](../examples/phase3b_pilot/plots/irregular_mixed_1.png) | 119.252 | 10 | 8.413 | 0.489 | 1.813 | 14.59 | 5.048 | 76.5% |
| [Mixed 2](../examples/phase3b_pilot/plots/irregular_mixed_2.png) | 102.184 | 9 | 8.839 | 0.460 | 1.615 | 16.40 | 5.892 | 68.7% |
| [Mixed 3](../examples/phase3b_pilot/plots/irregular_mixed_3.png) | 118.135 | 9 | 7.640 | 0.431 | 1.818 | 18.09 | 5.094 | 69.5% |
| [Dense 1](../examples/phase3b_pilot/plots/corner_dense_1.png) | 93.283 | 8 | 8.627 | 0.601 | 1.388 | 11.80 | 6.470 | 70.0% |
| [Dense 2](../examples/phase3b_pilot/plots/corner_dense_2.png) | 106.129 | 8 | 7.583 | 0.662 | 1.291 | 14.09 | 5.687 | 69.8% |
| [Dense 3](../examples/phase3b_pilot/plots/corner_dense_3.png) | 100.832 | 8 | 7.979 | 0.668 | 1.291 | 14.79 | 5.984 | 64.3% |
| [Long-straight 1](../examples/phase3b_pilot/plots/high_speed_transitions_1.png) | 187.349 | 8 | 4.276 | 0.317 | 1.478 | 46.19 | 2.138 | 76.0% |
| [Long-straight 2](../examples/phase3b_pilot/plots/high_speed_transitions_2.png) | 198.206 | 7 | 3.536 | 0.331 | 1.671 | 50.38 | 2.020 | 73.8% |
| [Long-straight 3](../examples/phase3b_pilot/plots/high_speed_transitions_3.png) | 216.047 | 7 | 3.243 | 0.288 | 1.538 | 58.89 | 1.853 | 72.7% |

The last category's native name is `high_speed_transitions`; this describes
long-straight experimental intent, not achieved speed or an assigned physical
rating. Every such track has **two** exact-straight approaches ≥20 m immediately
before a primary turn with peak curvature ≥0.4 inverse meters. Their longest
fixed primary straights are 45, 50 and 55 m. The proposed braking demand must
still be tested with a controller.

All twelve are asymmetric: measured halfturn residuals are **3.15–18.83 m**.
They use 7–10 turning requests, several explicit placement permutations,
different turn words and optimized distributed gaps. They are not copies
manufactured by changing seam, mirror or travel direction. All twelve profile
fingerprints and independent polygon fingerprints differ. After removing
translation, rotation, uniform scaling, seam, reflection and reversed traversal,
the closest pair has normalized coordinate RMS distance **0.10645** (the second
and third long-straight cases). The nearest reference-to-pilot pair is **0.28113**
(Budapest versus compact 3). These are approximate geometric diagnostics without
a validated near-duplicate threshold; they supplement exact duplicate rejection.

Primary coverage is **62.3–76.5%** and supporting coverage **23.5–37.7%**, inside
the explicit 55% primary floor and 45% supporting cap. Primary following
straights are fixed requested geometry; adjustable gaps remain separate
supporting annotations. Near-straight geometric exposure is higher than
supporting exposure because primary straights and shallow ramp ends also count.
Family diversity is reported separately from curvature, angle and density.

## What the references show

| Track | Lap m | Significant corners | Corners / 100 m | p95 \|κ\| 1/m | Sustained min radius m | Longest straight m | Near-straight | Reversals / 100 m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Budapest | 402.9 | 14 | 3.48 | 0.291 | 1.64 | 68.5 | 51% | 2.49 |
| Hockenheim | 359.9 | 13 | 3.62 | 0.319 | 1.13 | 28.9 | 61% | 1.67 |
| Phase 2 straight | 86.0 | 2 | 2.33 | 0.336 | 2.97 | 32.3 | 75% | 0 |
| Phase 2 hairpin | 24.6 | 2 | 8.19 | 0.341 | 2.93 | 1.7 | 14% | 0 |
| Phase 2 sweeper | 50.7 | 2 | 3.95 | 0.141 | 7.11 | 2.1 | 8% | 0 |
| Phase 2 chicane | 77.4 | 14 | 18.16 | 0.336 | 2.97 | 1.8 | 19% | 15.57 |
| Phase 2 S-curve | 93.3 | 14 | 15.07 | 0.336 | 2.97 | 0.8 | 6% | 12.91 |
| Phase 3 five symmetric | 163.5 | 14 | 8.57 | 0.240 | 3.98 | 19.6 | 30% | 7.35 |
| Phase 3 five asymmetric | 199.7 | 9 | 4.51 | 0.223 | 3.48 | 60.7 | 59% | 3.01 |

The missing distribution was not simply “more families” or “more reversals.”
Phase 2 opposing-turn specialists already have high reversal/corner density.
Phase 3 five-family circuits have milder sustained radii, relatively long
maneuver windows and restrictive placement/closure. The references mix tighter
local corner radii with substantially longer laps, irregular spacing and
longer straight-to-turn approaches. This pilot adds independently controlled
30–150° corners, tight radii, increasing/decreasing-radius bodies, multi-apex
corners, short kinks and mixed turn clusters. It does not reproduce either
reference's coordinates, route or full joint distribution.

Scale sensitivity matters. Budapest's raw p95 curvature is **0.599**, falling to
**0.314 / 0.291 / 0.275 inverse meters** at sigma 0.15 / 0.4 / 0.8 m. Its raw
maximum is **2.117**, versus **0.634** at sigma 0.4 m; maximum curvature rate
falls from **15.02 to 0.62 inverse square meters**. Hockenheim's raw p95 is
**0.521**, versus **0.329 / 0.319 / 0.316** at the three smoothed scales; raw
maximum **2.694** becomes **0.891** at sigma 0.4 m, and peak rate **13.47** becomes
**0.86**. Counting raw regions gives 12/20 corners versus 14/13 at sigma 0.4 m.
These large changes indicate that raw peak curvature and raw threshold-region
counts are strongly affected by centerline sampling noise. The sustained radii
and smoothed distributions retain genuine tight turning demand. Smoothing also
shortens curves and can increase local curvature in some places; it is not an
unbiased physical ground truth or a controller-feasibility test.

At approximately 2 m centerline sampling, normal-ray wall widths have minimum /
median **2.708 / 2.747 m** for Budapest and **2.301 / 2.354 m** for Hockenheim.
Nearest-wall sampled minimum distances are **1.260 m** and **1.124 m**. These are
reference wall estimates, without reference-vehicle footprint certification.
Generated tracks have an explicit 1.5 m corridor, so their relative width and
radius demands differ. The full report records valid ray counts, distributions
and source centerline/wall SHA-256 hashes.

## Closure, acceptance and rejection

The new solver fixes every primary curve and primary straight, then adjusts
one explicitly designated straight gap per request. Three affine equalities
solve x/y closure and target lap length, with per-gap bounds. A bounded convex
projection optimizer ranks alternative desired length vectors and allowed
inventory permutations. It cannot repair a wrong total heading and does not
change requested radii, angles, apex knots or end transitions.

The final run evaluated **72** candidates: **44 geometrically valid (61.1%)**,
**28 rejected (38.9%)**, **12 selected (16.7% of all proposals)** and **32 valid
but unselected**. All twelve requests completed within their six-candidate
budget. Seven winners were not the first candidate. Every rejection in this
pilot exhausted the 2,000-iteration connector search with nonzero equality
residual; all reasons, desired/solved lengths, histories and geometric ranking
decisions remain in each track's metadata and validation report. The manifest
collects rejection details. Residuals are search outcomes, not global proofs
that no alternate circuit exists.

[Separate rejection evidence](phase3b_rejections.json) documents five two-trial
failures with unchanged requests: impossible connector bounds, fixed primary
heading mismatch, excessive supporting fraction, unachievable curvature target,
and a configured minimum-radius violation. Regression tests additionally reject
excess curvature rate and offset singularities. No constraints were lowered to
obtain acceptance.

The rejection report also reproduces all six failed trials of the initial
second long-straight placement request. Earlier accepted development exports
are preserved under ignored `generated_maps`. The final pilot uses explicit
revised placement requests and category-specific
target ranges. Its published native recipes, not those intermediate requests,
define the review artifacts.

## Geometry and consumer evidence

All source and quantized centerlines/walls, intersections, nonlocal boundary
gaps, sampled full-vehicle footprint checks and full-area raster footprint
checks pass. The actual resolved F110 `combined_slip.yaml` snapshot is retained
in each identity: length 0.5 m, width 0.27 m, wheelbase 0.3302 m, steering bounds
±0.523599 rad; source hash
`fb8bab7a7c49cb913c6adafbec84d4560e02d927087ff61956be0145f6288016`.
The profile is marked uncalibrated. Geometric required steering angles fit its
bounds; steering-rate feasibility at speed is not claimed.

Across the twelve tracks:

- Minimum exported opposing-wall gap: **1.49899652 m**; reserved footprint margin
  **0.02 m per side**, with final usable/raster width bounds recorded.
- Maximum analytic/sample curvature rate: **1.58730159 inverse square meters**,
  below the explicit 2.0 limit. Minimum requested corner radius is **1.35 m**.
- Maximum join residual: **2.50e-14 m** position, **2.03e-15 rad** wrapped heading,
  **1.12e-16 inverse meters** curvature. G2 continuity is enforced.
- **895–2,188** centerline samples, maximum physical spacing 0.1 m;
  six-decimal CSV positions and corridor raster resolution 0.04 m/pixel.
- Every accepted track has valid periodic annotations, including an actual
  seam-crossing window, and evaluation-only vertex IDs/boundary distances.

**12/12 actual `marl_race` consumer smokes passed**, using the unchanged reference
checkout. Evidence covers centerline and wall loading, corridor occupancy,
`grid_1` named spawn, randomized centerline spawn, directional finish acceptance,
reverse and off-segment finish rejection, LiDAR/collision coordinate agreement,
out-of-map handling and MPC occupancy-mask agreement.

**12/12 native recipe replays passed**, rerunning the entire bounded candidate
search and comparing **10 artifacts byte for byte**. Two additional golden
regressions replay saved technical tracks in fresh Python processes. Existing
Phase 0–3 golden recipes also remain covered. Each validation report includes
artifact SHA-256 hashes and actual smoke/replay results. Validation reports
are evidence artifacts, not part of the ten deterministic bundle files.

## Tests and profiling

The baseline suite passed **255 tests in 55.42 s** before implementation. The
new technical test module adds **58 cases** for classification/tolerances,
compound apexes, tight opposing turns, exact bounded closure and optimum,
optimization exhaustion, primary preservation, all-candidate ranking, cyclic
fingerprints, duplicate winners, target intersections, curvature-rate/offset
failures, periodic metadata, schema compatibility, scale artifacts, native
roundtrips, partial manifests, immutable outputs, actual published evidence and
fresh-process golden replay. One existing test's unsupported schema version
moves from 2.0.0 to 3.0.0 because schema 2 is now supported; its rejection
assertion is retained. Schema 1 explicitly rejects new corner vocabulary.

The final full suite passed **313 tests in 77.69 s**, including all legacy
checks and the 58 new technical cases.

[Runtime profiling](phase3b_runtime.json) records **102.81 s** total for the final
pilot, including **34.71 s** candidate preparation and **68.05 s** staged export,
complete replay and actual smoke. Per-track preparation was **1.19–6.80 s** and
publication/replay/smoke **3.24–11.64 s**. Analysis, plots, rejection audits,
intermediate development and test-suite runtime are outside that profile.
Every track searches all six proposals and native replay searches them again;
this is intentionally more work than the earlier first-valid closure backend.
The scientific 2D PNG/SVG plots render despite this host's unrelated Matplotlib
3D-projection warning. No new runtime dependency is required.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
python3 scripts/generate_technical.py pilot \
  --recipe examples/phase3b_pilot/pilot_recipe.json \
  --output generated_maps/phase3b_reproduction \
  --profile generated_maps/phase3b_reproduction_runtime.json \
  --marl-race-root ../marl_race
python3 scripts/analyze_technical_geometry.py --pilot generated_maps/phase3b_reproduction \
  --output generated_maps/phase3b_reproduction_comparison.json
python3 scripts/plot_technical_pilot.py --pilot generated_maps/phase3b_reproduction \
  --analysis generated_maps/phase3b_reproduction_comparison.json
python3 scripts/audit_technical_rejections.py \
  --output generated_maps/phase3b_reproduction_rejections.json
```

Use fresh output/evidence paths. Native single-track replay is also available
through `generate_technical.py replay` as described in the contract.

## Modified files and remaining limits

New implementation files:

- `geometry/technical.py`: explicit corner/kink/compound primitives and achieved
  classification with measurement tolerances.
- `services/technical_spec.py`: native versioned specification and identity.
- `services/technical_layout.py`: bounded distributed connector optimization.
- `services/technical_tracks.py`: full candidate validation, measured hard
  objectives, ranking, periodic metadata, immutable publication and replay.
- `services/technical_pilot.py`: twelve controlled requests, duplicate prevention,
  partial manifests, rejection and runtime accounting.
- `services/technical_analysis.py`: spatial-scale comparison and wall estimates.
- `schemas/track-metadata-v2.schema.json`: explicit added vocabulary.
- `scripts/generate_technical.py`, `analyze_technical_geometry.py`,
  `plot_technical_pilot.py`, `audit_technical_rejections.py`: CLI and review evidence.
- `tests/test_technical_geometry.py`: 58 regression cases.

Existing files changed: `services/geometry_metadata.py` dispatches schema versions;
`services/parametric_track.py` adds explicit schema-2 preparation/measurement and
loading, with legacy serialization unchanged; `tests/test_phase0_contract.py`
retains the unsupported-version check against schema 3. README and metadata
contract link this phase. New deliverable files include this results guide,
[technical contract](technical_geometry.md), three numerical evidence JSONs and
`examples/phase3b_pilot` (twelve complete bundles, deterministic manifest/recipe,
and scientific PNG/SVG plots).

This pilot improves local corner severity and asymmetric placement, but does
not yet match the references' full distribution: compact tracks have fewer total
corners and shorter laps, much higher corner density and p95 curvature, while
the long-straight cases have comparable density but a larger near-straight
fraction (about 81–83%). The physical corridor is narrower than the references.
The fixed-turn-word convex backend cannot optimize arbitrary heading/curve
geometry, close every primary inventory or guarantee a globally optimal layout.
Its straight connectors and three proposed inventory permutations still limit
route realism. Fingerprints and approximate shape distances are not exhaustive
near-duplicate detection. Footprint checks are sampled, not continuous swept-body
certification. Curvature smoothing is an analysis choice, not ground truth.

Before controller evaluation, test steering-rate and braking envelopes at
explicit speeds and verify tire/surface calibration. Run complete laps and
record controller success, collision/off-track rates, tracking errors, speed
profiles and transitions into multi-apex and hairpin regions. Sweep the planned
5/10/20-step selector periods against actual traversal times without exposing
ground-truth labels as policy observations.

Before a final dataset, add longer 300–450 m irregular circuits with 12–20
turning regions, vary width independently of radius, broaden turn-word/topology
proposals and target joint reference-informed distributions rather than only
marginal severity. Validate near-duplicate thresholds, continuous swept clearance
and randomized spawn footprints, then retain lineage-aware split information for
Phase 5. No physical difficulty scores or drivability labels have been assigned.
**Stopped after Phase 3B.**
