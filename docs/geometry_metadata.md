# Geometry and maneuver metadata contract 1.0.0

The executable JSON Schema is
[`track-metadata-v1.schema.json`](../src/map_editor/schemas/track-metadata-v1.schema.json).
Generated bundles reference `<stem>_metadata.json` from the map YAML's
`track_metadata` key. `geometry_metadata.validate_geometry_metadata` applies
JSON Schema plus periodic-interval, finite-number, width ordering, vocabulary,
nonoverlap and artifact-path checks. `load_geometry_metadata` validates on read.
Unknown schema versions or top-level fields reject instead of silently degrading.

This sidecar is independent of the ordinary `x,y,theta,velocity` centerline CSV
and of `<stem>_generation.yaml`. Recipe schema stays integer **1**, with generator
`map_editor.closed_bspline.v1`. Old recipes default to boundary-only occupancy
and empty label input; replay remains deterministic. New recipes retain explicit
`occupancy_mode` and the complete `track_metadata` inputs. A metadata schema
version describes data, while a generator version describes geometry/replay
behavior; changing either does not implicitly change the other.

| Field | Meaning |
| --- | --- |
| `schema_version` | String `1.0.0`; incompatible changes need a new schema. |
| `dataset_id`, `track_id` | Dataset namespace (nullable for standalone maps) and nonempty track identifier. Uniqueness is a dataset-manifest responsibility. Default track ID is the filename stem. |
| `generation_mode` | `specialist`, `composite`, or `legacy`. Existing generators emit `legacy` and no guessed labels. |
| `geometry_family` | Geometry implementation/family identifier, e.g. `closed_bspline` or `paper_l`; separate from maneuver vocabulary so one geometry may serve multiple research tasks. |
| `random_seed` | Nonnegative integer, or null if existing geometry was not sampled from a seed. Paper variants retain their candidate seed. |
| `generator_version` | Replay algorithm/version identifier; current output is `map_editor.closed_bspline.v1`. |
| `geometry` | Closed, world/map coordinates in meters; arc-length zero at the first exported centerline vertex, increasing in CSV order. Positive curvature means left. |
| `requested` | Requested geometry parameters, independent of measurements; unknown/not requested can be null. Includes nominal width, target length, minimum radius/separation, centerline spacing and raster resolution. |
| `measured` | Required total `length_m`, `minimum_radius_m` (nullable if curvature is zero), min/max/mean `width_m` fields, and `sample_count`, all from the final geometry used for export. Width is normal-ray corridor width, not a global boundary-distance bound. |
| `maneuvers` | Array of nonoverlapping primary maneuver intervals; empty for unlabeled legacy geometry. Each includes ID, controlled type/direction, periodic positions, requested/measured parameter mappings and difficulty. Array order is not geometry order; sort by start position for traversal. |
| `difficulty` | Optional `label` (`easy`, `medium`, `hard`, `unrated`), normalized `score` in [0,1], numeric `indicators`, and `assessment_version`. Empty means unassessed, not easy. A dataset assigning difficulty should record the assessment method/version. |
| `split` | `train`, `validation`, `test`, `unspecified`; default unspecified. Does not configure the simulator's scenario split selection. |
| `provenance` | Original paper assumptions, candidate seed/reference, generator revision, source paths/IDs, parent track/dataset IDs, calibration IDs or artifact checksums. Record missing evidence as unknown rather than claiming calibration. No automatic timestamp/absolute host path in generated metadata. |
| `occupancy_mode` | `walls` or `corridor`, matching the recipe/image. |
| `artifacts` | Required relative POSIX paths to map YAML, image, PGM, centerline, walls, track profile, preview, recipe and metadata itself. Absolute paths, backslashes and parent traversal reject. |

Numeric geometry keys should include their units (`_m`, `_rad`, `_inv_m`,
`_m_per_pixel`). Requested/measured maneuver mappings intentionally remain open
for family-specific parameters such as `turn_angle_rad`, `radius_m`,
`straight_length_m`, `lateral_offset_m`, `transition_length_m`, or
`curvature_rate_inv_m2`. Declare their measurement definitions with the generator
version before producing datasets. Difficulty indicators can include total
absolute heading change in radians, peak absolute curvature in inverse meters,
width-to-vehicle-width ratio and the fraction of lap length assigned to a target
family. Geometric indicators do not imply dynamic driving success.

