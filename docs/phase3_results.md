# Phase 3 results and review guide

Implemented from clean map-edit HEAD `d45004a` (`track gen`). The reference was
read-only `marl_race`, branch `physics-correctness`, commit
`8a4bddf97c6de7740263b962a74ae4ae88fec0da`. No reference changes, commits or pushes
were made. Phase 0–2 generator source, semantics, recipe versions and original
artifact replay remain unchanged.

The new backend is **`map_editor.composite_circuits.v1`**, template
**`block_and_bounded_return.v1`**. It declares `generation_mode: composite`
explicitly and retains metadata schema **1.0.0**. The
[composite contract](composite_circuits.md) documents ordered requests, ranges,
exposure/length constraints, solver bounds, periodic evaluation and identity.

## Eight accepted circuits

The completed pilot is in
[`examples/phase3_pilot/manifest.json`](../examples/phase3_pilot/manifest.json),
with its deterministic [pilot recipe](../examples/phase3_pilot/pilot_recipe.json).
It has exactly two two-family cases, two three-family cases, two five-family
cases, and two additional matched-order cases: **eight distinct layout
fingerprints**, not cyclic representations counted again.

Review the [overview](../examples/phase3_pilot/plots/overview.png). Each track has
an exportable PNG/SVG figure with full colored geometry, curvature, cyclic window
sequence, family exposure, a direct transition matrix including connectors, and
a projected primary-family order matrix whose connector bridges remain recorded.

| Circuit / plot | Layout | Primary families | Final lap (m) | Primary coverage | Family switches | Switches / 100 m |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [Two symmetric](../examples/phase3_pilot/plots/two_symmetric.png) | 2-block | 2 | 81.3748 | 58.231% | 4 | 4.916 |
| [Two asymmetric](../examples/phase3_pilot/plots/two_asymmetric.png) | bounded return | 2 | 93.1195 | 47.393% | 2 | 2.148 |
| [Three symmetric](../examples/phase3_pilot/plots/three_symmetric.png) | 2-block | 3 | 111.2236 | 63.147% | 6 | 5.395 |
| [Three asymmetric](../examples/phase3_pilot/plots/three_asymmetric.png) | bounded return | 3 | 138.4061 | 39.108% | 4 | 2.890 |
| [Five symmetric](../examples/phase3_pilot/plots/five_symmetric.png) | 2-block | 5 | 163.4896 | 90.825% | 10 | 6.117 |
| [Five asymmetric](../examples/phase3_pilot/plots/five_asymmetric.png) | bounded return | 5 | 199.6564 | 44.297% | 5 | 2.504 |
| [Matched order A](../examples/phase3_pilot/plots/matched_order_a.png) | 2-block | 5 | 148.8793 | 88.447% | 12 | 8.060 |
| [Matched order B](../examples/phase3_pilot/plots/matched_order_b.png) | 2-block | 5 | 148.8793 | 88.447% | 12 | 8.060 |

The two-family inventories combine straight/chicane and straight/hairpin.
The three-family inventories combine straight/chicane/S-curve and
sweeper/straight/hairpin. The larger cases contain all five primary families.
The pilot varies ordering, bend angles/radii, internal separation, global gaps,
approach lengths, primary-window lengths and symmetry. One case reverses travel;
one reflects geometry while retaining the specified winding. Constructor
parameters are preserved and all inserted connectors are separately identified.

The matched pair has exactly the same requested parameter multiset and counts,
but different requested and measured ordering. Its geometry fingerprints differ,
and family exposure differs by at most **6.86e-9** in fraction. For example, the
chicane/S-curve/straight placement changes relative to the sweepers and hairpin.
This difference is visible in the projected five-family matrix as well as the
geometry and sequence timeline. The direct six-state matrix can have the same
counts because intervening connector windows are explicit; it is not a substitute
for the recorded projected order and bridge chains.

Supporting exposure is deliberately transparent. It ranges from about **9.2% to
60.9%** of a lap, within the declared 65% cap. Some asymmetric returns use long
supporting straight legs; they are not presented as extra requested primary
maneuvers. Primary and supporting coverage, active-curvature coverage, and
internal straight regions are all separate statistics. The eight cases are a
controlled pilot, not a claim that every track is dominated by requested primary
windows or that this return topology maximizes experimental efficiency.

## Closure and geometric validation

Symmetric cases use the exact rotated-block displacement sum. Asymmetric cases
fix a bounded candidate set of smooth bends and solve two designated straight
lengths in a 2×2 system. Only supporting geometry can adjust. There is no primary
radius/angle/length scaling and no general arbitrary-layout optimizer.

Every accepted pilot candidate succeeded on its first searched return/radius
proposal, then passed the full existing validation pipeline and final CSV/raster
checks. Source maximum join residuals across the pilot are approximately:

- Position: **3.68e-14 m**.
- Wrapped heading: **1.53e-15 rad**.
- Curvature: **0** at the reported joins.

