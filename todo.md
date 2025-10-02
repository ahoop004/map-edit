# Map Editor MVP TODO

## MVP Foundation
- [x] Scaffold project directories and placeholder modules.
- [ ] Bootstrap PySide6 application entry point (`src/map_editor/app.py`) and lightweight CLI launcher.
- [ ] Implement main window shell with menu, status bar, and dock/side layouts (`src/map_editor/ui/main_window.py`).
- [ ] Build map viewer widget with zoom/pan and overlay hooks (`src/map_editor/ui/map_viewer.py`).
- [ ] Build metadata editor panel with validated inputs and signal wiring (`src/map_editor/ui/metadata_panel.py`).
- [ ] Define map bundle data model capturing image path, metadata, and annotations (`src/map_editor/models/map_bundle.py`).
- [ ] Define annotation data structures for start/finish lines and spawn points (`src/map_editor/models/annotations.py`).
- [ ] Implement YAML read/write utilities (`src/map_editor/services/yaml_serializer.py`).
- [ ] Implement bundle loader/validator that pairs PNG + YAML and reports issues (`src/map_editor/services/map_loader.py`).
- [ ] Create undo/redo command implementations for metadata and annotations (`src/map_editor/commands/annotation_commands.py`).
- [ ] Wire viewer and panels together to display loaded maps and overlays.
- [ ] Implement annotation editing tools (add/move/delete) tied into undo stack.
- [ ] Add save workflow exporting updated YAML (with backups/versioning as needed).

## Testing & Quality
- [ ] Define sample map fixtures (existing PNG/YAML pairs) for manual + automated tests.
- [ ] Add unit tests for YAML parsing/serialization and annotation models.
- [ ] Plan integration test to ensure round-trip open → edit → save works.
- [ ] Integrate linting/formatting (e.g., `ruff`, `black`) and CI-ready test entry point.

## UX Enhancements
- [ ] Evaluate need for dockable panels vs stacked widgets; prototype layout options.
- [ ] Add status bar messaging, tooltips, and keyboard shortcuts.
- [ ] Implement measurement helpers (distance markers, grid overlay) if needed for racetrack tuning.

## Nice-to-Have / Future
- [ ] Support additional map formats (`.pgm`, `.tif`, `.bt`) via abstraction layer.
- [ ] Integrate occupancy editing (paintbrush/eraser) with configurable brush sizes.
- [ ] Allow custom layers (cones, obstacles) with visibility toggles.
- [ ] ROS integration hooks (publish/subscribe) for real-time preview or validation runs.
- [ ] Scenario import/export for RL training metadata.

## Documentation & Planning
- [ ] Draft architecture overview (modules: UI, services, models, storage).
- [ ] Decide whether lightweight component diagram or state diagram is helpful once MVP modules stabilize.
- [ ] Document usage workflow and configuration options in README.
- [ ] Flesh out dependency instructions (`requirements.txt`) and virtual environment guidance.
