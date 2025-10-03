# Next Tasks (ordered simple → complex)

## Follow-up & Validation
- [x] Update documentation/tooltips to explain click-to-place behaviour.
  - [x] Document placement workflow in README.
  - [x] Add status bar/cursor hints summary to UX notes.
  - [x] Update any in-app tooltips or help dialogs.
- [ ] Add regression checks (manual or automated) to confirm save/load still reflects new annotations accurately.
  - [x] Capture baseline round-trip using sample map bundles.
  - [x] Add unit tests for coordinate conversions in `map_viewer`.
  - [ ] Add integration test covering click-to-place → undo → save → reload.

## Future Features
- [x] Map diagnostics tooling.
  - [x] Surface resolution/origin deltas and occupancy threshold sanity checks.
  - [x] Provide quick toggle/visual overlay for metadata mismatches.
  - [x] Summarize diagnostics in a dock or modal report.
- [ ] Centerline editing/generation.
  - [ ] Decide on centerline data model (polyline or spline representation) and sampling resolution (e.g., 0.1–0.25 m spacing).
  - [ ] Implement manual centerline editing tools (add/move/delete nodes, smoothing options).
  - [ ] Export centerline as `nav_msgs/Path` YAML and `waypoints.csv` (x, y, theta [, v]) for ROS and offline use.
  - [ ] Provide helper to publish/export the waypoints for RL pipelines.
- [ ] New map wizard.
  - [ ] Design wizard steps for metadata defaults, spawn grid presets, optional centerline seed.
  - [ ] Implement wizard UI and integrate with project bootstrap.
  - [ ] Provide starter templates and sample outputs for validation.
