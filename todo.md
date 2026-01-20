## TODO

### Procedural Track Generation
- [x] Define YAML schema for procedural tracks.
  - [x] Required: `stem`, `control_points` (x, y).
  - [x] Optional overrides: `track_width`, `centerline_spacing`, `resolution`, `padding`, `wall_thickness_px`.
  - [x] Defaults: track width 2.2 m, centerline spacing 0.2 m, resolution 0.06 m/px, padding 5 m.
  - [x] Threshold defaults: occupied_thresh 0.45, free_thresh 0.196, negate 0.
  - [x] Implicit loop closure (connect last point to first).
  - [x] Origin formula: origin = (-min_x, -min_y, 0) after padding.
  - [x] Bundle layout: `stem_map/` with `stem.{png,pgm,yaml}`, `stem_centerline.csv`, `stem_walls.csv`.
  - [x] CLI: `generate_track --input track.yaml --output sample_maps/stem_map --preset sample_default`.

- [x] Implement closed-loop spline evaluation.
  - [x] Use cubic B-spline for the closed-loop curve.
  - [x] Enforce continuity at loop closure.
  - [x] Arc-length resampling (default spacing 0.2 m).
  - [x] Output centerline samples as (x, y, theta).

- [x] Generate walls from centerline.
  - [x] Compute local tangents and normals.
  - [x] Offset left/right by half-width.
  - [x] Smooth wall polylines (optional) and prevent self-intersections.
  - [x] Enforce constraints: min curvature radius 3 m, min wall separation 1.5 m.
  - [x] Export `*_walls.csv`.

- [x] Rasterize to occupancy map.
  - [x] Convert world coords to pixel grid using resolution.
  - [x] Draw walls into 8-bit grayscale image (default thickness 2 px).
  - [x] Add padding/margins.
  - [x] Export PNG and raw PGM.
  - [x] Generate a preview overlay image for quick validation.

- [x] Emit bundle metadata.
  - [x] Write YAML with image, resolution, origin, thresholds, negate.
  - [x] Embed annotations (centerline, optional spawn/start-finish defaults).
  - [x] Align YAML field order/values with sample bundles.

- [x] Bundle outputs.
  - [x] Save `stem.png`, `stem.pgm`, `stem.yaml`.
  - [x] Save `stem_centerline.csv`, `stem_walls.csv` with existing headers.
  - [x] Add CLI entrypoint to generate bundles from input file.
  - [x] Add scale-to-width step to hit target track width exactly.

### GUI Integration
- [x] Add File → "Generate Track…" menu action.
- [x] Build a modal wizard/dialog:
  - [x] Select YAML input file and output folder.
  - [x] Expose preset overrides (width, resolution, padding).
  - [x] Show preview overlay (centerline + walls).
  - [x] Confirm + run generation.
- [x] Run generation in background thread with busy/progress dialog.
- [x] Auto-load generated bundle into the editor.
