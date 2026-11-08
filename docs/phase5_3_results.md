# Phase 5.3 — frozen V2 publication

Published release: [datasets/phase5_v2](../datasets/phase5_v2/README.md).
[60-track gallery](../datasets/phase5_v2/plots/overview.png) · [Gallery index](../datasets/phase5_v2/index.html) · [Master manifest](../datasets/phase5_v2/manifest.json) · [Train](../datasets/phase5_v2/train_manifest.json) · [Validation](../datasets/phase5_v2/validation_manifest.json) · [Test](../datasets/phase5_v2/test_manifest.json).

**All 60 selected tracks reproduce the Phase 5.2E preflight, with zero recipe,
track-ID, centerline-coordinate, identity or geometric-statistic differences.**
No candidate was replaced, reselected or tuned during publication.

## Frozen selection and coordinator

- Plan identity: `448fb2b45d961d105c7c0cac0dc134833ff8e0d0e597507896ca0c7a31b95642`.
- Canonical selected-list checksum: `bf78bd2f3277c78db7231736762aca161b380d0e822f8be759d6667f12babcd8`.
- Plan file SHA-256: `cdca80c8d9eb12ec99745168e9e1914ac3568e10b3cc2aa5a904382e983a9365`.

The new `freeze-selection` / `publish-selection` commands extend the existing
research-dataset coordinator. They verify the preflight's selector replay, quotas,
all selected native requests against the V2 specification, source metadata and
coordinates, and all 1,770 pairwise constraints. A checksum-protected frozen plan
records every selected slot, attempt, seed, track ID, full native recipe and
selection evidence. Publication consumes only these native requests and fails on
any mismatch, without using fallback candidates.

The existing bundle publisher supplies atomic staging, metadata validation,
standalone ROS-compatible exports and byte replay. Master/split checkpoints and
orphan adoption are reused. The original V1 coordinator path, native interpreters,
geometry primitives, closure solvers and independence policy are unchanged.

## Publication and integrity results

| Check | Result |
|---|---|
| Tracks | 60/60 |
| Split quotas | 40 train / 8 validation / 12 test |
| Physical length classes | 18 short / 22 medium / 20 long |
| Specialists / composites | 30 / 30; training 20 / 20 |
| Specialist quotas | Four per family in training, one per family in validation/test |
| Training complexity buckets | 6 two-family / 8 three-family / 6 four-or-five-family |
| Pairwise comparisons | 1,770 passed; 896 cross-split |
| Exact fingerprints | 60 unique centerlines and 60 unique coordinate fingerprints |
| Lineage leaks / independence conflicts | None |
| Native replay | All 60 passed; 600 artifacts byte-identical |
| Per-track checksum verification | 660 files, including 60 validation reports |
| Composite repetition <.65 | 28/30 |
| Preflight versus publication differences | None |

Before the full release, a specialist and an asymmetric composite were published
to a temporary development subset. Both matched preflight and replayed 20 artifacts
exactly. An intentional interruption after atomic composite-bundle publication but
before the manifest checkpoint recovered that same bundle without changing any
file. [Subset test evidence](../generated_maps/phase5_3_publication/subset_test_results.json).

Candidate evidence stays separate: **17 rejected preparations**, **74 valid but
unselected candidates**, and **60 published selected-candidate ledger entries**.
The original 151-candidate pool, protocol, calibration and vehicle snapshot are
archived with the release. Completed resume verifies archived inputs and is
read-only; changing the plan or native recipe is rejected.

The release includes PNG/PGM occupancy, ROS map YAML, native generation YAML,
centerline/wall/profile CSVs, metadata/evaluation files, actual solved parameters,
all manifests and path lists, selection evidence, environment and SHA-256 coverage.
Physical drivability remains unassessed and difficulty unrated.

## Visualizations and review flags

There are 21 PNG/SVG visualization pairs: the full gallery, five specialist-family
galleries, composite gallery, scale galleries, split galleries, geometric/curvature
and width distributions, maneuver-exposure matrix, signed-curvature examples,
repetition/active-curvature summary and normalized similarity matrix. All layout
galleries share the same metric axes.

The high-repetition exceptions are **`train_composite_03`** and
**`train_composite_06`**. Nine composites fall below a review-only active-curvature
threshold of 25%: `train_composite_02`, `05`, `07`, `08`, `16`, `19`, `20`,
`test_composite_05` and `test_composite_06`. Their active exposures range from
14.7% to 24.1%; all match preflight. They were flagged, not rejected or replaced.
[Exact review values](../datasets/phase5_v2/review_flags.json).

Primary annotation coverage includes genuine primary straights and is separate
from active curvature. Low repetition and policy-based geometric independence do
not establish physical difficulty or held-out topology generalization. Clearance
is sampled, widths remain mostly uniform, and environment-dependent replay
compatibility is limited to the recorded software versions.

## Tests, preservation and changed files

**The complete offline suite passed: 474 passed, 5 skipped in 291.81 s.** It was
run once after publication, with simulator-dependent tests excluded. The result is
recorded in [release_tests.json](../datasets/phase5_v2/release_tests.json). The new
checks cover frozen-plan/native agreement, all selected pairwise constraints,
tamper rejection, and read-only completed resume using archived inputs.

Changed code: `research_dataset.py` (selected publication and audit hook),
`research_selection_plan.py` (frozen plan verification),
`generate_research_dataset.py` (explicit commands), `plot_research_dataset.py`
(V2 repetition/active plots), and `test_research_publication_v2.py`. The dataset
and this report are new artifacts. V1 and all previous pilots/preflights are
preserved. No simulator access, training, new geometry, parameter tuning, commit
or push was performed.

Release sealing verified **2,170 protected prior files unchanged** and
**881 release-wide SHA-256 entries**. The final `SHA256SUMS` covers every release file except itself.
Stopped after publication and verification.
