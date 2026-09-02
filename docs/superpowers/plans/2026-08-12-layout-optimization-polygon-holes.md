# Layout Optimization Polygon Holes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `boundaries` so the three layout optimizers accept homogeneous `list[shapely.geometry.Polygon]` inputs, preserve holes, union overlapping regions, and exclude interiors from placement.

**Architecture:** Centralize input validation and Shapely normalization in `LayoutOptimization`. Keep the caller's original `boundaries` value, while geometric consumers use one normalized Polygon/MultiPolygon. Preserve the existing point-containment and signed-distance algorithms; remove SciPy's raw-vertex and single-region assumptions.

**Tech Stack:** Python 3.10+, Shapely 2.x, NumPy, SciPy, pytest.

## Global Constraints

- Preserve `list[tuple[float, float]]` and `list[list[tuple[float, float]]]` behavior.
- Accept only a non-empty homogeneous `list[Polygon]` for the new form; reject mixed inputs.
- Reject invalid Polygon inputs with `ValueError`; never repair them implicitly.
- Use `unary_union`; overlapping polygons count once and disjoint polygons may produce `MultiPolygon`.
- Preserve `contains` semantics: points on exterior or hole boundaries are invalid.
- Do not add a raster mask or resolution-dependent approximation.
- Do not include `.codegraph/`, `.history/`, or `AGENTS.md` in commits.

---

### Task 1: Add failing geometry and optimizer tests

**Files:**
- Modify: `tests/layout_optimization_integration_test.py`

**Interfaces:** Uses current `FlorisModel`, `YAML_INPUT`, and optimizer constructors. Produces executable expectations for holes, unioned regions, legacy inputs, and validation.

- [ ] **Step 1: Add Shapely imports and fixtures.** Import `Point` and `Polygon`; define an outer square with a smaller square hole plus overlapping and disjoint squares sized for the existing test model.
- [ ] **Step 2: Add a failing Gridded hole test.** Construct `LayoutOptimizationGridded` with `boundaries=[polygon_with_hole]`, run it with deterministic spacing/translation, and assert `all(polygon_with_hole.contains(Point(x, y)) for x, y in zip(x_opt, y_opt))`; directly assert a known hole point is rejected by `test_point_in_bounds`.
- [ ] **Step 3: Add failing union and validation tests.** Assert overlapping polygons normalize to one merged component and disjoint polygons normalize to a `MultiPolygon`; assert `[]` raises `ValueError`, `[polygon, [(0.0, 0.0)]]` raises `TypeError`, and an invalid Polygon raises `ValueError`.
- [ ] **Step 4: Add a failing SciPy test.** Construct `LayoutOptimizationScipy` with disjoint Polygon regions and a hole; assert construction succeeds, `_distance_from_boundaries` is negative for a hole point, and positive for a valid point away from an edge.
- [ ] **Step 5: Run the failing tests.** Run `pytest tests/layout_optimization_integration_test.py -k "polygon or hole or union or scipy" -q`. Expected: new Polygon tests fail against the current coordinate-only parser and SciPy guard.

### Task 2: Normalize all accepted boundary forms in the base class

**Files:**
- Modify: `floris/optimization/layout_optimization/layout_optimization_base.py`
- Test: `tests/layout_optimization_integration_test.py`

**Interfaces:** Consumes raw `boundaries`; produces original `self.boundaries`, normalized `self._boundary_polygon` (Polygon/MultiPolygon), its `_boundary_line`, and aggregate bounds.

- [ ] **Step 1: Add Shapely operation imports.** Import `unary_union` and retain `Polygon`/`MultiPolygon` for strict type checks and legacy conversion.
- [ ] **Step 2: Add `_normalize_boundaries(boundaries)`.** Reject a non-list or empty top-level value; detect a pure Polygon list, validate every polygon with `is_valid`, and return `unary_union(polygons)`; detect the existing one-ring and nested-ring coordinate forms, convert them to Polygons, and union them; reject mixed/malformed input with `TypeError`; reject invalid polygons, empty results, or non-Polygon/MultiPolygon results with `ValueError`. Do not call `buffer(0)`.
- [ ] **Step 3: Replace inline constructor parsing.** Set `self.boundaries` to the raw input, assign the helper result to `_boundary_polygon`, assign `.boundary` to `_boundary_line`, and derive all four bounds from the normalized geometry.
- [ ] **Step 4: Update `plot_layout_opt_boundary`.** Iterate Polygon exteriors and interiors, and each component of a MultiPolygon, without assuming a single Polygon boundary has `.geoms`; retain existing styles.
- [ ] **Step 5: Run base and Gridded tests.** Run `pytest tests/layout_optimization_integration_test.py -k "Gridded or polygon or hole or union" -q`; expect Polygon-hole, union, validation, legacy, separate-region, and hexagonal tests to pass.

