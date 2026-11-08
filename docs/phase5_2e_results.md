# Phase 5.2E — allocation and repetition goals met

**60/60 slots filled; 28/30 composites have repetition below .65.** The two
remaining composites have repetition above .95. This is one offline preflight;
no map bundles or formal dataset were published.

[Ten-layout gallery](../generated_maps/phase5_2e_preflight/composite_gallery.png) · [Selected metrics CSV](../generated_maps/phase5_2e_preflight/selected_metrics.csv) · [Summary JSON](../generated_maps/phase5_2e_preflight/summary.json) · [Full pool, conflicts and selection log](../generated_maps/phase5_2e_preflight/preflight.json)

| Measure | Phase 5.2D | Phase 5.2E |
|---|---:|---:|
| Filled allocation | 55/60 | **60/60** |
| Specialists | 30/30 | 30/30 |
| Composites | 25/30 | **30/30** |
| Composite repetition <.65 | 6 | **28** |
| Composite repetition >.95 | 19 | **2** |
| Preparations | 85 | 151 |
| Preparation rejections | 6 | 17 |

The phases use different candidate budgets. The larger pool and new construction
library both contribute; the same-pool selection comparison below isolates the
selection contribution. These are deterministic screening counts, not estimated
generation success rates.

## Templates and truthful composition

The six successful Phase 5.2D profiles remain available. Additional asymmetric
arrangements regroup opposing turns and vary actual corner counts and turn words.
Two-/three-family short and medium circuits now adapt Phase 3B technical patterns;
long versions adapt the Phase 4B clusters and designated supporting turns.

Two-family templates contain technical corners and fixed primary straights.
Three-family templates add meaningful chicane/S-curve content or preserve the
already meaningful compact kink family. Converting a shallow kink to a corner
changes its physical angle to at least 40 degrees and balances the signed turn
word; it does not simply change the label. Medium variants derived from short
patterns add actual opposing technical corners and unequal fixed approaches.
Corner radii never grow to fill lap length. Original fixed primary straights remain
requested geometry, while all solved gaps and supporting turns retain supporting
roles. All family-exposure, radius, width, clearance and curvature-rate checks remain.

The selected composites represent **eight measured primary-family combinations**.
The gallery uses common approximately 127 m square metric axes and emphasizes
asymmetric shapes. The unchanged compact four-/five-family half-turn templates
supply the two high-repetition exceptions, `train_composite_03` and
`train_composite_06`.

## Bounded allocation selection

The pool protocol was fixed before execution: two initial candidates per specialist,
three per composite; at most three/five respectively, two extension rounds and an
overall cap of 180 preparations. Additional attempts are reserved for unfilled or
quality-constrained slots. Actual work was **150 initial preparations plus one
third hairpin candidate** whose first two failed geometry. No extra composite
attempts or post-preflight geometry tuning were performed.

Selection ranks scarcity using currently compatible choices and within-slot
pairwise-independent option counts. A depth-two repair can displace up to two
selected candidates and rehome their slots. Three bounded passes and 5,000 node
visits per selection call limit work. Equal-coverage choices maximize the number
of composites below .65, then minimize their total repetition. Every candidate
stays in its originally assigned split, scale and lineage; no slot was reassigned.

On the **same final pool**, original slot-order greedy selection fills **59/60**;
scarcity-first selection fills **60/60**. Four quality-repair transactions substitute
nine candidate choices at equal coverage. Coverage-repair functionality is tested,
but final-pool coverage did not require a committed coverage repair. The final
selector used 357 node visits; both selection runs together used 713. Replaying
the final selection from saved pools and conflicts reproduced the complete result.
This is a bounded heuristic, not an optimality proof or an external optimizer.

## Conflicts, coverage and measured fractions

Of 151 preparations, **134 validated and 17 were rejected**: eleven bounded-closure
failures, three centerline intersections, two boundary intersections and one
meaningful-family exposure failure. All rejected recipes and reasons are retained.

The valid pool contains **65 independence conflicts between different slots**:
58 near-duplicate and seven ambiguous pairs. Forty are cross-split conflicts.
The selected 60 contain **zero conflicts** across all **1,770 pairs**, including
**896 cross-split pairs**. Both centerline and coordinate fingerprints have 60
unique values. Frozen independence thresholds and ambiguity rejection are unchanged.

All five previously unfilled slots are recovered. Split counts are exactly
**40 train / 8 validation / 12 test**, and scales **18 short / 22 medium / 20 long**;
all specialist and composite complexity quotas, lineage, seed and measured-scale
checks passed.

| Selected composite measure | Minimum | Median | Maximum |
|---|---:|---:|---:|
| Primary annotation coverage | 61.8% | 68.0% | 96.9% |
| Supporting geometry | 3.1% | 32.0% | 38.2% |
| Active-curvature exposure | 14.7% | 28.8% | 72.8% |
| Periodic repetition | .000 | .076 | 1.000 |

Primary coverage includes genuine requested straights. Active curvature is measured
separately and is lower in some longer technical/straight layouts. Low repetition
therefore does not imply uniformly greater driving demand, proven difficulty, or
independent topology. Independence here means passing the frozen geometric policy.

## Verification, changes and scope

**14 targeted tests passed, 99 deselected** in 33.03 s: two-blocker rehoming,
equal-coverage quality swaps, independent-option scarcity, deterministic bounds,
conflict rejection, technical family/heading budgets, native recipe roundtrip,
allocation lineage and all frozen V1 candidate identities. The selector replay and
all 60 selected lineage/seed/scale checks also passed. Checksums verify **1,889
protected V1 and prior pilot/readiness artifacts unchanged**.

Changed files: `research_reliable_design.py` (asymmetric technical library),
`research_design.py` (V2 composite selection), `research_pool_selection.py` (bounded
pure-Python selection), `preflight_composite_diversity.py` (pool preflight/gallery),
`test_research_pool_selection.py`, `test_research_dataset.py`, and this report.
No geometry primitive, closure solver, V1 interpreter or independence policy changed.

**Both requested preflight goals are met.** A formal attempt would need to retain
this tested pool-selection procedure; the existing publication path was not changed
or exercised. Native dataset replay, publication validation and physical performance
remain outside this preflight. No full suite, simulator/controller evaluation,
formal dataset publication, commit or push. Stopped after the preflight.
