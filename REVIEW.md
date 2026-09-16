# Repository review and cleanup

## Fixed

- **Unsaved edits:** track changes against the last loaded/saved bundle, including undo and metadata edits. Prompt before closing or replacing the map; cancelled or failed saves keep the current document.
- **Save integrity:** preserve `negate`, extra YAML fields, and image references across saves to other directories. Write a temporary file before replacing the original and retain backups.
- **Map loading:** convert malformed YAML and invalid metadata into handled errors. A failed image load leaves the previous map visible.
- **Graphics lifetime:** clear placement previews before Qt deletes scene items, avoiding stale C++ references during reloads and clears.
- **Centerline editing:** fix row movement, preserve coordinate precision, and reject invalid/nonfinite values rather than silently dropping rows.
- **Placement:** restore keyboard focus, enable hover previews, reset the Finish button when switching tools, and consistently use right-click to cancel.
- **Layout:** use scrollable dock tabs; fit maps after initial layout and resizing until the user zooms. Add View → Fit Map to Window (`Ctrl+0`).
- **Coordinates:** use shared forward/inverse transforms for rotated map origins, and honor inverted occupancy when extracting walls.
- **Responsiveness:** enable worker threads by default, connect completion before starting work, and remove duplicate diagnostics calls.
- **Other state fixes:** retain spawn-list selection, preserve untouched metadata precision, prevent stale undo commands after scaling, and allow repeated exports into the map's own folder.
- **Maintenance:** remove unused imports, fix undefined type names and stale test expectations, correct the README launcher, and remove tracked Python bytecode with ignore rules to prevent recurrence.

## Validation

Regression coverage includes scene replacement during placement, centerline validation/reordering, save failures and round-trips, unsaved-change handling, worker responsiveness/errors, rotated coordinates, inverted occupancy, repeated exports, and small-window layout. A sample map was also rendered and inspected using Qt's offscreen backend. Native desktop interaction across display servers remains untested.

## Follow-up opportunities

- Make track-width scaling a document-level undo command. This pass clears the older annotation history to prevent commands from restoring obsolete coordinates.
- Separate file/export workflows from `MainWindow` as further features are added; it currently coordinates most application behavior.
- Split the track generator's YAML and Oval forms into tabs, as already noted in `todo.md`.