The minimum actual exported opposing-wall distance is **1.49965503 m** for the
1.5 m nominal corridor. Footprint margin is **0.02 m** per side. Peak curvature
rate is at most **0.42857143 inverse m²**, within the configured limit of 2.0.
All source/quantized centerlines and walls, nonlocal gaps, sampled full-vehicle
footprints, conservative raster width and full-area occupied-cell footprint
checks pass. Sample counts range from **562 to 1,362** at maximum 0.15 m curve
spacing, with 0.04 m/pixel corridor occupancy and no inversion.

The symmetric half-turn residuals are about a micrometer. The three asymmetric
cases have measured residuals around **1.62 m, 11.56 m and 11.44 m**. Here
“asymmetric” means the bounded-return layout is not a repeated half-turn layout;
it does not assert that every possible reflection symmetry is absent.

Vehicle dimensions and limits come from the actual combined-slip snapshot:
0.50 × 0.27 m body, `lf=0.15875`, `lr=0.17145`, steering ±0.523599 rad and
steering-rate bounds ±3.2 rad/s. The source YAML SHA-256 is
`fb8bab7a7c49cb913c6adafbec84d4560e02d927087ff61956be0145f6288016`.
Its tire calibration is recorded as **uncalibrated**.

G2 is not conflated with G3. Metadata records actual curvature and curvature-rate
jumps, plus changes in peak curvature/rate demand across windows. A regression
uses a requested linear-curvature ramp to verify that nonzero curvature-rate
jumps can be reported while position, heading and curvature remain continuous.

## Periodic composition and selector-window metadata

All main windows partition the final text-CSV lap without overlap or double
counting. The finish line is deliberately moved 5 m in physical arc length and
snapped to a retained vertex, so pilot annotations include real nontrivial
seam-crossing windows. Those windows remain single maneuvers; no artificial
label boundary is inserted at the finish. Cyclic last-to-first transitions still
count exactly once.

Each bundle adds a dedicated evaluation CSV alongside the nine standard map
artifacts and validation report. It records maneuver/region IDs and distances to
the next boundaries. Labels remain evaluation data: the normal centerline header
is still `x,y,theta,velocity`, and no policy observations or simulator code change.

The direct six-state matrix counts every annotation boundary. A five-family
projected matrix has an explicit connector-ID chain and distance for every edge.
The report separately counts primary-family switches, label changes, annotation
boundaries and geometrically significant envelope changes. These are not
interchangeable. For the matched pair, for example, there are **30 annotation
boundaries**, **28 label changes**, **12 primary-family switches**, and **20**
indicator-level demand changes per lap.

Nested regions expose the internal separation straight inside a chicane and the
straight portions of supporting returns. Actual zero-curvature coverage ranges
from about **30.0% to 62.3%**, calculated from the active-curvature fractions; it
is not hidden by treating an entire compound window as a uniform turn.

Timing analysis explicitly assumes **2 m/s** and **0.05 s per environment step**
(the inspected reference default with `action_repeat: 1`). The proposed selection
periods **5/10/20 steps**, with **10** the declared default, correspond to assumed
travel distances **0.5/1/2 m**. Whole windows, contiguous regions and internal
regions each receive optional time/opportunity estimates. Primary windows in this
pilot provide at least **4–18** nominal 10-step selection periods, depending on
the circuit's shortest window. Those counts can change substantially at another
speed. No speed is silently assumed when a specification omits it.

These are geometric/constant-speed estimates, not selector training, guaranteed
switch opportunities at runtime, successful driving labels or physical ratings.
Difficulty stays **unrated**, physical drivability stays **unassessed**. There
are no RL/LoRA, adapter-selection, automatic observation or controller changes.

## Rejection and duplicate evidence

Final root seed: **42**. Outer budget: **4 candidate attempts per pilot request**.
All final eight candidates were accepted on their first attempt, with **zero
final pilot candidate rejections**. The manifest retains all closure trials and
would preserve partial completion if the budget were exhausted. An early export
check caught a one-ULP periodic lookup ambiguity; evaluation now resolves boundary
ties at the profile's serialized arc precision. Intermediate review runs remain
under ignored `generated_maps`; the final pilot contains the corrected records.

[`phase3_rejections.json`](phase3_rejections.json) separately records four
intentionally rejected requests and their exact recipes/trial reasons:

| Request | Recorded outcome |
| --- | --- |
| Asymmetric return legs capped at 0.25 m | Four bounded trials rejected; the first required a 22 m return leg. |
| Requested 90-degree “hairpin” | Three trials rejected by measured heading-reversal classification. |
| 99% straight exposure in the fixed composite | Three allowed connector-radius trials rejected the measured exposure. |
| 20–21 m target lap range | Three trials rejected measured laps around 81–103 m. |

These are failures within the chosen bounds/topology, not a mathematical proof
that no alternative layout could exist. Nothing was silently scaled or relaxed.
Regressions also demonstrate recovery on a later sampled candidate, bounded
partial manifests, immutable destinations, wrong-label rejection, and rejection
of duplicate/cyclic-equivalent layouts with a changed seed, seam or traversal.
Configuration/representation IDs remain distinct from geometry fingerprints.

