# Phase 5.2C — reliability improved; V2 still not ready

**60/72 geometric passes, versus 5/36 in the same Phase 5.2B categories.**
Composites improved from **1/24 to 36/48**; chicanes/S-curves from **4/12 to 24/24**.
**15/18 categories meet the initial target of two valid, independent configurations.**
No formal dataset-generation attempt is justified yet.

[Concise CSV](../generated_maps/phase5_2c_readiness/summary.csv) · [Summary JSON](../generated_maps/phase5_2c_readiness/summary.json) · [Full evidence and native recipes](../generated_maps/phase5_2c_readiness/readiness.json) · [Original failure diagnosis](../generated_maps/phase5_2c_readiness/failure_diagnosis.json)

## Readiness table

Each cell is **original passes / 2 → improved passes / 4 (independent count)**.
Independent count is the largest subset of successful configurations whose every
pair passes the unchanged independence policy. Original and revised sample sizes
and configurations differ; these are screening results, not estimated population
success rates.

| Category | Short | Medium | Long |
|---|---|---|---|
| Composite, 2 families | 0/2 → 4/4 (2) | 0/2 → 4/4 (3) | 0/2 → 4/4 (2) |
| Composite, 3 families | 0/2 → 4/4 (4) | 0/2 → 4/4 (4) | 0/2 → 4/4 (4) |
| Composite, 4 families | 0/2 → 3/4 (2) | **0/2 → 0/4 (0)** | 0/2 → 4/4 (2) |
| Composite, 5 families | 0/2 → 3/4 (2) | **1/2 → 0/4 (0)** | **0/2 → 2/4 (1)** |
| Chicane | 2/2 → 4/4 (4) | 0/2 → 4/4 (4) | 0/2 → 4/4 (2) |
| S-curve | 0/2 → 4/4 (4) | 0/2 → 4/4 (4) | 2/2 → 4/4 (3) |

## Diagnosis and design changes

The saved 33 failures comprise **24 bounded-closure failures and nine coverage
failures**. Necessary-condition checks identify fixed budget violations in **29/33**:

- All nine coverage failures have too little requested primary source length for
  the declared lap and exposure floor; changing closure initializations cannot fix them.
- Eighteen closure failures cannot cancel their fixed displacement using the
  available gap length/headings. Scalar projection certificates record the required
  displacement and maximum possible contribution of remaining straight length.
- Four inventories exceed the lap even with minimum supporting geometry. Two of
  these also fail the displacement bound, so these counts overlap.
- Thus 20/24 closure failures have a budget certificate; four remain unresolved by
  these necessary checks. No claim of global infeasibility is made for those four.

The diagnostic groups each failure by family, scale, construction, reason, source
coverage, heading deficit and minimum support budget. It reuses the existing motion
model and scalar bounds; it is not a replacement closure solver.

The revised composite design reuses Phase 5's existing `controlled_halfturn.v1`
assembly, combining the fixed technical vocabulary reviewed in Phases 3B/4B with
Phase 5.1/5.2B alternating U-turns and opposing features. Each explicitly requested
half-lap ends with net heading pi and is assembled twice using the unchanged native
method. Its lap length is allocated before geometry construction, eliminating the
old impossible full-ring closure budgets. Two-family inventories contain straight
and hairpin maneuvers; three add chicane or S-curve; four contain both; five add
opposed sustained sweepers. Different counts, ordering, severity and straight
lengths produce the four deterministic configurations. Corner radii never grow
with lap length. Adjustable/supporting gaps retain their supporting annotations.

Accepted composites have **92.96–98.04% primary annotation coverage**, **1.96–7.04%
supporting geometry**, and **27.63–84.57% active-curvature exposure**. These are
separate measurements: primary annotation coverage includes genuine requested
straights. The per-family 2.5–78% exposure bounds remain enforced.

Chicane and S-curve specialists reuse the proven opposing-maneuver ring. Counts now
follow physical maneuver length and a reserved support budget, rather than a count
that leaves long chicane laps mostly supporting geometry or overfills short
S-curve laps. Fixed supporting angles and shorter supporting ramps retain all
curvature-rate and clearance checks. Chicane radii stay 2–5 m with 1.5–4 m lateral
displacement; S-curve radii stay 3–8 m with 45–90-degree opposing bends.

## Independence and remaining failures

The original three near-duplicate and two ambiguous pairs were caused by similarly
shaped straight rings, a shared short-sweeper turn word and a nearly regular
chicane scaffold. Replacements vary straight corner count (4–7), signed sweeper
ordering, opposing-window count and severity, and physical length allocation.
Targeted geometric tests validate independent low/high configuration pairs for
short/medium/long straights and short sweepers; this is eight additional geometry
preparations in tests, separate from the 72-draw readiness table.

Thresholds and ambiguity rejection are unchanged. Among the 60 successful screen
candidates, **24 pairs remain near-duplicates and one pair is ambiguous**. Nineteen
flags are within categories, and six are between categories. They are retained as
flags, not counted as independent configurations. The category targets therefore
do not establish that all category selections can be combined into an independent
formal allocation.

The twelve remaining geometry failures are **ten centerline self-intersections and
two variable-boundary self-intersections**. No revised screen candidate fails
closure convergence or primary/supporting coverage. Remaining blockers are:

- Four-family medium: all four self-intersect.
- Five-family medium: all four self-intersect; this category regressed from its
  single successful Phase 5.2B draw.
- Five-family long: two valid, two intersecting; the valid pair is near-duplicate
  (shape distance .02497, relative length .14063, relative sustained radius .16965).

The half-turn construction enforces symmetry and repeats motifs. High annotation
coverage alone does not establish useful driving diversity. Four deterministic
configurations per category are insufficient to establish robust success rates,
full allocation independence or physical drivability. No additional tuning was
performed after this screen.

## Checks, files and scope

**39 targeted tests passed, 58 deselected** in 36.58 s: resolved half-turn budgets,
family counts, physical severity, support budgets, native recipe roundtrip,
independence examples, V2 specification contracts and frozen V1 candidate identities.
Existing geometry, width, footprint and raster checks ran for every preparation.
No bundles were published and no full-dataset replay or audit was executed.
Checksums verify **1,508 existing V1 and pilot artifacts unchanged**.

Modified files:

- `src/map_editor/services/research_design.py`: select the new V2 templates; V1 stays unchanged.
- `src/map_editor/services/research_reliable_design.py`: new compact template layer using existing assembly methods.
- `scripts/screen_research_reliability.py`: saved-budget diagnosis, immutable four-configuration screen and independence report.
- `tests/test_research_dataset.py`: targeted template and independence tests.
- `docs/phase5_2c_results.md`: this report.

All new evidence is under `generated_maps/phase5_2c_readiness`. Coordinate CSVs are
review artifacts, not a dataset release. Native recipe interpreters, geometry
primitives, frozen policy, V1 and accepted pilots remain unchanged. No simulator,
controller, broad regression suite, 60-track generation, commit or push.
**Stopped after the readiness screen.**
