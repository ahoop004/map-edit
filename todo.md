## Clean Up
- [x] Remove options and functionality related to adding the centerline to yaml
- [x] Dont automatically run track metrics. Only run when clicked.
- [x] Add option to generate pgm 
- [x] Add option to view pgm
- [x] Add option to generate wall csv
- [x] Add option to view wall csv



## Dock Layout UX
- [x] Make each major dock section collapsible with a consistent toggle header/affordance.
- [x] Persist collapsed state per section across sessions.
- [x] Verify layout resizing and keyboard focus behave when sections expand/collapse.

## Export & Feedback Enhancements
- [x] Add bundled export action that writes PNG, PGM, YAML, centerline CSV, and wall CSV to a chosen folder.
- [x] Provide a progress indicator/spinner for long-running tasks (centerline extraction, exports, diagnostics).

## Track Width Analysis
- [x] Compute per-point track width by intersecting centerline normals with wall contours.
- [x] Visualise width profile and summary stats in the UI with map highlights for out-of-spec regions.
- [x] Add auto-scale option to adjust map resolution so average width equals 2.20 m.

## Future Features
- [ ] New map wizard.
  - [ ] Design wizard steps for metadata defaults, spawn grid presets, optional centerline seed.
  - [ ] Implement wizard UI and integrate with project bootstrap.
  - [ ] Provide starter templates and sample outputs for validation.
