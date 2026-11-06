# Phase 0: bundle compatibility and geometry audit

Completed against `map-edit` main at base `5686ff4` and the local, clean
`ahoop004/marl_race` `physics-correctness` checkout at
`8a4bddf97c6de7740263b962a74ae4ae88fec0da`. Only map-edit source was changed.
The consumer checks below use its actual Python modules, not copied loader logic.
No simulator lap logic, maneuver generators, training code, or full dataset were
added. No commit or push commands were run by the agent. During the task HEAD
advanced externally to `bf08dbf` (`map compatibility`); that history was left intact.
Findings apply to these revisions, not an uninspected future branch.

## Compatibility findings

| Area | Confirmed behavior and discrepancies | Phase 0 treatment |
| --- | --- | --- |
| Coordinates | Both use world/map meters, X right, Y up, headings in radians. YAML origin is `[x,y,yaw]`; editor `MapMetadata` and consumer `env/map_config.py`, LiDAR and collision transforms support yaw. Procedural maps export yaw zero. | CSVs and annotations stay in world coordinates. New corridor mode uses the consumer's floor-based cell ownership. Existing rotated-map editor regressions remain intact. |
| Image orientation | Image row zero is at the top. `MapLoader.track_mask` is top-down; LiDAR flips it exactly once into bottom-up cells. Cell `(c,r)` covers local `[c*rsl,(c+1)*rsl] × [r*rsl,(r+1)*rsl]`. | PNG and PGM contain identical 0/255 pixels. Corridor fill samples cell centers. |
| Legacy raster coordinates | `_world_to_pixel` rounds X and `H-1-y/resolution`, while editor display uses continuous `H-y/resolution`. This is a one-pixel Y convention difference plus rounding versus cell flooring, up to roughly a cell per axis. CSV values are unaffected. | Preserve old `walls` raster and preview behavior. `corridor` uses `floor(x/resolution)`, image row `H-1-floor(y/resolution)`. Overlay positions may differ from continuous GUI placement by up to one cell; this is not a geometry translation. |
| Metadata | Consumer resolves `image` relative to map YAML; consumes resolution/origin. Runtime occupancy uses `track_threshold` and `track_inverted`, **not** ROS occupancy thresholds or `negate`. Its default threshold is 200 for light images, 127 for dark images. | Keep ROS fields and emit binary pixels. Defaults classify both modes identically in ROS, LiDAR, collision and MPC clearance. Newly generated specs reject threshold endpoints: `0 < free_thresh < occupied_thresh < 1`. Existing map YAML loading is unchanged. |
| Inverted images | Editor and ROS honor `negate`. Consumer loader ignores it, while MPC clearance honors it. | Preserve existing image inversion. Inverted bundles require environment `track_inverted: true`; YAML `occupancy.marl_race_track_inverted` records this requirement but the simulator does not read it automatically. The smoke script applies it explicitly. Prefer `negate: 0`. |
| Centerline | `x,y,theta,velocity` header; consumer reads first three columns as float32 and ignores the optional blank velocity. Closed-loop inference requires the closing gap to be at most 1.5 times median spacing. | Ordinary CSV is unchanged. No duplicate terminal vertex. Sample recognized as closed; float32 consumer length is 16.999996 m for the 17 m source. |
| Walls | `wall_id,vertex_id,x,y` header; consumer groups by ID and reads X/Y as float32. `vertex_id` is accepted and ignored. | Two closed boundaries remain separate, without a repeated last vertex. Closing edges are drawn explicitly. Physics collisions use the image, not this CSV; spawn lateral limits use nearest wall vertices. |
| Finish | Consumer resolves explicit scenario override, then `annotations.finish_line`, then top-level `finish_line`. It never reads `annotations.start_finish`. Direction must cross the segment. | Export compatible annotation alongside legacy segment. New tracks span the final boundary ray intersections at centerline `s=0`. Direction is the final centerline tangent, including reversed travel. Actual `validate_finish_line` and `LapTracker` checks pass. |
| Spawns | Named `[x,y,theta]` poses under `annotations.spawn_points` work with the loader and `env/spawn.py`. Centerline random spawning interpolates periodic geometry. Its min-distance parameter separates vehicles, not occupied cells; wall clamping reserves only 0.1 m from nearest vertices. | Preserve named-spawn format. Integration tests add a named grid pose and check both extraction paths. Generated samples retain the original no-named-spawns behavior and pass the actual random-centerline spawn helper. |
| Discovery | Both consumer discovery and bundle-directory resolution pick the first alphabetically sorted `*.yaml`. Recipes and collection manifests are not map YAML. Default `<stem>.yaml` sorts before `<stem>_generation.yaml`. | Keep one bundle per directory and prefer explicit map YAML paths. Sidecar metadata uses JSON so it cannot be mistaken for a map. Avoid placing `collection.yaml` alongside an individual map YAML. |