The fingerprints normalize cyclic start, reflection and travel direction, and
merge adjacent constant-curvature pieces. They are practical versioned checks,
not a universal proof of equivalence for arbitrary reparameterized curves.
The matched pair shares inventory lineage; no final train/validation/test split
has been assigned. All split fields remain `unspecified`.

## Real simulator integration and exact replay

For **every accepted circuit**, publication executed the actual existing
`smoke_marl_race.py` against the local reference. Per-track validation reports
record the reference commit and results for asset resolution, closed centerline,
PNG/PGM agreement, named `grid_1` and random-centerline spawns, directional finish
validation, forward/reverse/beyond-segment crossing, LiDAR, swept contact queries,
out-of-map behavior and MPC occupancy-mask agreement.

Each publication loaded the saved native recipe, rebuilt and revalidated the
track, and compared **10 deterministic artifacts byte for byte**: the standard
nine bundle files plus evaluation CSV. Eight additional golden regressions
independently replay the checked-in composite bundles in standalone processes.
All Phase 0–2 legacy golden checks also pass. Validation reports include SHA-256
hashes and actual smoke/replay evidence.

This is **static consumer integration and sampled geometric clearance**, not
full vehicle controller rollouts, completed race laps, controller-success
ratings, calibrated tire/surface tests or transfer evaluations. Continuous
swept-body certification between all poses remains future work.

## Runtime, tests and reproduction

[`phase3_runtime.json`](phase3_runtime.json) records the final pilot runtime,
separate from deterministic artifacts. Total preparation, publication, full
native replay and actual consumer smoke took **27.56 s** on this host:
**4.21 s** preparation and **23.28 s** publication/replay/smoke. Per-track
preparation ranged **0.280–0.780 s**, and the combined second stage
**2.00–3.89 s**. All selected closure solutions needed one trial. Plotting,
rejection audits, preliminary trials and the regression suite are outside these
timings. Replaying validation and starting consumer processes dominate this
small pilot; the Phase 1 spatial checks remain unchanged.

Baseline: **209 tests passed** before Phase 3. The final full suite passed
**255 tests in 55.59 s**, including all legacy tests. Coverage adds 46 composite cases:
eight accepted inventories, symmetric/asymmetric closure, deterministic ranges
and ordering, preserved primitives, connector constraints, mirrored/reversed
travel, cyclic duplicates, min/max exposure, useful windows, seam boundaries,
G2 versus curvature-rate jumps, transition matrices, internal regions, explicit
selector assumptions, matched ordering, bounded recovery/partial manifests,
immutable directories, metadata integrity, and all-eight golden replay.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
python3 scripts/generate_composites.py pilot \
  --recipe examples/phase3_pilot/pilot_recipe.json \
  --output generated_maps/phase3_reproduction --marl-race-root ../marl_race \
  --profile generated_maps/phase3_reproduction_runtime.json
python3 scripts/plot_composite_pilot.py generated_maps/phase3_reproduction
python3 scripts/audit_composite_rejections.py \
  --output generated_maps/phase3_rejection_reproduction.json
```

Use fresh output paths. The existing development dependencies suffice; no new
runtime dependency was added. Matplotlib's unavailable-3D warning on this host
does not affect the completed 2D PNG/SVG scientific plots.

## Modified files and recommendations

- `services/composite_spec.py`: native ordered specification, constraints, ranges,
  seed handling, identity and versioned loading.
- `services/composite_assembly.py`: explicit connector/source geometry, G2 ramps,
  exact repeated blocks, bounded asymmetric return and traversal transforms.
- `services/composite_statistics.py`: periodic interval lookup, independent
  fingerprints, composition, direct/projected transition accounting, nested
  driving regions, and evaluation-only selector-window analysis.
- `services/composite_tracks.py`: existing validation integration, final coordinate
  measurements, seam relocation, publication, native replay, evaluation CSV,
  compatible finish/spawn export and actual consumer smoke.
- `services/composite_pilot.py`: eight controlled requests, matched-order checks,
  bounded failures, duplicate prevention, manifest and runtime evidence.
- `scripts/generate_composites.py`, `plot_composite_pilot.py`,
  `audit_composite_rejections.py`: CLI and reproducible review artifacts.
- `tests/test_composite_tracks.py`: 46 new cases. README, metadata cross-reference,
  contract/results documents, runtime/rejection JSON and the eight-track pilot.

For Phase 4, evaluate feature operating ranges against the specialist tracks,
especially the larger composite hairpin radii and tight supporting return bends.
Sweep explicit speed/step assumptions and compare them with measured controller
traversal times before fixing selector periods or useful-window thresholds.
Connector burden is high in some asymmetric layouts; tighter exposure caps or
additional bounded return topologies should be explicit design choices. Preserve
primary-window identity after any future assembly changes, and keep internal
straight/demand regions visible in composition analysis.

Before a full dataset, broaden topology/severity coverage, test approximate
geometric duplicate detection beyond exact profile signatures, validate continuous
clearance and randomized spawn footprints, and perform calibrated controller
rollouts. Retain shared lineage for matched inventories and defer final split
assignment to Phase 5. A general optimizer, full 60-track collection and all
training workflows remain out of scope. **Stopped after Phase 3.**
