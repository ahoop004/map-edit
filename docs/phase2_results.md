# Phase 2 results and review guide

Implemented from clean map-edit HEAD `31ac353` (`map gen`). The read-only
reference remains `marl_race` branch `physics-correctness`, commit
`8a4bddf97c6de7740263b962a74ae4ae88fec0da`. No simulator changes, commits or pushes
were made. Phase 0/1 source generator versions, primitive geometry, CSV schemas
and original artifact replay are preserved.

The separate **`map_editor.specialist_templates.v1`** recipe declares specialist
intent, target family and minimum exposure explicitly. Supporting straights or
turns do not change the experimental role into `composite`. Metadata remains
schema **1.0.0**. See the [template and parameter contract](specialist_templates.md)
for closure proofs, inputs, ranges, identity policy and measurement definitions.

## Ten-track pilot

The accepted pilot is in [`examples/phase2_pilot`](../examples/phase2_pilot/manifest.json).
Its deterministic [manifest](../examples/phase2_pilot/manifest.json) gives every
track's paths, identity, exposure, requested minimum, features and validation
report. The [pilot recipe](../examples/phase2_pilot/pilot_recipe.json) records the
complete requests, numerical ranges, seed and bounded candidate budget.

[Overview](../examples/phase2_pilot/plots/overview.png) shows target-family geometry
in blue, supporting geometry in orange, boundaries in gray and finish segments
in green. Each family has a PNG and SVG comparison with geometry and signed
curvature versus final exported arc length:

- [Straights](../examples/phase2_pilot/plots/straight_comparison.png)
- [Hairpins](../examples/phase2_pilot/plots/hairpin_comparison.png)
- [Sweepers](../examples/phase2_pilot/plots/sweeper_comparison.png)
- [Chicanes](../examples/phase2_pilot/plots/chicane_comparison.png)
- [S-curves](../examples/phase2_pilot/plots/s_curve_comparison.png)

| Family | Variant / travel | Final lap (m) | Target-family exposure | Required minimum | Primary target features |
| --- | --- | ---: | ---: | ---: | ---: |
| Straight | 1 / CCW | 85.9795 | 75.753% | 70% | 2 |
| Straight | 2 / CW | 123.9070 | 80.132% | 70% | 2 |
| Hairpin | 1 / CCW | 24.5797 | 83.726% | 70% | 2 |
| Hairpin | 2 / CW | 33.1868 | 81.921% | 70% | 2 |
| Sweeper | 1 / CCW | 50.7301 | 92.115% | 80% | 2 |
| Sweeper | 2 / CW | 64.8357 | 87.661% | 80% | 2 |
| Chicane | 1 / CCW | 77.3537 | 67.878% | 60% | 6 |
| Chicane | 2 / CW | 93.4617 | 69.685% | 60% | 6 |
| S-curve | 1 / CCW | 93.2889 | 73.365% | 65% | 6 |
| S-curve | 2 / CW | 127.4872 | 76.320% | 65% | 6 |

Variants differ by measured geometry, not merely ID or travel direction:
straight feature lengths are about 30.57 versus 44.64 m; target hairpin radii
about 2.96 versus 4.06 m; target sweeper radii about 7.12 versus 9.10 m, with
requested angle changing from π to 2.8 rad; chicane displacement/radius/spacing
increase; S-curve radii and per-lobe severity increase. Each pair exceeds the 5%
measured-variation requirement. CW reverses travel around the constructed layout;
it does not manufacture a distinct layout by changing direction alone.

Every bundle has ROS YAML, corridor occupancy PNG/PGM, ordinary centerline/wall
CSVs, curvature/width profile, schema-1.0.0 maneuver metadata, a native specialist
generation recipe, occupancy preview, and a validation report. The report
contains checks and SHA-256 hashes of all nine standard artifacts. `grid_1` is a
named spawn before the finish, with the actual centerline travel heading.
No dataset split has been assigned; all splits are `unspecified`.

## Acceptance and rejection evidence

The final root seed is **42**, budget **8 attempts per request**. All ten final
pilot requests passed on their first candidate: **10 accepted, 0 rejected,
complete=true**. No constraint was relaxed. An intermediate run was preserved
under ignored `generated_maps` while correcting the straight-before-turn metric;
the published review pilot contains the corrected, merged-run measurements.

