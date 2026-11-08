# Phase 5 research dataset v1

This release contains **60 accepted independent physical layouts under the
frozen development screening policy**: 40 train, 8 validation, 12 test. It is
complete. The [results](../../docs/phase5_results.md),
[contract](../../docs/research_dataset.md) and [overview](plots/overview.png)
explain generation, validation, diversity and limitations.

Use `manifest.json` for all tracks, or `train_manifest.json`,
`validation_manifest.json` and `test_manifest.json`. Stable map lists are
`all_maps.txt`, `train_maps.txt`, `validation_maps.txt`, and `test_maps.txt`.
Every listed path is relative to **this dataset directory**. Resolve it against
that directory before loading the ROS map YAML. Its image and sidecar paths
are relative to the individual bundle directory. No simulator configuration
or machine absolute path is required. Copy the entire release to relocate it.

Every `tracks/<slot_id>` directory is independently loadable and includes:

- ROS map YAML, occupancy PNG/PGM and preview PNG.
- Centerline, wall and measured width-profile CSVs.
- Native generation YAML, schema 2 metadata JSON and evaluation-only sample CSV.
- Offline validation JSON with native replay result and ten artifact SHA-256s.

The master additionally hashes each validation report, covering eleven files
per bundle. `integrity_report.json` verifies all quotas, pairwise independence,
lineages, paths, serialized geometry and candidate evidence hashes.
`analysis.json` contains per-track, marginal, joint and split statistics;
`generation_runtime.json`, `reproduction.json` and `environment.json` record
performance and local reproducibility evidence.
`SHA256SUMS` covers every other file in this release, including manifests,
evidence, plots and this README. From this directory verify with:

```bash
sha256sum -c SHA256SUMS
```

`dataset_recipe.json` fixes root seed 20261108, all 60 slots and the acceptance
policy. `development` contains the frozen calibration/readiness evidence and
resolved vehicle snapshot. `evidence/<slot_id>/attempt_XX.json` preserves all
accepted/rejected requests. Plot galleries use a common physical scale; only
the explicitly labeled shape diagnostic removes physical size.

From the map-edit repository root:

```bash
python3 scripts/generate_research_dataset.py audit datasets/phase5_v1 --require-complete
python3 scripts/generate_research_dataset.py generate \
  --recipe datasets/phase5_v1/dataset_recipe.json \
  --snapshot datasets/phase5_v1/development/vehicle_snapshot.json \
  --calibration datasets/phase5_v1/development/calibration.json \
  --readiness datasets/phase5_v1/development/readiness.json \
  --output generated_maps/research_reproduction
python3 scripts/generate_research_dataset.py replay \
  datasets/phase5_v1/tracks/train_specialist_straight_01/research_2bfd27e84a24eed59634dd42_generation.yaml \
  --output generated_maps/research_single_replay
```

Output directories must be fresh. Add `--resume` to dataset generation only
when recovering the same root recipe with the same frozen evidence. The
coordinator verifies accepted bytes before continuing.

Specialist families all occur in all three length scales globally. Train
composites satisfy the 6 two-family / 8 three-family / 6 four-or-five-family
quota. Full scale totals are 18 short [70,140) m, 22 medium [140,260) m and 20
long [260,450] m. Family IDs, maneuver labels and split IDs are evaluation
metadata; consumers must not automatically add them to policy observations.

Independence is physical-scale-aware: shared broad route shapes can occur at
materially different lengths/severities. No topology family is explicitly
held out. All circuits wind counterclockwise; 33 have modest variable widths.
The six five-family circuits have explicitly recorded halfturn symmetry.

The entire phase is offline. Vehicle/raster clearance is checked at retained
poses and does not certify continuous dynamic feasibility. The saved vehicle
profile is uncalibrated. Physical drivability is **unassessed**, difficulty
**unrated**, and simulator integration **not_run**. No controller or learning
outcome is included.