## Controlled maneuver vocabulary

| `type` | Meaning | Permitted `direction` |
| --- | --- | --- |
| `straight` | Approximately zero-curvature run, with tolerance in requested/measured parameters. | `none` |
| `hairpin` | Tight, predominantly single-sign turn with large heading reversal. Record actual turn angle/radius. | `left`, `right` |
| `sweeper` | Sustained, predominantly single-sign bend with larger radius than the task's hairpin range. | `left`, `right` |
| `chicane` | Short, paired opposing turns defining an obstacle-avoidance/lateral-displacement feature. | `left_right`, `right_left` |
| `s_curve` | Connected opposing bends intended as a sustained S feature. Record lengths/radii to distinguish from a chicane. | `left_right`, `right_left` |
| `transition` | Connector, curvature ramp, or deliberately unclassified transitional geometry between maneuvers. | Any of the above directions |

Directions are encountered in increasing arc length. Left/right refer to signed
curvature, not screen coordinates. Compound directions record the first and
second turn signs. Phase 1 must choose explicit numerical tolerances and family
ranges; Phase 0 does not invent a universal radius threshold separating hairpins,
sweepers, chicanes, and S-curves.

Specialists require at least one annotated maneuver; the target family and a
requested dominance fraction can be placed in `requested`, with achieved fraction
in `difficulty.indicators`. The current validator checks vocabulary and geometry
interval consistency, not semantic dominance. Composites require at least two
maneuver families. Adjacent segments may touch at endpoints. Gaps are allowed and
mean unlabeled geometry, not an inferred straight. For exhaustive annotation,
add explicit transition intervals. The schema allows no overlapping primary
labels, including across the seam; overlapping research labels need a future
separate annotation layer.

## Periodic intervals

For a lap of length `L`, both `s_start_m` and `s_end_m` must lie in `[0,L)`.
Intervals are half-open in increasing travel direction:

- `wraps_seam: false`: `end > start`, interval `[start,end)`, length `end-start`.
- `wraps_seam: true`: `end <= start`, interval `[start,L) ∪ [0,end)`, length
  `L-start+end`.
- Equal endpoints with seam wrapping mean a full lap. A zero-length maneuver is
  invalid. Use endpoint zero, not `L`, to end precisely at the seam.

`length_m` is required and must agree with endpoints to a numerical tolerance of
1e-8 (relative or absolute meters). This removes the ambiguity between an empty
interval and a full lap and supports deterministic seam-aware slicing. CSV
profile `s_m` follows the same origin and omits the duplicated seam vertex.

For `L=17`, an interval from 15 m through the seam to 2 m is:

```json
{
  "id": "hairpin_1",
  "type": "hairpin",
  "direction": "left",
  "s_start_m": 15.0,
  "s_end_m": 2.0,
  "length_m": 4.0,
  "wraps_seam": true,
  "requested": {"radius_m": 1.0},
  "measured": {"minimum_radius_m": 1.04},
  "difficulty": {"label": "unrated"}
}
```

This is an illustrative annotation, not a measured label for the paper reference.

## Supplying future labels without changing recipes

A YAML spec may add a `track_metadata` mapping with `dataset_id`, `track_id`,
`generation_mode`, `geometry_family`, `random_seed`, `split`, `maneuvers`,
`requested`, `difficulty`, or `provenance`. Inputs cannot override measured
geometry, generator version, occupancy mode, frame or artifact paths. Actual
requested generator settings and original provenance override duplicate keys.
Malformed labels reject before any bundle files are written. Existing generators
do not infer labels, implement new maneuver shapes, enforce dominance fractions,
or claim that caller-provided labels match measured geometry. Those checks belong
to the Phase 1 feature-controlled generator.

Phase 2's [specialist templates](specialist_templates.md) retain this schema and
declare specialist intent independently of geometric composition. Their new
generator version records target/minimum exposure in `requested` and measured
family/role exposure, lineage and difficulty dimensions in `provenance`. Existing
Phase 0 and Phase 1 recipe interpretation remains unchanged.
