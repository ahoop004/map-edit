# Paper circuit and collections

The `paper_l` preset approximates the rounded L circuit described in
*On learning racing policies with reinforcement learning*,
[arXiv:2504.02420v2](https://arxiv.org/abs/2504.02420v2), Section III-C.
It is **not the authors' original geometry**. The paper reports a 17 m circuit
and a 1 m width; here 17 m is interpreted as centerline lap length. The control
polygon proportions and corner shapes are approximations. The default 0.65 m
minimum corner radius is our generation constraint, not a measured paper value.

## In the editor

Choose **File → Generate Track… → Source: Paper L (approximation)**.
The preset uses a 17 m lap, 1 m width, 0.02 m/pixel raster resolution, and
0.05 m centerline spacing. Preview shows the reference circuit.

- Leave **Variants** at zero to generate just the reference.
- Set **Variants**, **Collection seed**, and **Shape variation fraction** to
  generate a reference plus a collection. For example, 12 variants means 13 maps.
- Collections require an empty output folder, preventing accidental replacement.
- The editor opens the reference when collection generation finishes. Open an
  individual variant's map YAML to inspect it.

The target length is fitted after smoothing and resampling. Candidates that
violate the radius or boundary constraints are rejected; they are not enlarged
to make them pass. Width measurements describe the geometric boundaries; wall
pixel thickness and raster quantization affect the usable occupancy-map width.

## Command line

From the repository root, with the development environment installed:

```bash
# One reference bundle
python scripts/generate_track.py --preset paper_l \
  --output generated_maps/paper_l_reference_map

# Reference plus 12 variations, reproducible from seed 42
python scripts/generate_track.py --preset paper_l --count 12 --seed 42 \
  --variation 0.2 --output generated_maps/paper_l_collection

# Replay any bundle from its stored generation recipe
python scripts/generate_track.py \
  generated_maps/paper_l_collection/paper_l_001/paper_l_001_generation.yaml \
  --output generated_maps/replayed_variant
```

Optional overrides: `--target-length`, `--track-width`, `--min-radius`, and
`--max-attempts`. Existing `python scripts/generate_track.py SPEC.yaml` usage
continues to work. The GUI's YAML source also accepts generation recipes.

Variations independently multiply the reference's horizontal, vertical, and arm
control-polygon extents by factors in `[1 - variation, 1 + variation]` before
fitting the lap length. Length and width stay fixed unless explicitly changed.
This first collection generator varies the L family only; it does not yet
generate other layout families or randomize surface friction.

`collection.yaml` records the reference, accepted map paths, each attempted seed,
achieved dimensions, and rejection reasons and recipes when available. Its paths
are relative to the collection folder. A candidate with degenerate geometry may
have `achieved: null` because measurements could not be calculated. Generation
stops after the requested accepted count or the attempt budget (default: count
times 20). CLI exit status 2 means a partial collection; the manifest has
`complete: false`. I/O and invalid-reference errors exit with status 1.

## Bundle files and gym integration

The existing formats are preserved:

| File | Contents |
| --- | --- |
| `<stem>.yaml` | ROS map metadata and embedded centerline annotations |
| `<stem>.png`, `<stem>.pgm` | Identical occupancy pixels; closed boundary lines |
| `<stem>_centerline.csv` | Existing `x,y,theta,velocity` columns |
| `<stem>_walls.csv` | Existing `wall_id,vertex_id,x,y` format with BEGIN/END rows and closed loops |
| `<stem>_preview.png` | Visual preview with centerline overlay |
| `<stem>_track_profile.csv` | Periodic geometric observations, described below |
| `<stem>_generation.yaml` | Versioned recipe, provenance, measured geometry, and relative artifact paths |

Generation now writes the two additional files for all procedural bundles.
They are optional for consumers: your gym can continue loading its existing files.
They are snapshots of generation, **not automatically refreshed after manual
map edits**. Regenerate the bundle from a revised recipe to keep these artifacts
consistent.

The profile uses the same centerline vertices as the centerline CSV:

| Column | Meaning |
| --- | --- |
| `s_m` | Cumulative centerline distance in meters, starting at zero |
| `x_m`, `y_m` | Position in the ROS map's world coordinate frame |
| `heading_rad` | Periodic tangent heading, radians, counterclockwise from +x |
| `curvature_inv_m` | Signed curvature in 1/m; positive for left turns |
| `width_m` | Measured left width plus right width |
| `left_width_m`, `right_width_m` | Distance to the first boundary intersection along each centerline normal |

The first vertex is not repeated at the end of the profile or centerline CSV.
The closing segment counts toward `achieved.length_m` in the generation recipe;
wrap observation queries modulo that length. Curvature uses three neighboring
vertices with periodic indexing; headings likewise use periodic neighbors.
All distances are metric, and widths are full corridor widths rather than
vehicle-clearance margins. A car footprint must be accounted for by the gym.

For the paper's 0.3 m observation spacing, interpolate curvature and width from
the dense profile at `s + k * 0.3`, wrapping at the lap boundary. If interpolating
heading, handle the ±pi wrap rather than interpolating raw angles linearly.
The generator does not prescribe an observation horizon or vehicle dynamics.

No friction coefficient is assumed. A future optional surface file can describe
spatial properties; episode-to-episode friction and dynamics randomization should
remain an experiment configuration. The recipe's `schema_version` and `files`
mapping provide a place to identify additional bundle artifacts later.

Keep this family together when constructing train/validation/test splits:
nearby variants alone are not a strong test of generalization to new layouts.
