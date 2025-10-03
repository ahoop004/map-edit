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

## Future Features
- [ ] New map wizard.
  - [ ] Design wizard steps for metadata defaults, spawn grid presets, optional centerline seed.
  - [ ] Implement wizard UI and integrate with project bootstrap.
  - [ ] Provide starter templates and sample outputs for validation.
