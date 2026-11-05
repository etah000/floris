import numpy as np

from floris import FlorisModel, ParFlorisModel, WindRose


def test_parallel_progress_preserves_aep():
    rose = WindRose(
        wind_directions=np.array([0.0, 90.0]),
        wind_speeds=np.array([8.0, 9.0]),
        freq_table=np.array([[0.1, 0.2], [0.3, 0.4]]),
        ti_table=0.06,
    )
    model = ParFlorisModel(
        FlorisModel("defaults"), max_workers=2, n_wind_condition_splits=4,
    )
    model.set(layout_x=[0.0, 500.0], layout_y=[0.0, 0.0], wind_data=rose)
    model.run()
    expected = model.get_expected_turbine_powers()
    events = []
    model.run(progress_callback=lambda completed, total: events.append((completed, total)))
    np.testing.assert_allclose(model.get_expected_turbine_powers(), expected)
    assert events == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]
