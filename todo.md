## TODO

### Procedural Track Generation
- Define input format for procedural tracks.
  - Choose file type (JSON or YAML).
  - Specify schema (control points, optional tangents, track width, resolution, padding).
  - Decide how to express closed loops (implicit close or explicit last point).
  - Add metadata defaults to match sample bundles (occupied/free thresholds, negate, resolution).
  - Define origin placement to mirror existing negative origin offsets.
  - Specify output naming conventions (stem, folder layout) to match sample bundles.
  - Use implicit loop closure (connect last point to first).
  - Default values: track width 2.2 m, centerline spacing 0.2 m, resolution 0.06 m/px, padding 5 m.
  - Origin formula: origin = (-min_x, -min_y, 0) after padding.
  - Threshold defaults: occupied_thresh 0.45, free_thresh 0.196, negate 0.
  - Raster wall thickness default: 2 px.
  - Constraints defaults: min curvature radius 3 m, min wall separation 1.5 m.
  - Deterministic-only generation (seed optional later).
  - Bundle layout: `stem_map/` with `stem.{png,pgm,yaml}`, `stem_centerline.csv`, `stem_walls.csv`.
  - CLI draft: `generate_track --input track.yaml --output sample_maps/stem_map --preset sample_default`.

- Implement closed-loop spline evaluation.
  - Use cubic B-spline for the closed-loop curve.
  - Enforce C1 continuity at loop closure.
  - Add arc-length resampling (e.g., spacing = 0.2 m).
  - Output centerline samples as (x, y, theta).

- Generate walls from centerline.
  - Compute local tangents and normals.
  - Offset left/right by half-width (configurable or per-point).
  - Smooth wall polylines (optional).
  - Detect/self-correct self-intersections.
  - Export `*_walls.csv`.
  - Enforce minimum wall separation and curvature constraints.
  - Add optional noise/smoothing controls for track feel.

- Rasterize to occupancy map.
  - Convert world coords to pixel grid using resolution.
  - Draw walls into a grayscale image (tunable wall thickness).
  - Add padding/margins.
  - Export PNG and PGM.
  - Enforce 8-bit grayscale PNG and raw grayscale PGM output.
  - Generate a preview overlay image for quick validation.

- Emit bundle metadata.
  - Write YAML with image, resolution, origin, thresholds, negate.
  - Embed annotations (centerline, optional spawn/start-finish defaults).
  - Ensure YAML field order and values align with sample bundles.

- Bundle outputs.
  - Save `map.png`, `map.pgm`, `map.yaml`.
  - Save `map_centerline.csv`, `map_walls.csv`.
  - Match CSV headers/formatting used in existing bundles.
  - Add CLI entrypoint to generate bundles from input file.
  - Support deterministic seeds for reproducible outputs.
  - Add scale-to-width step to hit target track width exactly.
