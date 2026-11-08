# Phase 5.2D — categories repaired; allocation still incomplete

**The three focused categories pass locally. The single dry run filled 55/60 slots;
formal V2 generation is not justified yet.** No map bundles were published.

[Six-layout gallery](../generated_maps/phase5_2d_preflight/focus_gallery.png) · [Metrics CSV](../generated_maps/phase5_2d_preflight/focus_metrics.csv) · [Preflight summary](../generated_maps/phase5_2d_preflight/preflight_summary.json) · [Failures by category](../generated_maps/phase5_2d_preflight/preflight_categories.csv) · [Full evidence](../generated_maps/phase5_2d_preflight/preflight.json)

## Focused corrections

| Category | Phase 5.2C valid / tried | Previous independent | New valid / tried | New independent |
|---|---:|---:|---:|---:|
| Medium, four families | 0/4 | 0 | 2/2 | 2 |
| Medium, five families | 0/4 | 0 | 2/3 | 2 |
| Long, five families | 2/4 | 1 | 2/2 | 2 |

Only seven configurations were prepared, stopping each category upon finding two
eligible independent layouts. All configurations in a category used the same
closure seed; inventory and turn-word changes supplied the variation. The sole
rejection was a five-family profile inheriting a four-family count declaration.
That declaration was corrected and covered by a targeted test; the profile was
not promoted or retried. The six successful profiles alone were promoted.

Inspection of saved failures located crossings between the first half's opposing
maneuver path and the second half's primary straight. In the five-family case,
the swept segment itself crosses that return straight. Exact half-turn closure
therefore concealed a routing problem. [Diagnostic crossing locations](../generated_maps/phase5_2d_preflight/failure_diagnosis.json).

The replacements use the existing asymmetric bounded-gap closure and proven
Phase 5.2B inventories. The four-family pair adds a useful S-curve to the hairpin
approach in one configuration and changes the U-turn/corner angle balance in the
other. The medium five-family pair contrasts an irregular technical-corner flow
with a compact hairpin/sweeper arrangement obtained by removing/reordering opposing
windows. The long pair adds an approach S-curve versus a balanced 180-degree
hairpin and 90-degree opposing sweeper word. Counts and turn sequences change;
primary radii are never scaled to fill lap length.

Literal primary families are measured, not inferred from labels: one medium
five-family inventory uses corner/chicane/sweeper/S-curve/straight; the other uses
hairpin/chicane/sweeper/S-curve/straight. Both contain five meaningfully exposed
families. Four-family layouts contain corner/hairpin/S-curve/straight.

### Measured geometry and diversity

| Profile | Lap m | Primary | Active curvature | Significant turns | Family transitions | Repetition |
|---|---:|---:|---:|---:|---:|---:|
| Four-medium 0 | 225 | 63.0% | 43.4% | 17 | 11 | .147 |
| Four-medium 1 | 210 | 62.4% | 41.3% | 15 | 11 | .106 |
| Five-medium 0 | 170 | 75.6% | 47.6% | 15 | 12 | .239 |
| Five-medium 2 | 250 | 63.9% | 48.6% | 15 | 12 | .242 |
| Five-long 0 | 350 | 63.6% | 52.7% | 25 | 17 | .010 |
| Five-long 1 | 330 | 64.9% | 53.2% | 23 | 16 | .197 |

Supporting fractions are **24.4–37.6%**. Requested primary straights occupy only
**10.7–27.6%** of the lap; none were expanded to manufacture coverage. Actual
primary geometry is declared before closure; solved gaps retain supporting roles.
Symmetry residuals are **10.3–40.7 m**, versus approximately zero for the prior
half-turn templates. Their previous periodic repetition was approximately 1.0.

Normalized shape distances within the selected pairs are **.119, .362 and .111**.
The unchanged frozen policy accepts all three pairs. All **360 comparisons**
against the 60 accepted Phase 5.2C configurations, including other categories,
and all **12 comparisons between new categories** passed. Nearest old-C shape
distances are .194–.344. These measurements remove translation, rotation, scale,
reflection, reversed traversal and seam placement.

