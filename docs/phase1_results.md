# Phase 1 results and review guide

Implemented against map-edit HEAD `913c31e` (`compat`), starting from a clean
working tree. Reference read-only checkout:
`marl_race` branch `physics-correctness`, commit
`8a4bddf97c6de7740263b962a74ae4ae88fec0da`. No reference source changes, commits or
pushes were made. The legacy sampler and geometry calculations are unchanged.
Phase 1 stops at reusable primitive/sequence construction and a small review set;
no 60-track collection, RL/LoRA workflow, Phase 2 or Phase 3 was implemented.

The [parameter and numerical contract](parametric_geometry.md) documents the API,
formulas, tolerances, measurement definitions, vehicle assumptions and limitations.
The Phase 0 metadata schema remains **1.0.0**. The new generator identifier is
**`map_editor.parametric_curvature.v1`**.

## Review the generated examples

[Overview plot](../examples/phase1/overview.png) shows all nine demonstrations.
Every example directory has a centerline/boundary plot and curvature-versus-arc-
length plot in `geometry.png` and exportable `geometry.svg`, plus
`measurements.json` and a differential profile CSV. Aggregate and per-maneuver
measurements are collected in
[`demonstrations.json`](../examples/phase1/demonstrations.json).

| Example | Physical length (m) | Exported chord length (m) | Signed heading change (rad) | Min radius (m) | Peak abs curvature rate (1/m²) |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Left hairpin](../examples/phase1/hairpin_left/geometry.png) | 13.566371 | 13.566052 | +3.141593 | 4 | 0.375 |
| [Right hairpin](../examples/phase1/hairpin_right/geometry.png) | 13.566371 | 13.566052 | -3.141593 | 4 | 0.375 |
| [Long straight](../examples/phase1/long_straight/geometry.png) | 40.000000 | 40.000000 | 0 | unbounded | 0 |
| [Left/right chicane](../examples/phase1/chicane_left_right/geometry.png) | 8.692881 | 8.692778 | 0 | 4 | 0.375 |
| [Right/left chicane](../examples/phase1/chicane_right_left/geometry.png) | 8.692881 | 8.692778 | 0 | 4 | 0.375 |
| [S-curve](../examples/phase1/s_curve/geometry.png) | 14.566371 | 14.566231 | 0 | 5 | 0.300 |
| [Varying sweeper](../examples/phase1/sustained_sweeper/geometry.png) | 16.279645 | 16.279524 | +2.094395 | 6 | 0.208333 |
| [Smooth primitive sequence](../examples/phase1/smooth_connections/geometry.png) | 23.600000 | 23.599949 | +1.075000 | 8 | 0.0625 |
| [Closed stadium](../examples/phase1/closed_stadium/geometry.png) | 51.132741 | 51.132104 | +6.283185 | 4 | 0.375 |

The chicanes achieve signed displacement +3 m and -3 m while returning to their
entry heading. The S-curve uses radii 5 m and 7 m and two opposing 60-degree
bends. The varying sweeper transitions between body radii 6 m and 9 m over a
120-degree turn. All examples have 1.5 m nominal corridors. Labels are validated
against final measurements; every difficulty rating remains **unrated**.

The largest sequence join residuals across these examples are:
position **1.8303e-15 m**, wrapped heading **2.4493e-16 rad**, curvature **0**.
The closed stadium's opposing-boundary minimum distance is **1.49988349 m**.
After two 0.02 m margins, usable vector width is **1.45988349 m**. Its full
configured vehicle rectangle passes at all 512 distinct sampled poses, including
raster occupied-cell overlap tests. The nonlocal gap policy certifies at least
0.1 m outside a 4.5 m centerline arc neighborhood. These are sampled geometric
results, not a continuous footprint sweep or a driving-success claim.

The first eight examples are **open geometry**, not simulator maps. Their wall
CSV format is unchanged, with wall endpoints left open explicitly. The ninth is
a true closed bundle:
[`closed_stadium.yaml`](../examples/phase1/closed_stadium/closed_stadium.yaml).
It was assembled from two unmodified 12 m straights and two unmodified 4 m-radius
hairpins with 1 m entry/exit transitions. Symmetry closes the circuit; no closure
fitting changed a requested maneuver.

## Actual simulator integration and replay

[`phase1_smoke.json`](phase1_smoke.json) records a successful run through the real
consumer modules: map selection/configuration, PNG/PGM agreement, centerline and
wall assets, periodic centerline detection, random-centerline spawn, finish-line
validation/tracking, LiDAR, swept collision queries and MPC clearance masks.
Forward finish crossing is accepted; reverse and beyond-endpoint crossings are
rejected. The 817 × 384 raster uses 0.03 m cells and `negate: 0`. Consumer float32
lap length is about 51.132137 m; source chord length is 51.132104 m.

New closed bundles retain ordinary centerline/wall CSV schemas, compatible finish
annotations, profile CSV, images, preview, schema-1.0.0 metadata and a parametric
recipe. Tests replace the old spline sampler with a failure to demonstrate it is
not used. Replaying the new recipe reproduces every generated bundle artifact.
The checked-in Phase 0 bundle also reproduces every artifact byte in its original
standalone CLI context, in addition to the existing GUI and recipe regressions.
The numerical contract explains Qt's pre-existing PNG physical-DPI metadata
variation between GUI and standalone contexts.

## Performance

[`phase1_profile.json`](phase1_profile.json) records the new preparation profile
and includes the original Phase 0 baseline. Both use a 17 m lap and 1 m width;
Phase 0 used a rounded spline oval and Phase 1 an analytic circle. The new timed
scope includes classification, global boundary distance, nonlocal-gap checks,
vehicle footprint, rasterization, raster footprint and metadata validation.
The old scope was geometry/profile validation. These are single-host observations
with different geometry and scope, not a controlled universal speedup claim.

