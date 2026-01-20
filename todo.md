## Code Quality & Refactoring

### Critical Priority

- [x] Extract duplicate spawn point copying logic in `annotation_commands.py:75-86`

- [x] Add error handling/logging in `wall_extraction.py` for image load failures

- [x] Replace 8 bare `except Exception` catches in `main_window.py`
  - Lines: 354, 549, 779, 831, 847, 900, 954, 1031
  - Replace with specific exceptions: `OSError`, `MapYamlError`, `ValueError`

- [x] Light refactor of `map_viewer.py`
  - [x] Update type hints to modern style (`list[T]`, `X | None`)
  - Skipped coordinate extraction: transforms are simple, Qt-specific, and only used internally

- [x] Light refactor of `main_window.py`
  - [x] Update type hints to modern style (`list[T]`, `X | None`)

### Moderate Priority

- [x] Add `__all__` exports to package `__init__.py` files
  - `ui/__init__.py`
  - `models/__init__.py`
  - `services/__init__.py`

- [x] Standardize type hints to modern style (`list[T]` instead of `List[T]`)
  - Files: `yaml_serializer.py`, `track_metrics.py`

- [x] Move magic numbers to constants module
  - Car dimensions in `map_viewer.py`
  - Default window size, spacing values in `main_window.py`

- [x] Extract large nested methods
  - `main_window.py._export_bundle_assets()` - kept as-is (linear sequence, readable)
  - `map_viewer.py.update_annotations()` - extracted 4 helper methods

### Low Priority

- [ ] Document complex geometry algorithms in `wall_extraction.py`
- [ ] Add logging infrastructure
- [ ] Expand test coverage for services and commands

### Deferred

- [ ] Full split of `map_viewer.py` into placement_handler.py and overlay_builder.py
  - Deferred: Code is cohesive and tightly coupled to viewer state
- [ ] Full split of `main_window.py` into separate operation modules
  - Deferred: Would require complex state sharing between modules

---

## Future Features

- [ ] New map wizard
  - [ ] Design wizard steps for metadata defaults, spawn grid presets, optional centerline seed
  - [ ] Implement wizard UI and integrate with project bootstrap
  - [ ] Provide starter templates and sample outputs for validation
