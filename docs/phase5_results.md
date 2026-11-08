# Phase 5 results and review guide

The formal dataset is complete: **60 accepted physical centerline layouts**, with
all requested family, complexity, split and measured scale quotas verified.
Review the [60-track gallery](../datasets/phase5_v1/plots/overview.png),
[master manifest](../datasets/phase5_v1/manifest.json),
[integrity audit](../datasets/phase5_v1/integrity_report.json), and
[dataset contract](research_dataset.md).

Work started from clean `main` HEAD **`ec4b1c9`** (`extended tracks`). This phase
used only map-edit and its saved resolved vehicle profile. No external simulator
checkout was accessed, no simulator/controller/training work was run, and no
commit or push was made. Existing generator source, versions, schemas, artifacts
and recipe interpreters remain unchanged. Work stops at Phase 5.

## Allocation and completeness

The [versioned root recipe](phase5_allocation.json) fixed all 60 joint
family/split/scale slots before formal generation, with root seed **20261108**
and at most **24 candidates per slot**. Its canonical specification SHA-256 is
`6472ad03f8de21426b721144f37f44f6cbe637c6b9e0054b328dffd6ceec4d84`.
The release copies this recipe and its frozen calibration/readiness evidence.

| Split | Specialists | Composites | Total | Short [70,140) m | Medium [140,260) m | Long [260,450] m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | 20 | 20 | 40 | 12 | 15 | 13 |
| Validation | 5 | 3 | 8 | 2 | 3 | 3 |
| Test | 5 | 7 | 12 | 4 | 4 | 4 |
| Total | 30 | 30 | **60** | **18** | **22** | **20** |

Specialist joint allocation, with each cell giving **short / medium / long**:

| Target family | Train | Validation | Test | Total |
| --- | --- | --- | --- | ---: |
| Straight | 1 / 1 / 2 | 1 / 0 / 0 | 1 / 0 / 0 | 6 |
| Hairpin | 1 / 2 / 1 | 0 / 1 / 0 | 0 / 0 / 1 | 6 |
| Sweeper | 1 / 1 / 2 | 0 / 0 / 1 | 0 / 1 / 0 | 6 |
| Chicane | 2 / 1 / 1 | 0 / 1 / 0 | 1 / 0 / 0 | 6 |
| S-curve | 1 / 2 / 1 | 0 / 0 / 1 | 0 / 0 / 1 | 6 |

Each family has four training specialists and one each in validation/test.
Training composites have exactly **6 two-family, 8 three-family, 3 four-family
and 3 five-family** tracks: the requested 6/8/6 grouping. Validation composite
complexities are **2, 3, 5**; test complexities are **2, 3, 4, 5, 2, 3, 5**.
Their scale counts are train **6/8/6**, validation **1/1/1**, test **2/3/2**.
Every family has short, medium and long coverage globally.

The root and master explicitly record `complete: true`, with no incomplete
requests. Stable relative path lists are [train](../datasets/phase5_v1/train_maps.txt),
[validation](../datasets/phase5_v1/validation_maps.txt),
[test](../datasets/phase5_v1/test_maps.txt) and
[all maps](../datasets/phase5_v1/all_maps.txt). The
[release README](../datasets/phase5_v1/README.md) explains relocation and loading.

## Specialist readiness and measured intent

The new native generator is **`map_editor.research_tracks.v1`**, using existing
parametric maneuvers, technical corner geometry, variable corridor widths and
bounded supporting-turn closure. Phase 2 recipes retain their original behavior.
The [readiness pilot](phase5_readiness.json) passed **15/15 family × scale cases**
before formal generation. These development cases are not extra dataset entries.

Every accepted specialist has only its target family in primary windows; all
maneuvers pass existing measured classification. Supporting geometry is labeled
separately. Non-straight specialists must also have ≥50% genuinely curved length
within target windows. The primary exposure is measured, not a template name.

| Target | Required minimum exposure | Achieved range across six specialists |
| --- | ---: | ---: |
| Straight | 70% | 72.60–79.01% |
| Hairpin | 70% | 74.86–80.86% |
| Sweeper | 80% | 83.31–86.28% |
| Chicane | 60% | 70.11–79.86% |
| S-curve | 65% | 70.25–81.71% |

Primary hairpins satisfy the measured 150–210 degree class; sweeper specialist
windows have radius ≥5 m and length ≥5 m. Short, medium and long specialists
vary source lengths, radii, headings, feature counts/order and connector
geometry. Straight, sweeper and opposing-turn templates use four/five/six-feature
rings. Hairpins use independently parameterized unequal two-hairpin routes.
Their shared broad route shape is a real limitation, visible in the gallery.

