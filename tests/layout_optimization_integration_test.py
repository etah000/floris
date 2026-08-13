import logging
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from floris import (
    FlorisModel,
    TimeSeries,
    WindRose,
)
from floris.optimization.layout_optimization.layout_optimization_base import (
    LayoutOptimization,
)
from floris.optimization.layout_optimization.layout_optimization_gridded import (
    LayoutOptimizationGridded,
)
from floris.optimization.layout_optimization.layout_optimization_random_search import (
    LayoutOptimizationRandomSearch,
    test_point_in_bounds as point_in_bounds,
)
from floris.optimization.layout_optimization.layout_optimization_scipy import (
    LayoutOptimizationScipy,
)
from floris.wind_data import WindDataBase


TEST_DATA = Path(__file__).resolve().parent / "data"
YAML_INPUT = TEST_DATA / "input_full.yaml"

test_boundaries = [(0.0, 0.0), (0.0, 1000.0), (1000.0, 1000.0), (1000.0, 0.0), (0.0, 0.0)]

site_polygon = Polygon(
    shell=[(0.0, 0.0), (0.0, 1000.0), (1000.0, 1000.0), (1000.0, 0.0)],
    holes=[[(400.0, 400.0), (400.0, 600.0), (600.0, 600.0), (600.0, 400.0)]],
)


def test_base_class(caplog):
    # Get a test fi
    fmodel = FlorisModel(configuration=YAML_INPUT)

    # Now initiate layout optimization with a frequency matrix passed in the 3rd position
    # (this should fail)
    freq = np.ones((5, 5))
    freq = freq / freq.sum()

    # Check that warning is raised if fmodel does not contain wind_data
    with caplog.at_level(logging.WARNING):
        LayoutOptimization(fmodel, test_boundaries, 5)
    assert caplog.text != "" # Checking not empty

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        LayoutOptimization(fmodel=fmodel, boundaries=test_boundaries, min_dist=5,)
    assert caplog.text != "" # Checking not empty

    time_series = TimeSeries(
        wind_directions=fmodel.core.flow_field.wind_directions,
        wind_speeds=fmodel.core.flow_field.wind_speeds,
        turbulence_intensities=fmodel.core.flow_field.turbulence_intensities,
    )
    fmodel.set(wind_data=time_series)

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        LayoutOptimization(fmodel, test_boundaries, 5)
    assert caplog.text != "" # Not empty, because get_farm_AEP called on TimeSeries

    # Passing without keyword arguments should work, or with keyword arguments
    LayoutOptimization(fmodel, test_boundaries, 5)
    LayoutOptimization(fmodel=fmodel, boundaries=test_boundaries, min_dist=5)

    # Check with WindRose on fmodel
    fmodel.set(wind_data=time_series.to_WindRose())

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        LayoutOptimization(fmodel, test_boundaries, 5)
    assert caplog.text == "" # Empty

    LayoutOptimization(fmodel, test_boundaries, 5)
    LayoutOptimization(fmodel=fmodel, boundaries=test_boundaries, min_dist=5)

def test_LayoutOptimizationRandomSearch():
    fmodel = FlorisModel(configuration=YAML_INPUT)
    fmodel.set(layout_x=[0, 500], layout_y=[0, 0])

    layout_opt = LayoutOptimizationRandomSearch(
        fmodel=fmodel,
        boundaries=test_boundaries,
        min_dist_D=5,
        seconds_per_iteration=1,
        total_optimization_seconds=1,
        use_dist_based_init=False,
    )

    # Check that the optimization runs
    layout_opt.optimize()

def test_LayoutOptimizationGridded_initialization(caplog):
    fmodel = FlorisModel(configuration=YAML_INPUT)
    fmodel.set(layout_x=[0, 500], layout_y=[0, 0])

    with pytest.raises(ValueError):
        LayoutOptimizationGridded(
            fmodel=fmodel,
            boundaries=test_boundaries,
            min_dist=None,
            min_dist_D=None,
        ) # No min_dist specified
    with pytest.raises(ValueError):
        LayoutOptimizationGridded(
            fmodel=fmodel,
            boundaries=test_boundaries,
            min_dist=500,
            min_dist_D=5
        ) # min_dist specified in two ways

    fmodel.core.farm.rotor_diameters[1] = 100.0
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        LayoutOptimizationGridded(
            fmodel,
            test_boundaries,
            min_dist_D=5
        )

