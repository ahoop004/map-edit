# Next Tasks (ordered simple → complex)

## Follow-up & Validation
- [x] Update documentation/tooltips to explain click-to-place behaviour.
  - [x] Document placement workflow in README.
  - [x] Add status bar/cursor hints summary to UX notes.
  - [x] Update any in-app tooltips or help dialogs.
- [x] Add regression checks (manual or automated) to confirm save/load still reflects new annotations accurately.
  - [x] Capture baseline round-trip using sample map bundles.
  - [x] Add unit tests for coordinate conversions in `map_viewer`.
  - [x] Add integration test covering click-to-place → undo → save → reload.

## Spawn Visualisation Refinements
- [x] Confirm vehicle footprint scaling in viewer matches map resolution metadata.
- [x] Replace spawn circle marker with footprint outline only.
- [x] Show a preview footprint under the cursor during spawn placement.

## Spawn Stamp Placement
- [x] Add dock control to toggle stamp mode and configure spawn count (1–20) and spacing.
- [x] Generate stamp preview with configurable two-row layout (N//2 per row, remainder on last row) that straddles the centerline.
- [x] Auto-orient stamp preview using nearby centerline tangent, else allow heading by click-drag before release.
- [x] On placement, create N spawns with sensible numbering aligned to stamp offsets.
- [x] Update status messaging/tests to cover stamp placement workflow.

## Dock Layout UX
- [x] Make each major dock section collapsible with a consistent toggle header/affordance.
- [x] Persist collapsed state per section across sessions.
- [x] Verify layout resizing and keyboard focus behave when sections expand/collapse.

## Export & Feedback Enhancements
- [x] Add bundled export action that writes PNG, PGM, YAML, centerline CSV, and wall CSV to a chosen folder.
- [x] Provide a progress indicator/spinner for long-running tasks (centerline extraction, exports, diagnostics).

## Future Features
- [ ] New map wizard.
  - [ ] Design wizard steps for metadata defaults, spawn grid presets, optional centerline seed.
  - [ ] Implement wizard UI and integrate with project bootstrap.
  - [ ] Provide starter templates and sample outputs for validation.