Composite complexity counts actual primary annotation families, including
technical `corner` where requested; connector turns do not increase complexity.
Five-family composites contain all five canonical specialist families. Every
primary composite family has ≥2.5% lap exposure and ≤78%, with total primary
coverage ≥60%. The six five-family circuits explicitly retain a controlled
halfturn motif. The other **54 layouts are asymmetric**. Native topology
metadata has **26 distinct descriptors**; those descriptors include inventory
size and do not represent 26 proven independent topology classes.

## Generation and rejection statistics

Formal publication evaluated **88 outer candidates**: **60 accepted (68.2%)**
and **28 rejected (31.8%)**. Every slot succeeded within **six attempts**, below
the 24-attempt limit. No quotas, acceptance limits, duplication thresholds or
split assignments were relaxed after formal generation began.

| Rejection stage | Count | Reason |
| --- | ---: | --- |
| Independence | 23 | Near duplicate under frozen policy |
| Independence | 2 | Ambiguous independence under frozen policy |
| Geometry | 1 | No valid bounded inner candidate for an S-curve specialist |
| Geometry | 2 | Requested variable corridor wall self-intersection |

The [candidate ledger](../datasets/phase5_v1/evidence) preserves all 88 attempt
records, including native requests, seeds, reasons and inner decision journals
where available. Outer counts differ from the internal placement proposals:
each bounded-turn request ranks three deterministic proposals, whereas an
explicit halfturn request has one. Valid unselected proposals are retained in
native metadata and per-track validation reports.

Development explored closure feasibility before the frozen release, including
rejecting ineffective connector arrangements. These exploratory outputs stay
under ignored `generated_maps`; they are not silently included in the formal
88-candidate acceptance rate. The formal ledger, frozen evidence and recipe
fully define this release's process.

## Independence and split integrity

Both width-independent fingerprint systems give **60 distinct centerlines**.
The final audit evaluates all **1,770 accepted pairs**, including every
cross-split pair: zero exact duplicates, zero near duplicates, zero ambiguous
pairs, zero parent-lineage leakage and zero near-group leakage under the frozen
policy. Every split was assigned before its final candidate was published.