def test_LayoutOptimizationGridded_basic():
    fmodel = FlorisModel(configuration=YAML_INPUT)

    min_dist = 60

    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=test_boundaries,
        min_dist=min_dist,
        rotation_step=5,
        rotation_range=(0, 360),
        translation_step=50,
        hexagonal_packing=False,
    )

    n_turbs_opt, x_opt, y_opt = layout_opt.optimize()

    # Check that the number of turbines is correct
    assert n_turbs_opt == len(x_opt)

    # Check that min_dist is respected
    xx_diff = x_opt.reshape(-1,1) - x_opt.reshape(1,-1)
    yy_diff = y_opt.reshape(-1,1) - y_opt.reshape(1,-1)
    dists = np.sqrt(xx_diff**2 + yy_diff**2)
    dists[np.arange(0, len(dists), 1), np.arange(0, len(dists), 1)] = np.inf
    assert (dists > min_dist - 1e-6).all()

    # Check all are indeed in bounds
    assert (np.all(x_opt > 0.0) & np.all(x_opt < 1000.0)
            & np.all(y_opt > 0.0) & np.all(y_opt < 1000.0))

    # Check that the layout is at least as good as the basic rectangular fill
    n_turbs_subopt = (1000 // min_dist + 1) ** 2

    assert n_turbs_opt >= n_turbs_subopt

def test_LayoutOptimizationGridded_diagonal():
    fmodel = FlorisModel(configuration=YAML_INPUT)

    turbine_spacing = 1000.0
    corner = 2*turbine_spacing / np.sqrt(2)

    # Create a "thin" boundary area at a 45 degree angle
    boundaries_diag = [
        (0.0, 0.0),
        (0.0, 100.0),
        (corner, corner+100.0),
        (corner+100.0, corner+100.0),
        (0.0, 0.0)
    ]

    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=boundaries_diag,
        min_dist=turbine_spacing,
        rotation_step=45, # To speed up test
        rotation_range=(0, 360),
        translation_step=50,
        hexagonal_packing=False,
    )

    n_turbs_opt, x_opt, y_opt = layout_opt.optimize()

    # Confirm that spacing is respected
    xx_diff = x_opt.reshape(-1,1) - x_opt.reshape(1,-1)
    yy_diff = y_opt.reshape(-1,1) - y_opt.reshape(1,-1)
    dists = np.sqrt(xx_diff**2 + yy_diff**2)
    dists[np.arange(0, len(dists), 1), np.arange(0, len(dists), 1)] = np.inf
    assert (dists > turbine_spacing - 1e-6).all()

    assert n_turbs_opt == 3 # 3 should fit in the diagonal

    # Test a limited range of rotation
    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=boundaries_diag,
        min_dist=turbine_spacing,
        rotation_step=5,
        rotation_range=(0, 10),
        translation_step=50,
        hexagonal_packing=False,
    )
    n_turbs_opt, x_opt, y_opt = layout_opt.optimize()
    assert n_turbs_opt < 3

    # Test a coarse rotation
    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=boundaries_diag,
        min_dist=turbine_spacing,
        rotation_step=60, # Not fine enough to find ideal 45 deg rotation
        rotation_range=(0, 360),
        translation_step=50,
        hexagonal_packing=False,
    )
    n_turbs_opt, x_opt, y_opt = layout_opt.optimize()
    assert n_turbs_opt < 3

    # Test a coarse translation
    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=boundaries_diag,
        min_dist=turbine_spacing,
        rotation_step=45,
        rotation_range=(0, 10),
        translation_step=300,
        hexagonal_packing=False,
    )
    n_turbs_opt, x_opt, y_opt = layout_opt.optimize()
    assert n_turbs_opt < 3

def test_LayoutOptimizationGridded_separate_boundaries():
    fmodel = FlorisModel(configuration=YAML_INPUT)
    separate_boundaries = [
        [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0), (0.0, 0.0)],
        [(200.0, 0.0), (200.0, 100.0), (300.0, 100.0), (300.0, 0.0), (200.0, 0.0)]
    ]

    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=separate_boundaries,
        min_dist=150,
        rotation_step=5,
        rotation_range=(0, 360),
        translation_step=50,
        hexagonal_packing=False,
    )

    n_turbs_opt, x_opt, y_opt = layout_opt.optimize()
    assert n_turbs_opt == 2 # One in each of the boundary areas

    # Check they're inside as expected
    assert ((0.0 <= y_opt) & (y_opt <= 100.0)).all()
    assert (((0.0 <= x_opt) & (x_opt <= 100.0)) | ((200.0 <= x_opt) & (x_opt <= 300.0))).all()


