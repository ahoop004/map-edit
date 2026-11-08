# Formal research dataset contract

Phase 5 adds dataset coordinator **`map_editor.research_dataset.v1`**, design
**`research_design.v1`**, and native generator **`map_editor.research_tracks.v1`**.
The native template is `scaled_maneuver_inventory.v1`; metadata remains schema
**2.0.0**. Existing generator interpreters, versions, schemas, defaults and pilot
artifacts are unchanged. See the [results and limitations](phase5_results.md)
and [portable release](../datasets/phase5_v1/README.md).

## Frozen allocation and identities

The [root specification](phase5_allocation.json) allocates all 60 slots before
formal candidate generation, including split, mode, family/complexity, scale,
blueprint seed and parent lineage. Its canonical SHA-256 is
`6472ad03f8de21426b721144f37f44f6cbe637c6b9e0054b328dffd6ceec4d84`.
Root seed is **20261108**. Candidate seeds are independent deterministic hashes
of root seed, slot ID and attempt; they do not depend on preceding rejections.
The attempt budget is **24 per slot**, without quota substitutions.

| Split | Specialists | Composites | Total | Short | Medium | Long |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | 20 | 20 | 40 | 12 | 15 | 13 |
| Validation | 5 | 3 | 8 | 2 | 3 | 3 |
| Test | 5 | 7 | 12 | 4 | 4 | 4 |
| Total | 30 | 30 | 60 | 18 | 22 | 20 |

Measured exported polygon length determines scale: short **[70,140) m**, medium
**[140,260) m**, long **[260,450] m**. Boundary checks are half open exactly as
specified. Each train family has four specialists; validation/test have one each.
Training composite complexity is 6 two-family, 8 three-family, and 6 four/five-
family tracks. Complexity and scale are jointly allocated, not synonymous.

Parent lineage identifies a preallocated blueprint and all its candidate
attempts, rather than an entire maneuver family. Broad topology families are
separate metadata. Every formal slot has an independent parent blueprint;
reflection, reversal, seam, raster and width variants are never allocated as
new parents. The final global near-duplicate rejection leaves singleton
near-duplicate groups. No broad topology family is explicitly held out: the
release tests geometric instances within shared topology families. It must not
be presented as a topology-held-out generalization benchmark.

Native recipes contain complete primary parameters, topology alternatives,
connector bounds, exact width profile, vehicle snapshot, acceptance limits,
seed, attempt, split, parent lineage and slot. Configuration IDs hash the whole
canonical recipe. Track IDs are `research_` plus 24 hash digits. Separate
width-independent curvature/profile and polygon fingerprints identify layouts;
a width hash and corridor fingerprint identify the exported corridor.

## Specialist and composite semantics

Specialists use existing Phase 1 maneuvers and Phase 4B bounded supporting-turn
closure through a new adapter. All primary windows must classify as the declared
target family. Measured target exposure is primary target window length divided
by measured lap length, including any internal straight within the window.
Non-straight target windows must also have at least 50% genuinely curved source
length. Chicane separations stay short; hiding long straights in an opposing-turn
label cannot satisfy the specialist contract.

| Target | Minimum measured exposure | Scaffold choices |
| --- | ---: | --- |
| Straight | 70% | Four, five or six unequal primary straights and smooth supporting turns |
| Hairpin | 70% | Two unequal 151–166 degree primary hairpins, independently bounded supporting turns |
| Sweeper | 80% | Four, five or six unequal sweepers totaling 300 degrees, plus supporting turns |
| Chicane | 60% | Four, five or six opposing-turn windows, varied order and turn direction |
| S-curve | 65% | Four, five or six unequal opposing-turn windows, varied order and turn direction |

Sweeper specialist windows additionally require measured minimum radius ≥5 m
and length ≥5 m. Primary classification is the existing measured geometric
classification, including the 150–210 degree hairpin range. The
[development readiness evidence](phase5_readiness.json) exercises all five
families at all three scales before formal publication. The two-hairpin family
has one broad route topology with unequal geometry; the release does not claim
multiple distinct hairpin topology classes.

