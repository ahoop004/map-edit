## TODO - Map Editor

All items from the initial cleanup pass have been completed. See git history for details.

### Critical Bugs (crash or data loss risk)

- [x] **Fix missing `math` import in `generate_random_tracks.py`** — moved to top of file; removed duplicate import from `if __name__` block.

- [x] **Potential `IndexError` in `_random_control_points()`** — added `if not points: return []` guard before the `points[0]` access.

---

### High Priority (significant UX or functional issues)

- [x] **Restructure the File / Edit menus** — File menu: Open, Save, Generate Track…, Export Bundle Assets…, Exit. Edit menu: all annotation actions + Generate Centerline from Map. Removed 7 redundant generate/view/export menu items.

- [x] **Fix `isinstance(destination_dir, bool)` hack in `_export_bundle_assets`** — split into a zero-arg `_export_bundle_assets()` slot and a private `_run_export_bundle_assets()` that holds the real logic.

- [x] **`_generate_centerline_from_walls` silently writes a CSV file** — removed the automatic `_create_centerline_csv()` call; user triggers CSV creation explicitly.

- [x] **Silent fallback in `_scale_walls_to_width()`** — raises `TrackSpecError` instead of returning unscaled walls when array lengths don't match.

---

### Medium Priority (correctness and maintainability)

- [x] **Off-by-one in `_update_track_metrics` highlight range** — verified as correct; `compute_track_width_profile` returns one sample per centerline point, so the formula `min(len(centerline)-1, len(profile.samples)-1)` iterates all C-1 segments without out-of-bounds access. No change needed.

- [x] **Redundant guard in `_add_spawn_point` and `_set_start_finish_line`** — simplified both to just call `_ensure_annotation_context()` directly.

- [x] **`min_wall_separation` never enforced** — implemented per-point wall separation check in `_ensure_wall_constraints()` using indexed left/right wall arrays.

- [x] **`2.2` track width hardcoded in three places** — all now use `DEFAULT_TRACK_WIDTH_TARGET` from `constants.py`; button label uses an f-string so it updates with the constant.

- [x] **Unused `centerline` parameter in `_ensure_wall_constraints()`** — removed the parameter and updated both call sites.

- [x] **Inconsistent zero-check for vector length** — added `EPSILON = 1e-9` module constant; replaced all `<= 1e-9` and the one `== 0` float comparison with `EPSILON`.

---

### Code Quality / Low Priority

- [x] **Confusing self-intersection skip condition** — simplified `if j in (i, i - 1, i + 1)` → `if j == i + 1`.

- [x] **Dead header-skip check in `_read_centerline_csv`** — removed the unreachable `if headers and row == headers` check; kept the `next(reader, None)` header skip with a comment.

- [x] **Redundant closure in `_resample_closed_polyline`** — added comment explaining the guard handles non-bspline callers; the bspline path always provides a closed polyline.

- [x] **Undocumented magic scaling overestimates** — added inline comments on the `* 1.05` and `* 1.02` overshoot buffers in both adjustment functions.

- [x] **`Optional` type hints** — standardized the entire codebase to PEP 604 `X | None` style; removed all `from typing import Optional` imports. Also replaced `List[X]` with `list[X]` where found, and removed an unused `from dataclasses import dataclass` in `track_metrics_panel.py`.

- [x] **Missing parameter documentation for `build_oval_control_points()`** — added a proper docstring with documented parameter ranges and typical values for `curve_amplitude` and `curve_frequency`.

- [x] **No resolution underflow protection** — added `_MAX_IMAGE_PIXELS = 32_768` cap in `_compute_raster_bounds`; raises `TrackSpecError` with a clear message if computed image dimensions would exceed the limit.

---

### Remaining / Future Work

- [ ] **`TrackGeneratorDialog` YAML/Oval toggle is fragile** — the two modes share one form with rows toggled via `setEnabled`. A `QTabWidget` (YAML tab / Oval tab) would be more idiomatic Qt and easier to extend.
