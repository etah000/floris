# Layout Optimization Polygon Holes Design

## Goal

Extend the existing `boundaries` argument accepted by FLORIS layout optimizers so it can
receive `list[shapely.geometry.Polygon]`. Polygon interiors must remain excluded from turbine
placement. The gridded, SciPy, and random-search optimizers must use the resulting solid geometry
for their existing grid packing and refinement behavior.

## Scope

The change applies to `LayoutOptimizationGridded`, `LayoutOptimizationScipy`, and
`LayoutOptimizationRandomSearch`. The existing coordinate-list formats remain supported:

- `list[tuple[float, float]]` for one region;
- `list[list[tuple[float, float]]]` for multiple disjoint regions.

The new format is a non-empty, homogeneous `list[Polygon]`. Polygon interiors are interpreted as
holes. Multiple polygons are merged with `shapely.ops.unary_union`; overlapping areas are counted
once, and the result may be a `Polygon` or `MultiPolygon`.

## Geometry normalization

`LayoutOptimization` remains the single normalization boundary. It will validate the input and
construct one internal Shapely geometry:

- coordinate lists are converted to Polygon objects;
- Polygon lists are validated and unioned;
- invalid Polygon inputs raise `ValueError` rather than being repaired implicitly;
- empty, malformed, or mixed coordinate/Polygon inputs raise clear `ValueError` or `TypeError`;
- an empty or unsupported union result raises `ValueError`.

The public `boundaries` attribute retains the caller's original value for compatibility. Internal
consumers use `_boundary_polygon`, `_boundary_line`, and the bounds derived from the normalized
geometry. Boundary and hole edges retain the existing `contains` semantics: points on either edge
are not valid placement points.

## Optimizer behavior

`LayoutOptimizationGridded` and `LayoutOptimizationRandomSearch` continue to use point containment
against `_boundary_polygon`; holes are therefore excluded without a raster resolution or mask
approximation.

`LayoutOptimizationScipy` no longer rejects multiple regions. It stops deriving normalized
vertices from `self.boundaries` and instead uses the normalized geometry and its total bounding box.
Its boundary constraint remains signed by containment, so points in holes and outside all regions
are infeasible while points in any union component are feasible.

Boundary plotting will support both Polygon and MultiPolygon normalized results, including hole
boundaries. No unrelated optimizer redesign is included. Existing consumers that use the base
geometry for containment continue to receive the normalized geometry; optimizer-specific code that
requires raw vertices is outside this feature's scope unless needed to prevent a regression.

## Testing and acceptance

Add focused tests for:

1. A Polygon with a hole, verifying gridded and random-search candidate/final points never lie in
   the hole.
2. Multiple overlapping and disjoint Polygons, verifying union semantics and access to all
   components.
3. SciPy optimization with a MultiPolygon and a hole, verifying construction succeeds and the
   signed boundary constraint rejects hole points.
4. Existing coordinate-list formats and current gridded behavior, including separate regions and
   hexagonal packing.
5. Empty lists, mixed input types, and invalid Polygons with the specified exception types.

Run the targeted layout-optimization tests and compilation/static checks. Run the full test suite
when practical. The primary acceptance condition is that no optimizer returns or accepts a turbine
location outside the normalized solid geometry, including its holes.