def test_LayoutOptimizationGridded_hexagonal():
    fmodel = FlorisModel(configuration=YAML_INPUT)

    spacing = 200

    # First, run a square layout
    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=test_boundaries,
        min_dist=spacing,
        rotation_step=5,
        rotation_range=(0, 360),
        translation_step=50,
        hexagonal_packing=False,
    )
    n_turbs_opt_square = layout_opt.optimize()[0]

    # Now, run a hexagonal layout
    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=test_boundaries,
        min_dist=spacing,
        rotation_step=5,
        rotation_range=(0, 360),
        translation_step=50,
        hexagonal_packing=True,
    )
    n_turbs_opt_hex = layout_opt.optimize()[0]

    # Check that the hexagonal layout is better
    assert n_turbs_opt_hex >= n_turbs_opt_square


def test_layout_optimization_gridded_polygon_hole():
    fmodel = FlorisModel(configuration=YAML_INPUT)
    layout_opt = LayoutOptimizationGridded(
        fmodel=fmodel,
        boundaries=[site_polygon],
        min_dist=200,
        rotation_step=90,
        rotation_range=(0, 90),
        translation_step=100,
        hexagonal_packing=False,
    )

    _, x_opt, y_opt = layout_opt.optimize()

    assert len(x_opt) > 0
    assert all(site_polygon.contains(Point(x, y)) for x, y in zip(x_opt, y_opt))
    assert not layout_opt._boundary_polygon.contains(Point(500.0, 500.0))
    assert not point_in_bounds(500.0, 500.0, layout_opt._boundary_polygon)


def test_layout_optimization_polygon_union_and_validation():
    fmodel = FlorisModel(configuration=YAML_INPUT)
    overlapping = [
        Polygon([(0, 0), (0, 100), (100, 100), (100, 0)]),
        Polygon([(50, 0), (50, 100), (150, 100), (150, 0)]),
    ]
    disjoint = [
        Polygon([(0, 0), (0, 100), (100, 100), (100, 0)]),
        Polygon([(200, 0), (200, 100), (300, 100), (300, 0)]),
    ]

    overlapping_opt = LayoutOptimization(fmodel, overlapping, min_dist=5)
    disjoint_opt = LayoutOptimization(fmodel, disjoint, min_dist=5)

    assert overlapping_opt._boundary_polygon.geom_type == "Polygon"
    assert disjoint_opt._boundary_polygon.geom_type == "MultiPolygon"
    assert len(disjoint_opt._boundary_polygon.geoms) == 2

    with pytest.raises(ValueError):
        LayoutOptimization(fmodel, [], min_dist=5)
    with pytest.raises(TypeError):
        LayoutOptimization(fmodel, [overlapping[0], [(0.0, 0.0)]], min_dist=5)
    with pytest.raises(ValueError):
        LayoutOptimization(
            fmodel,
            [Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])],
            min_dist=5,
        )


def test_layout_optimization_scipy_polygon_hole_and_disjoint_regions():
    fmodel = FlorisModel(configuration=YAML_INPUT)
    fmodel.set(layout_x=[100, 500], layout_y=[100, 500])
    disjoint_with_hole = [
        site_polygon,
        Polygon([(1200, 0), (1200, 100), (1300, 100), (1300, 0)]),
    ]

    layout_opt = LayoutOptimizationScipy(
        fmodel=fmodel,
        boundaries=disjoint_with_hole,
        min_dist=5,
        solver=None,
    )

    hole_and_valid = [
        layout_opt._norm(100, layout_opt.xmin, layout_opt.xmax),
        layout_opt._norm(500, layout_opt.xmin, layout_opt.xmax),
        layout_opt._norm(100, layout_opt.ymin, layout_opt.ymax),
        layout_opt._norm(500, layout_opt.ymin, layout_opt.ymax),
    ]
    boundary_distances = layout_opt._distance_from_boundaries(hole_and_valid)
    assert boundary_distances[1] < 0
    assert boundary_distances[0] > 0


def test_layout_optimization_random_search_polygon_hole():
    fmodel = FlorisModel(configuration=YAML_INPUT)
    fmodel.set(layout_x=[100, 200], layout_y=[100, 100])
    layout_opt = LayoutOptimizationRandomSearch(
        fmodel=fmodel,
        boundaries=[site_polygon],
        min_dist_D=1,
        n_individuals=1,
        seconds_per_iteration=0.01,
        total_optimization_seconds=0.01,
        interface=None,
        relegation_number=0,
        grid_step_size=200,
        random_seed=1,
        use_dist_based_init=True,
    )

    _, x_opt, y_opt = layout_opt._test_optimize()

    assert all(site_polygon.contains(Point(x, y)) for x, y in zip(x_opt, y_opt))
    assert point_in_bounds(100.0, 100.0, layout_opt._boundary_polygon)
    assert not point_in_bounds(500.0, 500.0, layout_opt._boundary_polygon)
    assert not point_in_bounds(1100.0, 100.0, layout_opt._boundary_polygon)