Composite complexity counts literal, independently classified **primary**
families. Supporting bends never inflate this count. The vocabulary includes
honest technical `corner` labels as well as the five canonical specialist
families. Two-family inventories use straight/corner, straight/hairpin or
corner/S-curve; three-family inventories add sweepers or opposing turns;
four-family inventories use straight/corner/chicane/S-curve. Five-family tracks
contain all five canonical specialist families.

Each composite primary family occupies at least 2.5% and at most 78% of the lap.
Total primary coverage is at least 60%, supporting geometry at most 40%.
The six five-family tracks explicitly use `controlled_halfturn.v1`, with two
rotated copies of a requested mixed motif. Their symmetry is recorded. Other
tracks use `bounded_supporting_turns.v1` and unequal source geometry. Internal
motif repetition does not create extra dataset entries.

For bounded closure, three deterministic placement proposals are scored by the
existing centerline objectives; a deterministic index breaks ties. Valid but
unselected proposals, failures and the selected candidate remain in journals.
Primary geometry is fixed before closure. Width is checked after centerline
selection and cannot change the winner. The halfturn method has one explicit
proposal. Per-slot retries vary independently seeded parameters within the
frozen recipe design, up to the outer attempt budget.

Widths use existing periodic independent left/right normal offsets. Uniform
width is sampled independently of the requested length scale; variable profiles
have smooth modest side changes. Width variants of an accepted centerline are
not counted as independent tracks. Source spacing is 0.12 m, raster resolution
0.06 m/pixel, exported CSV coordinates six decimal places.

## Development-calibrated independence policy

The [calibration evidence](phase5_calibration.json) records prior Phase 4B pilot
pairs, including actual matched-width duplicates, and synthetic translation,
rotation, reflection, reversal, seam and width controls. Thresholds were frozen
before formal validation/test generation. This is a pragmatic development
screen, without a human-labeled duplicate benchmark or statistical guarantee.

Shape distance uses 256 uniform-arclength complex coordinates, centered and
normalized to unit RMS radius. FFT cyclic correlations minimize RMS distance
over planar rotation, reflection, traversal reversal and seam position.
Translation and physical scale are removed **only for this diagnostic**.
Relative physical differences are `abs(a-b)/max(abs(a),abs(b),1e-12)`.
Primary-family exposure distance is L1 over the union of family keys.

Reject a pair as **near duplicate** when all of these hold:

- Normalized shape distance <0.055.
- Relative lap length difference <0.15.
- Relative minimum sustained radius difference <0.20.
- Primary-family exposure L1 difference <0.25.

Reject a pair as **ambiguous** when all of these hold:

- Normalized shape distance <0.085.
- Relative lap length difference <0.08.
- Relative p95 absolute curvature difference <0.12.
- Primary-family exposure L1 difference <0.15.
- Significant corner-count difference ≤1.

Both classes reject globally, including within a split. Exact curvature/profile
or polygon fingerprint matches reject regardless of physical or width metrics.
Every candidate is compared with all previously accepted layouts; all accepted
pairs are independently audited again after generation.

Independence is **physical-scale-aware**. Similar normalized shapes can pass
when physical length, radius/severity or primary maneuver distribution differs
materially. Consequently, 60 accepted physical layouts do not mean 60 unrelated
normalized shapes. Review the similarity matrix and joint physical metrics
before selecting a stronger shape-only holdout. Reassigning an accepted layout
to a split to rescue an ambiguous pair is not allowed by this release policy.

## Validation, publication and recovery

Only the saved local `profiles/f110_resolved_phase3b.json` is loaded. Each root
copies this resolved snapshot, calibration and readiness evidence with SHA-256
identities. No external checkout or simulator configuration is read.