Inspected producer files: `services/procedural_track.py`, `yaml_serializer.py`,
`track_profile.py`, `paper_tracks.py`, `models/annotations.py`, CSV exporters,
map metadata transforms, GUI generation/edit/scaling paths. Inspected consumer
files: `utils/map_loader.py`, `core/map_selection.py`, `env/map_config.py`,
`env/centerline_state.py`, `env/spawn.py`, `utils/centerline.py`,
`physics/laser_models.py`, `physics/collision_models.py`, `physics/simulaton.py`,
and `agents/mpc/racing.py`.

## Finish annotation compatibility

The editor continues to use `StartFinishLine` and `annotations.start_finish`.
It now retains optional `direction` and opaque finish options such as version,
hysteresis, padding, and trigger speed. The coordinate dialog and uniform map
scaling preserve these fields. Saves emit `annotations.finish_line` as well.
Imported nested or top-level canonical finish annotations are editable; a
standalone top-level alias migrates into annotations on save. Removing a finish
line cannot leave a stale top-level alias behind.

When both editor and simulator aliases exist, `start_finish` is the editor's
authoritative record; saves synchronize the canonical alias. Avoid maintaining
conflicting aliases externally. If a legacy segment lacks direction, export
chooses its perpendicular normal with the sign of the nearest ordered
centerline tangent. Without a centerline, forward travel is unknowable: the
fallback is the left normal of the start-to-end segment. Supply an explicit
`direction` for those maps. Arbitrarily placed old segments are not moved.
Procedurally generated segments are automatically placed across the corridor.
Finite, distinct endpoints and a nonzero direction crossing the line are
validated. This does not change the consumer's lap-counting rules.

## Occupancy choice and raster checks

`occupancy_mode: walls` remains the default, including old recipes that omit the
field. Only boundary strokes are occupied. The corridor, infield, and surrounding
image are otherwise free. This is usable for a correctly spawned car constrained
by continuous wall collisions, but it does not describe an exclusively drivable
track corridor. Starting outside the track is allowed by its occupancy image.
LiDAR sees boundaries; clearance is positive on either side of each wall.

`occupancy_mode: corridor` marks the infield and exterior occupied, with only the
annulus between the two walls free. Even-odd scanline filling supports either
winding direction; boundary strokes are applied after filling. Padding is at
least `(wall_thickness_px // 2 + 1) * resolution` to keep boundary pixels inside
the image, even when requested padding is zero. Stroke thickness retains legacy
semantics: a square radius `thickness_px // 2` means even thicknesses cover one
extra pixel. Rasterization can reduce usable width relative to vector geometry.
The corridor preview uses the actual occupancy raster plus a centerline overlay.

Before writing corridor bundles, generation samples all centerline edges,
including the seam, at no more than half a raster cell and rejects any blocked
sample. This catches erased/narrow corridors; it is not a swept F110 footprint
clearance certificate. Coarser meter-per-pixel resolution or thicker strokes may
cause rejection. Use finer cells (a smaller `resolution`) or wider corridors.

Consumer behavior is consistent for binary maps with the indicated inversion:

- LiDAR distance transform uses the loader's free mask. Outside-map clearance is
  zero, and LiDAR range stops at the map rectangle.
- Physical swept collisions use that same bottom-up mask, occupied closed cells,
  the entire vehicle footprint, and the occupied map exterior.
- MPC constructs a signed clearance field from ROS `free_thresh`/`negate`.
  For our binary maps its positive cells agree with the runtime free mask.
  Outside-field queries return -1 m. Gray/unknown pixels and custom environment
  threshold overrides need a separate agreement check.