[Development calibration](phase5_calibration.json) uses the prior Phase 4B pilot,
its actual width-only duplicates and representation controls. No formal held-out
candidate was used to select thresholds. Translation, rotation, reflection,
reversal, seam shifts and width changes are recognized by the shape diagnostic.
The [contract](research_dataset.md#development-calibrated-independence-policy)
gives every numeric threshold and relative-difference definition.

Near duplicates require close normalized shape (<0.055), physical length (<15%),
sustained radius (<20%) and primary-family exposure L1 (<0.25) simultaneously.
A second ambiguous band rejects shape <0.085 with close length (<8%), p95
curvature (<12%), exposure (<0.15) and corner count (difference ≤1).
Both categories reject across the entire dataset, even within one split.

Normalized shape distances span **0.00842–0.53405**. Low shape distance alone can
coexist with materially different physical scale or severity. Thus these are
**60 physical layouts independent under this documented policy**, not a claim of
60 unrelated normalized morphologies. The policy deliberately permits shared
broad route shapes at different physical scales. No width-only, mirrored,
reversed, seam-shifted or raster-only variant is counted as a new track.

Parent IDs denote independent preallocated blueprints and all their attempts,
not an entire family. Broad topology families are shared between splits;
**no explicit topology family is held out**. This release supports instance
transfer within those families. A future shape-only or topology-held-out study
should define a separate split condition before evaluating policies.

## Geometric coverage

[Machine-readable analysis](phase5_analysis.json) includes all track statistics,
aggregate marginals, split marginals, joint rows and all four existing spatial
analysis scales. Default significant-turn analysis uses sigma **0.4 m** with
≤0.1 m resampling. A significant turn requires |κ| >0.025/m, region length
≥0.6 m and accumulated heading ≥15 degrees. These geometric regions are
separate from maneuver windows. Whole-lap sustained-radius statistics include
supporting bends; they are not the minimum radius of primary hairpins/sweepers.

| Metric | Dataset range |
| --- | ---: |
| Exported lap length | 77.63–440.86 m |
| Significant turn count | 1–18 |
| Significant turns per 100 m | 0.31–16.61 |
| Minimum sustained radius | 1.81–7.57 m |
| p95 absolute curvature | 0.0158–0.5253 /m |
| Longest near-straight | 1.40–229.89 m |
| Cyclic curvature reversals | 0–12 |
| Left fraction of absolute turning | 0.689–1.000 |
| Primary coverage | 65.39–98.46% |
| Supporting coverage | 1.54–34.61% |
| Active-curvature source fraction | 7.93–96.36% |
| Minimum vector normal width | 1.412–1.831 m |
| Mean vector normal width | 1.434–1.831 m |
| Width standard deviation | approximately 0–0.04884 m |
| Width variance | approximately 0–0.002386 m² |
| Halfturn asymmetry residual | approximately 0–22.39 m |

**33 tracks have variable widths**, with independent smooth left/right profiles;
27 are nominally uniform. Sub-micrometer measured width variation in uniform
tracks comes from quantized wall geometry. Width differences are intentionally
modest in this release and should not be described as broad bottleneck diversity.
No auxiliary width pairs are counted among the 60.

| Split | Mean lap m | Mean turns | Mean sustained min radius m | Mean p95 absolute κ /m | Mean width m | Mean active fraction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | 228.13 | 8.175 | 3.693 | 0.2078 | 1.626 | 0.601 |
| Validation | 258.93 | 8.625 | 3.628 | 0.2207 | 1.659 | 0.648 |
| Test | 217.70 | 9.000 | 3.718 | 0.2255 | 1.594 | 0.566 |

All splits span the requested scale bins. Length differs by finite-sample
allocation: validation is about 31 m longer on average than training and test
about 10 m shorter. Mean widths differ by up to 0.065 m. These are descriptive
imbalances, not evidence of perfect distribution matching. The main whole-
dataset joint Pearson correlations are **−0.174** for length versus turn count
and **−0.027** for sustained radius versus mean width. Plots also compare primary
family with p95 curvature; family conditioning changes severity, as intended.

All circuits wind counterclockwise and left-turn exposure is biased. Opposing
features vary initial direction and local reversals, but travel directions are
not balanced at the whole-lap level. Broad route motifs are reused and some
geometric extremes depend on family. These limits should be retained when
interpreting future generalization results; split labels are not difficulty
labels.

## Validation, native replay and runtime

All accepted tracks pass offline source/quantized closure, +2π winding, G2 joins,
measured maneuver classification, radius/curvature-rate and saved-profile
steering geometry, centerline/wall intersections, global boundary clearance,
nonlocal gap, periodic variable-width consistency, sampled rectangular vehicle
clearance, corridor occupancy and full-area raster footprint checks.

Across the 60 bundles:

- Maximum source join residuals: **2.13e-9 m** position, **5.37e-11 rad** heading,
  **1.12e-16 /m** curvature.
- Maximum source curvature rate: **1.5 /m²**, within the configured 2.0 /m² bound.
- **117,342 retained poses** pass vehicle and raster footprint checks, with
  0.02 m footprint margin; minimum raster normal width is **1.27784 m**.
- Actual serialized CSVs, closed walls, winding, width sums, directional finish,
  named `grid_1` spawn and its full raster footprint pass independently.
  PNG/PGM occupancy pixels match exactly.
- Periodic maneuver windows partition each lap; sample evaluation CSVs retain
  family, role, ID and distance to the next annotation boundary.
- **60 native recipe reloads compare 10 deterministic artifacts each byte for
  byte: 600 exact comparisons.** Master checksums cover **660 files**, including
  each validation report. Candidate evidence is separately hashed.

A [second fresh root-recipe run](phase5_reproduction.json) reproduced the same 60 IDs, accepted attempt
numbers and **all 660 bundle SHA-256 hashes**, with the same 88-candidate ledger
outcomes. The final publication is that fresh run. Original development outputs
are preserved under ignored `generated_maps`. This verifies layout/export
reproducibility in the current local environment; it is not a portability promise
across different numerical/raster library versions. The [local environment](phase5_environment.json) records the exact installed versions.

[Runtime profiling](phase5_runtime.json) for that full run records **217.84 s**:
**81.79 s** summed successful preparation, **24.45 s** export, **83.76 s** native
replay, and **196.26 s** summed outer-candidate time. The remainder includes
checkpointing and the final serialized/pairwise audit. Failed partial preparation
is included in outer-candidate time, not successful-preparation totals. Plotting,
readiness development, analysis and the test suite are separate. Runtime is a
local wall-clock observation, not a hardware-independent benchmark.

The saved F110 profile remains uncalibrated (0.5 m length, 0.27 m width,
0.3302 m wheelbase). No velocity, friction, dynamic steering-rate feasibility,
controller outcome or continuous swept vehicle certificate is inferred.
Sampled footprint checks cannot certify clearance between retained poses.
Physical drivability stays **`unassessed`**, driving difficulty **`unrated`**,
and integration **`not_run`** in every report. Annotations are evaluation-only;
no policy observation or training interface was added.

## Visualization gallery

Every figure is available as PNG and SVG in the
[plot directory](../datasets/phase5_v1/plots). All layout galleries use identical
**202 m × 202 m axes**, centering geometry without changing its physical size.
Representative curvature panels share 0–450 m horizontal and ±0.8/m vertical
axes. Statistical panels use physical units and common split-comparison axes.

| View | Figures |
| --- | --- |
| All layouts | [60-track overview](../datasets/phase5_v1/plots/overview.png) |
| Specialist families | [Straight](../datasets/phase5_v1/plots/specialist_straight.png), [hairpin](../datasets/phase5_v1/plots/specialist_hairpin.png), [sweeper](../datasets/phase5_v1/plots/specialist_sweeper.png), [chicane](../datasets/phase5_v1/plots/specialist_chicane.png), [S-curve](../datasets/phase5_v1/plots/specialist_s_curve.png) |
| Composite complexity | [All composites ordered by family count](../datasets/phase5_v1/plots/composites.png) |
| Physical scale | [Short](../datasets/phase5_v1/plots/scale_short.png), [medium](../datasets/phase5_v1/plots/scale_medium.png), [long](../datasets/phase5_v1/plots/scale_long.png) |
| Split galleries | [Train](../datasets/phase5_v1/plots/split_train.png), [validation](../datasets/phase5_v1/plots/split_validation.png), [test](../datasets/phase5_v1/plots/split_test.png) |
| Curvature, density and physical geometry | [Distributions](../datasets/phase5_v1/plots/geometric_distributions.png), [curvature profiles](../datasets/phase5_v1/plots/curvature_examples.png) |
| Corridor widths | [Width distributions](../datasets/phase5_v1/plots/width_distributions.png) |
| Maneuver distribution | [Exposure heatmap](../datasets/phase5_v1/plots/maneuver_exposure.png) |
| Independence diagnostics | [Shape similarity matrix](../datasets/phase5_v1/plots/similarity_matrix.png) |
| Joint relationships | [Length/corners, radius/width, family/severity](../datasets/phase5_v1/plots/joint_relationships.png) |
| Split distributions | [Train/validation/test comparisons](../datasets/phase5_v1/plots/split_comparisons.png) |

## Tests and changed files

The offline command is:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q --offline-geometry
```

Baseline: **358 passed, 5 skipped**. Phase 5 adds dataset regression coverage for
joint allocation, invalid quotas, seeds, exact scale endpoints, readiness,
transformation-invariant screening, ambiguous pairs, all 60 identities and
1,770 pairs, split manifests/path resolution, lineage leakage, measured
specialists, composite complexity, hashes, manifest tampering, native replay,
partial recovery, orphan adoption and accepted-artifact immutability. Fresh
processes forbid external checkout access and subprocess launches during replay.
The five external-checkout tests are skipped explicitly by offline mode and
are reported separately from passing geometric checks.

Final full offline suite: **406 passed, 5 skipped in 155.62 s**. All 48
Phase 5 cases are included. A focused final manifest-tamper/hash check also
passed **2 tests in 3.76 s** after strengthening native/manifest identity checks.

The five skips are three parameterized external map-loading/finish/lidar/
collision integration cases, the external vehicle-source/advisory test and
the new-backend external bundle-loading test. None was executed.
The final audit passes all 60 bundles and all 1,770 pairs; the release
`SHA256SUMS` verifies **806 files (241,038,867 bytes before the checksum index)**,
including all evidence and figures. All 40 plot files reproduced byte for byte.

New services: `research_spec.py`, `research_design.py`, `research_tracks.py`,
`dataset_spec.py`, `dataset_diversity.py`, `research_dataset.py`,
`dataset_bundle_audit.py`, `dataset_analysis.py` under `src/map_editor/services`.
New scripts: `prepare_research_readiness.py`, `generate_research_dataset.py`,
`analyze_research_dataset.py`, `plot_research_dataset.py`.
New tests: `tests/test_research_dataset.py`.
New evidence/docs: root allocation, calibration, readiness, runtime and analysis
JSONs, environment and reproduction evidence; this report; the research dataset contract; and the complete portable
`datasets/phase5_v1` release. Existing README and metadata documentation gain
Phase 5 links. No previous generator implementation or pilot artifact changes.

## Limitations and follow-up recommendations

This release is a bounded geometric research dataset with shared broad topology
families, physical-scale-aware independence, mild variable-width variation,
counterclockwise global direction, family-dependent severity and finite-sample
split differences. Development calibration is transparent but small and does
not certify statistical independence or independent real-world track origins.

For a separately authorized future phase, consider a human-reviewed shape-only
holdout, independently designed hairpin topologies, clockwise scaffold allocation
without counting mirrored/reversed duplicates, stronger width/bottleneck
coverage, and dynamic/continuous swept-footprint validation. Simulator and
learning experiments require their own future work; none was performed here.