Acceptance reuses existing source closure, G2 continuity, maneuver measurement,
radius/rate, steering geometry, centerline/wall intersection, global opposing-
wall clearance, nonlocal gap, periodic width, sampled rectangular footprint,
occupancy and full-area raster footprint checks. Metadata windows partition the
whole periodic lap, with evaluation-only sample labels. The serialized audit
also checks actual CSV schemas and finite values, winding, closed walls,
side-width consistency, directional finish, named spawn, spawn raster footprint,
and PNG/PGM pixel equality. All exported artifacts are hashed.

Sampled footprint checks certify the retained poses only. They cannot certify
continuous vehicle clearance between those poses, speed-dependent feasibility,
tracking error, friction, steering-rate feasibility or physical drivability.
The vehicle snapshot remains uncalibrated. Every report retains
`physical_drivability: unassessed`, `driving_difficulty: unrated`, and simulator
integration `not_run`. IDs, split labels and maneuver annotations are evaluation
metadata and are not added to policy observations.

Every bundle is prepared and exported twice: the second pass reloads the saved
native YAML, repeats candidate selection and all geometry work, and compares
ten deterministic artifacts byte for byte. A validation JSON records these
ten SHA-256 values; the master manifest additionally hashes that validation
report, giving eleven covered files per bundle. Native recipe reload tolerates
YAML sequence/list representations through canonical configuration identity.
Replay verification is exact in the recorded local software environment;
different raster/serialization libraries may require separate compatibility
verification.

Bundles are staged and published to fresh `tracks/<slot_id>` directories.
Existing bundles and attempt evidence are immutable. Master and split manifests
use atomic file replacement checkpoints; completion is explicit and fewer than
60 accepted slots stays partial. Rejections retain seed, native request when
available, reason, stage, inner layout journal and screening metrics in
`evidence/<slot>/attempt_XX.json`. Integrity reports hash the candidate ledger.

Explicit resume first validates existing hashes, root recipe, development
evidence, split paths and independence. Completed slots are skipped. Previously
rejected attempts are not retried. If a complete published bundle predates a
manifest checkpoint, resume verifies its deterministic recipe and hashes,
rechecks independence and adopts it; no accepted artifact is overwritten.
Corrupt or unrecognized orphan directories stop recovery for inspection.

## Offline commands and portable outputs

From the repository root, generate to a fresh directory:

```bash
python3 scripts/generate_research_dataset.py generate \
  --recipe docs/phase5_allocation.json \
  --output generated_maps/research_reproduction \
  --profile generated_maps/research_runtime.json
python3 scripts/generate_research_dataset.py generate \
  --resume --output generated_maps/research_reproduction
python3 scripts/generate_research_dataset.py audit \
  datasets/phase5_v1 --require-complete
```

`--max-requests N` deliberately checkpoints a partial run for recovery testing.
Runtime output paths must be fresh. Keep the original frozen development
evidence when resuming; the root copies are sufficient and can be supplied using
`--snapshot`, `--calibration` and `--readiness` after relocating the release.
Native single-track replay takes a complete recipe path:

```bash
python3 scripts/generate_research_dataset.py replay \
  datasets/phase5_v1/tracks/train_specialist_straight_01/research_2bfd27e84a24eed59634dd42_generation.yaml \
  --output generated_maps/native_research_replay
python3 scripts/analyze_research_dataset.py datasets/phase5_v1 \
  --output generated_maps/research_analysis.json
python3 scripts/plot_research_dataset.py datasets/phase5_v1 \
  --analysis docs/phase5_analysis.json --output generated_maps/research_plots
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q --offline-geometry
```

The release includes root recipe; master/train/validation/test manifests;
relative `all_maps.txt`, `train_maps.txt`, `validation_maps.txt`, `test_maps.txt`;
all independently loadable bundles; development evidence; candidate ledger;
integrity report; PNG/SVG plots; and release `SHA256SUMS`.
Map list paths resolve against the dataset root. ROS YAML image paths and
sidecar artifact paths resolve against their bundle directory. No machine
absolute path or simulator-specific consumer configuration is embedded.
