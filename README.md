# ROS Map Editor (MapEdit)

A PySide6 desktop tool for inspecting and editing ROS map bundles used in F1TENTH-style race simulations. The app loads a PNG/YAML pair, lets you tweak metadata, place race annotations (start/finish line, spawn positions), and saves back to ROS-friendly formats.

## Features

- Load and validate ROS occupancy maps (PNG + YAML).
- Edit metadata such as resolution and origin with live validation.
- Visualise annotations: start/finish segment, spawn markers with heading ticks.
- Click-to-place tools for adding spawn points and defining the start/finish line with undo support.
- Diagnostics dock summarises metadata warnings and can highlight issues on the map.
- Centerline editor for managing polyline waypoints with smoothing helpers.
- Export centerline CSV and raster (PGM) artifacts for ROS toolchains.
- CLI helper `scripts/export_centerline.py` to resample/export waypoints from a map YAML into CSV.
- Occupancy-derived tooling: extract wall contours, auto-generate centerlines, and save walls to CSV.
- YAML save workflow with automatic backups to keep prior revisions safe.
- Paper-inspired rounded L circuit preset and seeded track collections, with
  replayable recipes, measured geometry, and curvature/width profiles.

See the [Phase 0 compatibility audit](docs/phase0_compatibility.md) for generation
commands, simulator integration, occupancy choices, validation limits and profiling.
The [geometry/maneuver metadata contract](docs/geometry_metadata.md) describes the
versioned sidecar schema for future dataset generators.

The [Phase 1 results](docs/phase1_results.md) provide a parametric maneuver backend,
[geometry/parameter contract](docs/parametric_geometry.md), and a small
[demonstration gallery](examples/phase1/overview.png). The new generator supports
physical-arc straights, hairpins, sweepers, chicanes, S-curves and curvature ramps,
with measured acceptance, continuity and vehicle-clearance checks. Its versioned
recipes use a separate backend; legacy spline recipes retain their behavior.

The [Phase 2 results](docs/phase2_results.md) add closed maneuver-specialist
templates with explicit intent, enforced measured exposure and bounded seeded
variation. Review the [ten-track pilot](examples/phase2_pilot/manifest.json),
[overview](examples/phase2_pilot/plots/overview.png), and
[specialist parameter contract](docs/specialist_templates.md).

The [Phase 3 results](docs/phase3_results.md) add controlled ordered composites,
repeated-block and bounded asymmetric closure, explicit connector/transition
statistics, and evaluation-only selector-window metadata. Review the
[eight-track manifest](examples/phase3_pilot/manifest.json),
[gallery](examples/phase3_pilot/plots/overview.png), and
[composite specification](docs/composite_circuits.md). Existing generator recipes
remain unchanged; no policy observations or training are added.

The [Phase 3B results](docs/phase3b_results.md) add explicit technical corners,
distributed connector optimization, measured layout objectives and a
[twelve-track pilot](examples/phase3b_pilot/manifest.json). Review the
[metric-scale gallery](examples/phase3b_pilot/plots/overview.png),
[Budapest/Hockenheim comparison](examples/phase3b_pilot/plots/reference_comparison.png),
and [technical geometry contract](docs/technical_geometry.md). New corner labels
use metadata schema 2; older generators keep their existing schemas and replay.

The [Phase 4B results](docs/phase4b_results.md) add offline long circuits,
bounded supporting-turn closure and independent variable left/right corridor
widths. Review the [twelve-track pilot](examples/phase4b_pilot/manifest.json),
[gallery](examples/phase4b_pilot/plots/overview.png),
[matched width comparisons](examples/phase4b_pilot/plots/width_pair_1.png), and
[extended geometry contract](docs/extended_geometry.md). New workflows use a
local resolved vehicle snapshot and require no simulator checkout or smoke test.

The [Phase 5 results](docs/phase5_results.md) provide the complete offline
[60-track research dataset](datasets/phase5_v1/README.md), with preassigned
train/validation/test splits, exact family/scale quotas, screened geometric
independence, immutable bundles and native byte replay. Review the
[60-track gallery](datasets/phase5_v1/plots/overview.png),
[master manifest](datasets/phase5_v1/manifest.json), and
[dataset/replay contract](docs/research_dataset.md). Physical drivability remains
unassessed; no simulator or learning experiments are included.

## Annotation Placement Workflow

1. Open a map bundle (File → Open Map…, select the YAML file).
2. Choose an annotation action:
   - `Edit → Add Spawn Point` (or “Add” in the Annotations dock) enters spawn placement mode.
   - `Edit → Set Start/Finish Line` (or “Set…” in the dock) enters start/finish placement mode.
3. The cursor switches to a crosshair and the status bar shows placement instructions.
4. Click on the map:
   - Spawn placement: left-click once to choose the spawn location. A dialog appears so you can adjust name and pose before committing.
   - Start/finish placement: left-click a start point, then left-click an end point. A dialog opens for fine-tuning the coordinates before saving.
5. Press `Esc` or right-click to cancel placement at any time.
6. Every confirmed placement becomes an undoable action (`Ctrl+Z` / `Ctrl+Shift+Z`).

## Status & Cursor Feedback

- Crosshair cursor indicates you are in placement mode.
- Status bar messages guide each step (“Click to place…”, “Placement cancelled”, etc.).
- After confirming a placement the status bar summarises the coordinates written to the map.
- The window title marks unsaved edits; opening another map, generating a track, or exiting offers Save, Discard, and Cancel.
- Editor docks use scrollable tabs so their controls remain accessible on smaller windows.
- Maps fit the viewport until you zoom manually; use View → Fit Map to Window to reset.

Track-width scaling clears earlier annotation undo history because it changes the coordinate system. Subsequent annotation edits remain undoable.

## Shortcuts

- `Ctrl+O` – Open map
- `Ctrl+S` – Save map
- `Ctrl+Z` / `Ctrl+Shift+Z` – Undo/Redo
- `Ctrl+Q` – Exit
- `Ctrl+0` – Fit map to window

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run.py
```

Run the tests with `pip install pytest` followed by `python -m pytest -q`.
The GUI tests use Qt's offscreen backend.
If unrelated system pytest plugins interfere, use
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`.

Generate and inspect an exclusively drivable corridor bundle:

```bash
python3 scripts/generate_track.py --preset paper_l --occupancy-mode corridor --output generated_maps/example
python3 scripts/smoke_marl_race.py generated_maps/example/paper_l_reference.yaml --marl-race-root ../marl_race
```

Omit `--occupancy-mode` to retain legacy boundary-only images. New bundles include
compatible finish annotations and a metadata JSON sidecar. Existing recipe files
remain valid; replay uses their recorded occupancy choice.

## Roadmap

See [todo.md](todo.md) for upcoming work, including diagnostics, centerline tooling, and the new map wizard.
