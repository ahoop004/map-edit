# ROS Map Editor (MapEdit)

A PySide6 desktop tool for inspecting and editing ROS map bundles used in F1TENTH-style race simulations. The app loads a PNG/YAML pair, lets you tweak metadata, place race annotations (start/finish line, spawn positions), and saves back to ROS-friendly formats.

## Features

- Load and validate ROS occupancy maps (PNG + YAML).
- Edit metadata such as resolution and origin with live validation.
- Visualise annotations: start/finish segment, spawn markers with heading ticks.
- Click-to-place tools for adding spawn points and defining the start/finish line with undo support.
- Diagnostics dock summarises metadata warnings and can highlight issues on the map.
- Centerline editor for managing polyline waypoints with smoothing helpers.
- YAML save workflow with automatic backups to keep prior revisions safe.

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

## Shortcuts

- `Ctrl+O` – Open map
- `Ctrl+S` – Save map
- `Ctrl+Z` / `Ctrl+Shift+Z` – Undo/Redo
- `Ctrl+Q` – Exit

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_map_editor.py
```

## Roadmap

See [todo.md](todo.md) for upcoming work, including diagnostics, centerline tooling, and the new map wizard.