- Vector wall CSVs describe boundaries; they do not encode the occupied exterior.
  Spawn clearance based on them alone does not certify the vehicle footprint.

## Geometry validation evaluation

| Check | Existing implementation / Phase 0 assessment |
| --- | --- |
| Centerline self-intersections | All nonadjacent segment pairs, including closing edge. Collinear touches/overlaps count as intersections. Adjacent pairs are skipped. Zero-length exported edges now reject explicitly. Adjacent backtracking and spline behavior between samples need a stronger future regularity test. |
| Wall self-intersections | Same pairwise test for each final wall after smoothing/width fitting. |
| Wall-to-wall intersections | Exhaustive segment pairs between the two boundaries. Rejects crossing/touching boundaries. |
| Minimum corridor width | Checks nominal width, paired wall-vertex separation and measured left/right normal-ray width at every centerline vertex. This is **not** the global Euclidean distance between arbitrary boundary segments, nor continuous vehicle clearance. On the reference, normal width is 1.000000 m while exhaustive endpoint-to-opposing-segment distance is about 0.99966645 m. Do not interpret the width field as an exact global clearance bound. |
| Minimum turn radius | Circumcircle radius from adjacent exported centerline vertices, with 1 mm comparison tolerance. Signed profile curvature uses the equivalent three-point formula. Ignores collinear triples; it does not bound curvature derivatives or steering demand between samples. |
| Closed-loop continuity | Periodic B-spline and all exports close explicitly/implicitly; headings and profile include periodic neighbors. No repeated terminal vertex. Consumer topology checked on real loaded CSV. No analytic continuous curvature certificate. |
| Raster consistency | PNG/PGM exact equality, closed wall seam regression, floor-based corridor cells, corridor centerline sampling, and actual consumer mask/LiDAR/collision/MPC agreement. Legacy image behavior retained. Full footprint clearance over an entire lap remains future work. |

Additional constraints for Phase 1: a robust global boundary-gap constraint,
vehicle footprint and orientation margins, inside/outside topology and corridor
connectivity, bounded curvature variation and transition lengths, steering angle
and steering-rate limits, braking/acceleration distances, speed-dependent lateral
acceleration with calibrated tire/road friction, multi-car spawn overlap checks,
and raster-aware full-lap footprint sweeps. Use the vehicle configuration from
the simulator rather than a universal F110 dimension/radius assumption. The smoke
check uses a 0.58 × 0.31 m rectangular footprint for local collision checks only.

Minimum radius alone cannot establish dynamic drivability. No controller rollout,
success-rate guarantee, speed envelope, friction calibration, or multi-car race
was performed. These remain distinct labels from geometric acceptance.

A dense-resampling limitation was also observed: paper L's six control points
are sampled at a fixed 96 spline points per segment before polyline resampling.
At 0.01 m output spacing the measured minimum radius becomes about 0.49 m and
fails the preset's 0.65 m limit, although the standard 0.05 m reference measures
0.964 m. Over-resampling a piecewise-linear source concentrates curvature at its
vertices. Preserve version-1 replay; a future adaptive/analytic sampler should
use a new generator version and a convergence test. Dense profiling below uses
a smooth 32-control-point oval with sufficient source sampling.

## Performance measurements

Run `python3 scripts/profile_geometry.py --output docs/phase0_profile.json`.
Each case has one uninstrumented geometry run and a separate cProfile run;
cumulative times overlap and instrumentation overhead is material. One host,
Python 3.12.3; numbers are observations, not performance guarantees.

| Samples per boundary | Geometry wall time | cProfile total | Segment intersection calls | Corridor raster time |
| ---: | ---: | ---: | ---: | ---: |
| 340 | 0.340 s | 0.772 s | 287,470 | 0.015 s |
| 850 | 2.204 s | 4.511 s | 1,802,425 | 0.030 s |
| 1,700 | 8.470 s | 18.015 s | 7,217,350 | 0.059 s |