[`phase2_thresholds.json`](phase2_thresholds.json) records 20 separate geometric
feasibility trials without exporting a training collection: 15 geometrically
valid candidates, five rejected for offset-boundary curvature singularities.
Of the 15 valid candidates, eight meet their family's default dominance policy
and seven do not. These observations informed family-specific thresholds:

| Family | Observed geometric exposure fractions | Default minimum |
| --- | --- | ---: |
| Straight | 53.5%, 75.4%, 83.3%, varying straight length | 70% |
| Hairpin | 91.2%, 72.3%, 46.5%, varying approach/exit length | 70% |
| Sweeper | 95.8%, 85.2%, 65.7%, varying approach/exit length | 80% |
| Chicane | 41.2%, 58.3%, 67.7%, with 1/2/3 repetitions per half-lap | 60% |
| S-curve | 47.9%, 64.8%, 73.4%, with 1/2/3 repetitions per half-lap | 65% |

These are operating points for the constrained template, not universal maximum
exposure or drivability claims. An impossible 100% request, duplicate layouts,
insufficient geometric variation and geometry failures remain explicit rejected
candidates in the bounded-generation regression tests. Tests verify exhaustion
produces a partial manifest, records the seed and reason, and never lowers a
threshold. Existing output directories are rejected without changing their data.

## Geometry, compatibility and difficulty measurements

All final tracks have 1.5 m requested width, 0.15 m maximum curve-sample spacing,
0.04 m/pixel binary corridor occupancy and `negate: 0`. Sample counts range from
172 to 858. The actual exported opposing-wall minimum gap across the pilot is
**1.49952923 m**, with at least **1.45952923 m** usable width after the reserved
0.02 m margin on each side. The largest source join residuals are about
**3.10e-14 m**, **1.13e-15 rad**, and **5.55e-17 inverse m** for position, heading
and curvature. Peak absolute curvature-change rate is at most **1.0 inverse m²**,
within the configured 2.0 limit. Quantized coordinate checks are recorded
separately from source differential continuity.

Global/nonlocal boundary checks, sampled full configured-vehicle footprint,
conservative raster usable width, and full-area occupied-cell footprint checks
all pass. The vehicle snapshot comes from the actual reference combined-slip
configuration: 0.50 × 0.27 m body, 0.3302 m wheelbase, steering ±0.523599 rad and
rate ±3.2 rad/s, source SHA-256
`fb8bab7a7c49cb913c6adafbec84d4560e02d927087ff61956be0145f6288016`.

Each track reports full family and role fractions, per-family and directional
counts, annotated straight lengths and continuous runs, turn-lobe radii,
left/right heading balance, total absolute heading change, peak curvature/rate,
global clearance, target-active-turn fraction and requested/measured geometric
difficulty dimensions. Approach runs merge adjacent annotations across the seam.
For example, the straight specialists' longest continuous approaches are about
32.57 m and 49.64 m, rather than only the final short exit annotation.

The second sweeper has 87.66% sweeper-family coverage but 82.96% primary-target
role coverage: the difference is explicitly identified heading-correction
geometry. Straight approaches similarly contribute to straight-family exposure.
Embedded ramps and chicane spacing belong to their target windows, and their
contribution is also disclosed separately. No overlapping intervals or duplicate
transition accounting inflate the exposure sum.

No scalar or categorical driving difficulty was invented. Labels remain
**unrated**, tire calibration remains **uncalibrated**, and physical drivability
remains **unassessed**. Smaller connector radii can dominate peak curvature even
when most of the lap belongs to a larger-radius target family; the distributions
include those connectors transparently.

## Actual consumer integration and replay

For **all ten tracks**, publication ran the existing `scripts/smoke_marl_race.py`
against actual local consumer modules. Each per-track validation report records
reference commit, asset selection, closed centerline loading, PNG/PGM equality,
named and random-centerline spawns, finish validation and forward/reverse crossing,
LiDAR distance/ranges, swept wall/contact queries, out-of-map semantics and MPC
clearance-mask agreement. Forward crossings count, reverse/beyond-segment
crossings do not. Each report names `grid_1` as a successfully parsed spawn.

Each publication also loaded its saved native recipe, rebuilt and revalidated
geometry, regenerated all nine standard artifacts in a fresh staging directory,
and compared every byte before publishing. New regressions independently replay
all ten pilot bundles in their original standalone context. Phase 0 and Phase 1
checked-in reference artifacts also retain byte identity. The old generation-mode
inference remains unchanged for Phase 1 recipes; explicit specialist intent is
implemented only in the new versioned layer.