### Task 3: Enable SciPy over holes and multiple components

**Files:**
- Modify: `floris/optimization/layout_optimization/layout_optimization_scipy.py`
- Test: `tests/layout_optimization_integration_test.py`

**Interfaces:** Consumes normalized geometry and aggregate bounds from the base class; produces SciPy construction and signed constraints for Polygon holes and MultiPolygon regions.

- [ ] **Step 1: Remove the nested-boundary `NotImplementedError`.** The base helper now owns validation and no SciPy-specific single-region guard remains.
- [ ] **Step 2: Remove `boundaries_norm`.** Stop indexing `self.boundaries` as raw coordinate pairs; SciPy needs only `xmin/xmax/ymin/ymax`, `_boundary_line`, and `_boundary_polygon`.
- [ ] **Step 3: Preserve and verify `_distance_from_boundaries`.** Continue using `Point.distance(self._boundary_line)` and containment sign; hole/outside points must be negative, valid interior points positive.
- [ ] **Step 4: Run focused SciPy tests.** Run `pytest tests/layout_optimization_integration_test.py -k "Scipy or scipy or polygon or hole" -q` and `pytest tests/reg_tests/scipy_layout_opt_regression.py -q`; expect multi-region construction and legacy regression behavior to pass.

### Task 4: Cover RandomSearch and document the public contract

**Files:**
- Modify: `tests/layout_optimization_integration_test.py`
- Modify: `docs/layout_optimization.md`
- Modify: `floris/optimization/layout_optimization/layout_optimization_base.py`
- Modify: `floris/optimization/layout_optimization/layout_optimization_gridded.py`
- Modify: `floris/optimization/layout_optimization/layout_optimization_scipy.py`
- Modify: `floris/optimization/layout_optimization/layout_optimization_random_search.py`

**Interfaces:** Consumes normalized geometry; produces deterministic RandomSearch coverage, accurate constructor docstrings, and a user-facing Polygon-with-hole example.

- [ ] **Step 1: Add a deterministic RandomSearch test.** Use `interface=None`, `n_individuals=1`, fixed `random_seed`, `use_dist_based_init=True`, short durations, and a coarse grid; assert every generated point is contained by the Polygon-with-hole. Also test `test_point_in_bounds` for valid, hole, and outside points.
- [ ] **Step 2: Update all relevant docstrings.** Document both legacy coordinate forms and homogeneous `list[Polygon]`; state that interiors are excluded and multiple polygons are unioned; do not add a second public parameter.
- [ ] **Step 3: Add a compact `docs/layout_optimization.md` example.** Import `Polygon`, build an outer square with a hole, pass `[site_polygon]` as `boundaries`, and explain union and hole semantics.
- [ ] **Step 4: Run layout integration and regression tests.** Run `pytest tests/layout_optimization_integration_test.py -q` and `pytest tests/reg_tests/scipy_layout_opt_regression.py tests/reg_tests/random_search_layout_opt_regression_test.py -q`.

### Task 5: Run final verification

**Files:** Verify all files changed in Tasks 1–4.

**Interfaces:** Consumes the complete implementation and produces evidence ready for review.

- [ ] **Step 1: Compile and lint.** Run `python -m py_compile floris/optimization/layout_optimization/layout_optimization_base.py floris/optimization/layout_optimization/layout_optimization_gridded.py floris/optimization/layout_optimization/layout_optimization_scipy.py floris/optimization/layout_optimization/layout_optimization_random_search.py tests/layout_optimization_integration_test.py` and `ruff floris/optimization/layout_optimization tests/layout_optimization_integration_test.py`; fix only feature-scoped findings.
- [ ] **Step 2: Run the full suite.** Run `pytest`; record unrelated pre-existing failures separately instead of changing unrelated code.
- [ ] **Step 3: Inspect the final diff.** Run `git diff --check`, `git status --short`, and `git diff --stat`; confirm only feature-scoped files are staged and user worktree files remain untouched.