At 1,700 samples, intersection predicates consume 10.97 s cumulative, wall
constraint checking 9.95 s, the three self-intersection scans 7.45 s, and profile
ray-width calculations 5.55 s. All-pairs intersections and per-sample all-edge
rays dominate with quadratic growth. Rasterization is small by comparison. No
broad optimization refactor was performed. Profile first in Phase 1; consider
spatial indexing/broad-phase segment bounds while retaining exact predicates
and deterministic ordering.

## Reproduce and inspect

Install `requirements.txt` plus `pytest`. The host's unrelated ROS pytest plugin
is incompatible with the installed pytest, so disable plugin auto-discovery:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
python3 scripts/generate_track.py --preset paper_l --occupancy-mode corridor \
  --output sample_maps/phase0_reference
python3 scripts/smoke_marl_race.py \
  sample_maps/phase0_reference/paper_l_reference.yaml \
  --marl-race-root /home/aaron/marl_race
python3 scripts/generate_track.py \
  sample_maps/phase0_reference/paper_l_reference_generation.yaml \
  --output generated_maps/phase0_replay
```

The actual-consumer tests locate `../marl_race`, or `MARL_RACE_ROOT` if supplied.
They explicitly skip with a reason if that checkout or its NumPy/Numba/SciPy/Pillow
dependencies are unavailable. The precise remaining check on such hosts is the
smoke command above after installing the reference repository's dependencies.
This host executed the real integration; it was not skipped. The standalone
smoke also imports MPC clearance dependencies from the reference environment.
It keeps bytecode disabled and JIT caches in the temporary directory.

Baseline: **68 passed** before edits. Final full suite: **116 passed in 16.00 s**,
with no skips, using the command above. `git diff --check` also passed. Tests
include deterministic artifact-byte replay for both modes and inversion,
legacy recipe defaults, finish alias parsing and invalid annotations, reversed
centerline crossing, periodic metadata validation, invalid geometry/raster
rejection, old bundled YAML round trips, and existing GUI regression coverage.
The three consumer test cases cover legacy/noninverted, corridor/noninverted,
and reversed-travel corridor/inverted images, with named spawns.

The checked-in sample is `sample_maps/phase0_reference/paper_l_reference.yaml`:
17 m source lap, nominal 1 m width, 0.964095 m measured minimum radius, 340
samples, 0.02 m/pixel, 443 × 395 image, `negate: 0`. It includes PNG, PGM,
centerline and wall CSVs, profile CSV, preview, version-1 generation recipe and
version-1.0.0 geometry metadata. See `phase0_smoke.json` for actual consumer
results: closed-loop asset loading, forward accepted/reverse rejected, random
centerline spawn, 0.488262 m clearance at start, and LiDAR/collision/MPC agreement.
It intentionally has no fabricated maneuver labels or named starting grid.

## Modified-file guide and Phase 1 recommendations

- `services/procedural_track.py`: compatible automatic finish, explicit occupancy,
  raster checks, stricter binary threshold validation, metadata sidecar and recipe
  fields; default geometric sampling and legacy image behavior remain unchanged.
- `models/annotations.py`, `services/yaml_serializer.py`, `ui/annotation_panel.py`,
  `ui/main_window.py`: direction/options preservation, finish aliases and validation.
- `services/geometry_metadata.py`, `schemas/track-metadata-v1.schema.json`:
  structural and periodic semantic contract validation.
- `ui/track_generator.py`, `scripts/generate_track.py`: occupancy selection.
- `scripts/smoke_marl_race.py`, `scripts/profile_geometry.py`: reproducible evidence.
- `tests/test_phase0_contract.py`, `tests/test_marl_race_integration.py`: contract,
  old-format, and actual-consumer regressions. Existing tests retained.
- `requirements.txt`: JSON Schema validator dependency. `README.md`, this report,
  `geometry_metadata.md`, evidence JSON and the sample bundle document the result.

Phase 1 should first establish the versioned sampler, vehicle-clearance checks
and speed/friction-aware feasibility criteria above. Implement the controlled
maneuver families against the metadata contract, measure achieved features,
then enforce specialist dominance and composite transition rules. Add independent
geometry/split identifiers and lineage-aware train/validation/test separation.
Only after controller evaluation should geometrically valid tracks receive
drivability labels or be used to generate a full dataset. No Phase 1 work has
been started here.