| Centerline samples | Phase 0 geometry wall time | Phase 1 full preparation wall time | Phase 1 instrumented time |
| ---: | ---: | ---: | ---: |
| 340 | 0.340 s | 0.084 s | 0.179 s |
| 850 | 2.204 s | 0.298 s | 0.748 s |
| 1,700 | 8.470 s | 0.966 s | 2.323 s |

The conservative grid makes self-intersection checks inexpensive in these dense
local tracks. At 1,700 samples, global opposing-boundary separation dominates
with about 1.35 s cumulative under cProfile; self-intersections take about 0.13 s
and raster footprint checks 0.15 s. Narrow-phase distance calls are about 37,357,
versus Phase 0's 7,217,350 intersection predicates, though these are different
operations. A first new-backend profile identified unnecessary footprint segment
checks; adding footprint AABB rejection removed them without changing geometry
or the legacy validation path. Grid results agree with exhaustive predicates in
randomized and adversarial tests. Worst-case dense/coincident geometry may still
be quadratic; no general asymptotic guarantee is claimed.

## Test results and reproduction

Baseline: **116 passed** before Phase 1. Full Phase 1 suite: **169 passed**,
no skips, in **20.73 s** on this host. Coverage includes analytic line/circle
geometry, independent adaptive integration, three sample resolutions,
convergence, mirroring/rigid placement, requested/measured radius/angle and
classification failures, G1/G2/wrapped-heading joins, degeneracy, intersections,
nonlocal pinches, vector and full-area raster footprint checks, real vehicle
configuration parsing, closed seam/full-lap metadata, deterministic recipe
replay and all previous GUI/bundle regressions. `git diff --check` passes.

```bash
python3 -m pip install -r requirements-dev.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
python3 scripts/demonstrate_maneuvers.py --output examples/phase1 \
  --vehicle ../marl_race/configs/vehicle/combined_slip.yaml
python3 scripts/generate_parametric.py \
  examples/phase1/closed_stadium/closed_stadium_generation.yaml \
  --output generated_maps/phase1_replay
python3 scripts/smoke_marl_race.py \
  examples/phase1/closed_stadium/closed_stadium.yaml --marl-race-root ../marl_race
python3 scripts/profile_parametric.py --output docs/phase1_profile.json
```

Matplotlib/SciPy are development/demo dependencies; the backend adds only NumPy
to the application dependencies. This host's Matplotlib reports unavailable 3D
axes because of mixed system/user installations; the saved 2D PNG/SVG plots are
complete. The reference repository is optional for core geometry and replay.
Real consumer integration requires its dependencies and checkout; an unavailable
checkout is explicitly reported as a skipped integration test.

## Modified files

- `geometry/curves.py`: physical-arc differential states, analytic lines/circles,
  clothoid/smoothstep ramps, deterministic quadrature and sampling.
- `geometry/maneuvers.py`: six parameterized constructors, mirroring and seeded
  user-range sampling. `geometry/__init__.py` exports the new API/version.
- `geometry/sequence.py`: rigid placement, continuity tolerances, sampled spans,
  closed seam checks and arc consistency.
- `geometry/measurement.py`: final differential/chord measurements, independent
  position curvature and measured feature acceptance.
- `geometry/spatial.py`, `geometry/validation.py`: conservative broad phase,
  global/nonlocal gaps, footprint checks, vehicle configuration snapshots,
  hard limits and separate speed-dependent advisories.
- `services/parametric_track.py`: closed backend preparation, unchanged schema
  integration and versioned recipe replay.
- `services/procedural_track.py`: shared export entry point for prepared geometry;
  no changes to legacy fitting/sampling. `services/wall_extraction.py`: optional
  open-wall CSV export, preserving the default closed output.
- `scripts/generate_parametric.py`, `demonstrate_maneuvers.py`,
  `profile_parametric.py`: replay CLI, review set/plots and reproducible profiling.
- `tests/test_parametric_geometry.py`: 53 new cases, alongside all legacy tests.
- `requirements.txt`, `requirements-dev.txt`, `README.md`, the parameter contract,
  this report, evidence JSON, and `examples/phase1/`: setup and review artifacts.

## Limits and recommendations for Phase 2

The closed adapter currently puts the lap seam at the first maneuver boundary;
arbitrary seam relocation through a maneuver is not a layout feature. Schema
semantics cover wrapping/full-lap intervals and are retained. Open demonstrations
have no artificial finish line, closed metadata, or occupancy-map claim. A
closed layout solver/composite circuit generator remains later work.

Validation is geometric and sampled. Refine or add certified swept-body checks
before claiming continuous clearance, especially around narrow transitions and
coarse rasters. The same-wall nonlocal-gap certificate deliberately excludes a
local arc neighborhood; it is not the global minimum over adjacent wall edges.
The conservative raster usable-width test can reject otherwise viable coarse
images. The classifier validates defined construction intent; it is not an
ambiguous-label-free shape classifier or a learned maneuver recognizer.

For Phase 2, first freeze these parameter/tolerance and recipe contracts with
reviewed per-family operating ranges. Add systematic parameter-range validity
exploration, measured feature coverage and provenance-aware dataset identities
and split policy. Calibrate the chosen vehicle and tire/surface assumptions;
evaluate steering-rate, speed envelopes and actual controller completion
separately from geometric acceptance. Verify maneuver identity after any later
connector/layout operation. Keep automatic closure, composite sequencing policy,
full dataset generation and training in their authorized later phases.