Before screening, technical eligibility required repetition <.65, symmetry error
>1 m, active curvature >=35%, and primary-straight exposure <=30%, in addition to
unchanged primary >=60%, supporting <=40%, meaningful-family and safety limits.
The extra eligibility criteria also applied to affected slots during preflight.

## One 60-slot geometric preflight

The existing V2 allocation was used without publication. Every slot received one
initial candidate before any fallback; only unfilled slots received a second or
third candidate. The procedure used the current generator and a greedy allocation
order, with no search/selection optimizer. It is not a proof that 55 is the maximum
possible independent subset under other candidate choices or orderings.

| Round | Preparations | Filled this round | Geometry rejected | Independence rejected |
|---|---:|---:|---:|---:|
| Initial | 60 | 42 | 5 | 13 |
| Fallback 1 | 18 | 11 | 1 | 6 |
| Fallback 2 | 7 | 2 | 0 | 5 |
| **Total** | **85** | **55** | **6** | **24** |

All **30/30 specialists** filled: six each of straight, hairpin, sweeper, chicane
and S-curve. Composites filled **25/30**: two-family 6/9, three-family 11/11,
four-family 3/4, five-family 5/6. All scales and families are represented, but quotas
are incomplete:

| Allocation | Filled / required |
|---|---:|
| Training | 38/40 |
| Validation | 8/8 |
| Testing | 9/12 |
| Short | 16/18 |
| Medium | 20/22 |
| Long | 19/20 |

All 55 retained centerline and coordinate fingerprints are unique. All **1,485
retained pair comparisons**, including **718 cross-split comparisons**, passed
the frozen independence policy. There are no retained exact/approximate duplicate
or cross-split independence failures. Twenty-four candidate requests were rejected
by independence screening, producing 22 near-duplicate and four ambiguous pair
flags (some requests matched multiple retained layouts).

The five unfilled slots all produced valid geometry but could not supply another
independent member after the two allowed fallbacks:

- `train_composite_05`: two-family short, near-duplicate.
- `train_composite_12`: two-family medium, near-duplicate.
- `test_composite_01`: two-family short, near-duplicate across splits.
- `test_composite_03`: four-family medium, ambiguous/near-duplicate against training.
- `test_composite_07`: five-family long, near-duplicate against training/validation.

Thus the repaired categories have two local independent profiles, but medium
four-family and long five-family each need a third independent allocated member.
Medium five-family filled both allocated slots. The six geometry failures were
three centerline intersections, one variable-boundary intersection and two bounded
closure failures in hairpin/sweeper specialists; fallback recovered those slots.

Across retained composites, primary coverage is **62.4–98.0%**, supporting fraction
**2.0–37.6%**, and active exposure **26.8–81.7%**. **19/25 retained composites still
inherit the other Phase 5.2C half-turn templates and repetition above .95.** The
focused repairs do not establish irregular driving diversity for the full release.
These inherited repetitive categories were outside this correction's scope.

## Verification, files and recommendation

**Seven targeted tests passed** (six construction/selection/V1 compatibility tests,
plus one declaration regression). They cover physical ranges, full-turn heading,
family counts, strict source budgets, promoted-profile selection, recipe roundtrip,
all 60 V2 specification contracts and all frozen V1 candidate identities.
Existing geometry, width, clearance, footprint and raster checks ran during
preparation. No native dataset replay, simulator, controller or full suite ran.
Checksums confirm **1,860 protected V1 and existing pilot/readiness artifacts unchanged**.

Modified files:

- `research_reliable_design.py`: six explicit asymmetric arrangements and promotion of the six successful category profiles.
- `research_design.py`: select promoted profiles only for the three affected categories.
- `preflight_research_v2.py`: bounded screen, gallery, cross-category comparison and conditional single dry run.
- `test_research_dataset.py`: targeted construction, selection and declaration guards.
- `docs/phase5_2d_results.md`: this report.

**Recommendation: do not start formal V2 generation.** The current bounded strategy
fills 55/60, lacks sufficient independent profile breadth for five slots, and
retains substantial repetition outside the repaired categories. No additional
candidates, solver work, optimization, dataset release, commit or push followed
the preflight. Physical drivability remains unassessed.
