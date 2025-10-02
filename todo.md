# Map Editor MVP TODO

## MVP Foundation
- [x] Scaffold project directories and placeholder modules.
- [x] Implement application bootstrap in `src/map_editor/app.py` (QApplication factory, `main()` entry).
- [x] Create CLI launcher script `scripts/run_map_editor.py` that invokes the app bootstrap.
- [x] Implement `MainWindow` skeleton with central widget placeholders.
- [x] Add file menu actions, status bar messaging, and dock/side panel layout to `MainWindow`.
- [x] Implement `MapViewer` base widget that renders the loaded PNG.
- [ ] Add zoom/pan interaction handlers to `MapViewer`.
- [ ] Expose overlay management hooks in `MapViewer` for annotations.
- [ ] Build metadata editor form layout in `src/map_editor/ui/metadata_panel.py`.
- [ ] Add field validation and signal/slot wiring for the metadata panel.
- [ ] Define `MapBundle` data model capturing image path, metadata, and annotations (`src/map_editor/models/map_bundle.py`).
- [ ] Define annotation data structures for start/finish lines and spawn points (`src/map_editor/models/annotations.py`).
- [ ] Implement YAML load helpers with schema validation (`src/map_editor/services/yaml_serializer.py`).
- [ ] Implement YAML dump helpers that serialize metadata + annotations.
- [ ] Implement bundle loader that pairs PNG + YAML, resolves paths, and surfaces validation issues (`src/map_editor/services/map_loader.py`).
- [ ] Implement annotation-focused undo/redo commands (`src/map_editor/commands/annotation_commands.py`).
- [ ] Wire viewer, metadata panel, and models together to display loaded maps.
- [ ] Implement annotation editing tools (add/move/delete) tied into undo stack.
- [ ] Add save workflow exporting updated YAML (with backups/versioning as needed).

## Testing & Quality
- [ ] Collect sample map fixtures (existing PNG/YAML pairs) for manual + automated tests.
- [ ] Add unit tests for YAML parsing/serialization and annotation models.
- [ ] Add integration test covering open → edit → save round trip.
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
