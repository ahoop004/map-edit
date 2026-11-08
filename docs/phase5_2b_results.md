# Phase 5.2B — pilot recovered; V2 not ready

**10/10 pilot tracks accepted. The lightweight check does not establish reliable
60-track generation.** No formal V2 dataset was generated.

[Gallery](../generated_maps/phase5_2b_pilot/plots/overview.png) · [Visual comparison](../generated_maps/phase5_2b_pilot/index.html) · [Pilot CSV](../generated_maps/phase5_2b_pilot/comparison.csv) · [Readiness matrix](../generated_maps/phase5_2b_pilot/readiness_summary.csv) · [Readiness JSON](../generated_maps/phase5_2b_pilot/readiness_summary.json)

All output is in `generated_maps/phase5_2b_pilot`. The original Phase 5.2 directory
is unchanged. Its seven accepted bundles were copied byte-for-byte; only three new
bundles were published. Gallery and comparison panels share approximately 130 m
square metric axes.

## Recovery

| Track | Lap m | Primary maneuvers | Primary | Supporting | Active curvature | Significant turns | Hairpin radii m |
|---|---:|---|---:|---:|---:|---:|---:|
| hairpin_02 | 180 | 7 hairpins | 56.5% | 43.5% | 66.3% | 8 | 3.29–5.89 |
| hairpin_03 | 390 | 17 hairpins | 55.7% | 44.3% | 60.6% | 18 | 3.08–5.96 |
| composite_01 | 145 | 4 corners, 4 chicanes, 1 sweeper, 2 straights | **60.23%** | **39.77%** | 45.2% | 13 | — |

The two saved cluster solutions closed to below 1e-10 m residual, but connector
segments crossed primary U-turns and other connectors. The failure is a spatial
routing problem associated with ordering and supporting-bend placement, rather
than numerical closure or a small clearance deficit. Prior bounded searches already
repeated these failures; no additional cluster tuning was attempted. Diagnostic
sampling disabled intersection rejection solely to locate crossings; it was never
used for acceptance. [Crossing locations and composite diagnosis](../generated_maps/phase5_2b_pilot/failure_diagnosis.json).

Both hairpins adapt the working folded-lane design: alternating 180-degree turns,
unequal lane spacing, two supporting quarter-turns and a long return connection.
Counts, lap lengths and supporting radii differ. Compared with Phase 5.1, the medium
track changes from 9 turns at 210 m to 7 at 180 m, while the long track changes from
15 at 340 m to 17 at 390 m. Relative to the existing five-hairpin pilot, the outlines
and driving sequences differ visibly, but **all three share one hairpin topology**.
The long layout remains repetitive; topology diversification is limited.

The saved compact composite stalled in position/length closure with fixed primary
heading and no adjustable supporting-turn slots. Recovery reuses Phase 5.1's proven
145 m arrangement, inserting an actual chicane after its 115-degree corner where a
long connector previously followed. At the same lap length, primary coverage rises
from 58.0% to 60.23%, active exposure from 39.3% to 45.2%, and significant turns from
11 to 13. No connector was relabeled as a primary straight. The coverage margin is
small, and the sixth candidate was required; this arrangement is not robust yet.

Recovery: **3 accepted / 6 rejected candidate requests** (nine total, at most six
per missing track, one solver proposal each). The hairpins passed on attempts 2 and
1; the composite on attempt 6. Cumulative pilot history: **10 accepted / 52 rejected**,
including the previous 46 failures. All requests and resolved recipes remain in
[manifest.json](../generated_maps/phase5_2b_pilot/manifest.json).

## Lightweight readiness

Two deterministic draws per category exercised formal `candidate_spec()` across
five specialist families × three scales and four composite complexities × three
scales: **54 preparations, 21 geometric passes, 33 failures**. These used existing
closure, composition, width, vehicle footprint and raster validation, with zero
bundle publication or replay. They are a category screen, not 60 allocated tracks,
a calibrated success estimate, or the formal dataset audit.

| Category | Short passes / 2 | Medium passes / 2 | Long passes / 2 |
|---|---:|---:|---:|
| Straight | 2 | 2 | 2 |
| Hairpin | 2 | 1 | 2 |
| Sweeper | 2 | 1 | 2 |
| Chicane | 2 | 0 | 0 |
| S-curve | 0 | 0 | 2 |
| Composite: 2 families | 0 | 0 | 0 |
| Composite: 3 families | 0 | 0 | 0 |
| Composite: 4 families | 0 | 0 | 0 |
| Composite: 5 families | 0 | 1 | 0 |

Failures were 24 bounded-closure failures and nine primary/supporting coverage
failures. Eighteen categories passed fewer than two draws; fifteen had no successes.
The composites need the most work. A recovered pilot example does not imply that
arbitrary seeds in its category will succeed.

The unchanged independence policy flagged **three near-duplicate pairs** (medium
and long straights, short sweepers) and **two ambiguous pairs** (short straights and
short chicanes). Those pairs would fail the formal independence screen. Hairpin
samples showed parameter diversity where two succeeded, but still use one topology.
Full evidence, seeds, native recipes, failure journals and pair metrics are in
[readiness.json](../generated_maps/phase5_2b_pilot/readiness.json).

Formal V2 selection now calls `corrected_spec()`: rejected hairpin clusters are
excluded, and medium/long fallback cycles have different maneuver counts. Each
candidate seed receives **one** bounded solver proposal, avoiding three repeated
solves of the same fixed-heading failure; seed retries retain deterministic new
parameters. Existing formal near-duplicate rejection remains active. The readiness
flags show that seed changes alone still provide insufficient diversity in some
other categories. These findings are reported rather than triggering more tuning.

## Validation and scope

**17 targeted tests passed, 58 deselected** in 8.52 s, including correction inventory,
physical radii, strict composite coverage, bounded fallback, all 60 V2 specification
contracts and unchanged V1 candidate identities. The three recovered bundles passed
native replay: **30 byte-identical artifacts**. All 100 pilot artifact checksums
verified. Original seven bundles and source directory remained byte-identical.
[Verification](../generated_maps/phase5_2b_pilot/verification.json).

Changes: `research_design.py` adds corrective selection and bounds per-seed work;
`recover_research_diversity_pilot.py` adds the recovery/readiness workflow;
`generate_research_diversity_pilot.py` labels the revised gallery; targeted tests and
this report document the result. The original tuning factory and native recipe
interpreter are unchanged. `datasets/phase5_v1` and Phase 5.1 artifacts are unchanged.

No new closure solver, geometry primitives, simulator/controller work, full regression
suite, formal audit, dataset release, commit or push. Physical drivability remains
unassessed. **Stopped after this corrective pass.**