These checks are **static simulator integration**, not full vehicle controller
rollouts, successful circuit completion or training evaluations. Source/raster
footprint validity is sampled rather than a certified continuous sweep between
all poses. No tire/surface calibration, collision-free driving rate or transfer
performance is inferred.

## Runtime and regression results

[`phase2_runtime.json`](phase2_runtime.json) records the final ten-track run on
this host, separate from deterministic dataset artifacts. Total generation,
validation, full recipe replay and actual consumer smoke took **20.19 s**.
Initial geometric preparation took **2.32 s** in total; publication/replay/smoke
used **17.84 s**. Per-track preparation ranged **0.068–0.432 s**, and the latter
combined stage ranged **1.24–2.51 s**. Process startup, duplicated replay work and
consumer import/check overhead dominate this small pilot. Plot generation and
the independent threshold sweep are outside these timings. Existing Phase 1
spatial checks were reused; no broad geometry optimization was needed.

Baseline before changes: **169 tests passed**. Final complete suite:
**209 passed, no skips, in 34.94 s**. This includes Phase 0/1 GUI, YAML, geometry,
legacy replay and real-consumer regressions plus 40 Phase 2 cases for specialist
intent/composition, CW/CCW geometry equivalence, ranges/seeds, identity/lineage,
parameter rejection, turn-angle preservation, dominance, merged straight metrics,
bounded retry/partial manifests, duplicate/overwrite prevention, CSV-precise
intervals, named spawns, artifact hashes and all-ten golden replay. `git diff
--check` passes. The reference working tree remains clean.

## Reproduce

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
python3 scripts/generate_specialists.py pilot --output generated_maps/phase2_reproduction \
  --recipe examples/phase2_pilot/pilot_recipe.json --marl-race-root ../marl_race \
  --profile generated_maps/phase2_reproduction_runtime.json
python3 scripts/plot_specialist_pilot.py generated_maps/phase2_reproduction
python3 scripts/evaluate_specialist_thresholds.py \
  --vehicle ../marl_race/configs/vehicle/combined_slip.yaml \
  --output generated_maps/phase2_threshold_reproduction.json
```

Choose fresh output paths: deliberate overwrite protection applies to bundles,
pilots and timing evidence. The saved pilot recipe owns its original seed and
budget. The Matplotlib 3D-import warning on this host does not affect the completed
2D scientific PNG/SVG plots. No new runtime dependency is required beyond Phase 1.

## Modified-file summary and Phase 3 recommendations

- `services/specialist_templates.py`: distinct versioned specification, parameter
  validation/defaults/ranges, exact half-turn constructions, physical traversal
  reversal and stable identities.
- `services/specialist_tracks.py`: quantized export measurements, explicit
  specialist intent, composition and difficulty dimensions, validation reports,
  named spawn, no-overwrite publication, native replay and consumer smoke.
- `services/specialist_pilot.py`: bounded per-request candidate selection,
  rejection reasons, duplicate/variation checks, deterministic manifest and
  separate runtime evidence.
- `scripts/generate_specialists.py`, `evaluate_specialist_thresholds.py`,
  `plot_specialist_pilot.py`: reproducible generation/replay, geometric feasibility
  evidence and final-asset visualizations.
- `tests/test_specialist_tracks.py`: 40 cases including all-ten artifact replay.
- `docs/specialist_templates.md`, this report, threshold/runtime JSON,
  `examples/phase2_pilot/`, `README.md` and a metadata-guide cross-reference.

Phase 3 should add controlled composite sequencing and additional layout
families while preserving each requested maneuver's achieved measurements.
Treat supporting-connector curvature as an explicit design constraint: it can
be tighter than the dominant target. Keep primary-role and family-window
coverage distinct, and investigate target-active-curvature exposure where long
internal straights matter. Broaden parameter-validity exploration before a full
collection, and add continuous clearance or validated controller evaluations
before assigning dynamic difficulty. Retain exact lineage and shape identity
for later leakage-aware splitting; no final split policy has been assigned.
The current lineage groups are deliberately broad and do not prove mathematical
shape equivalence or split independence. A general layout optimizer, full
60-track dataset and training remain out of scope. **Stopped after Phase 2.**
