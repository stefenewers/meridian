"""The demand model's job is calibrated uncertainty, so that is what gets asserted."""

import numpy as np

from meridian.demand import generate_history, sample_scenario, train_quantile_models
from meridian.world import served_zone_ids

_HISTORY = generate_history(days=30, seed=3)
_MODEL = train_quantile_models(_HISTORY, seed=3)


def test_history_has_expected_shape():
    assert len(_HISTORY) > 0
    assert (_HISTORY["requests"] >= 0).all()


def test_quantiles_are_monotonic():
    """Independently fitted quantile regressors can cross; the grid must not let them."""
    grid = _MODEL.predict_grid(day_of_week=4, is_raining=False, is_event=False,
                               window_start_hour=21, horizon_minutes=360)
    assert (grid["p10"] <= grid["p50"] + 1e-9).all()
    assert (grid["p50"] <= grid["p90"] + 1e-9).all()


def test_interval_coverage_is_near_nominal():
    """If the P10-P90 band does not cover ~80%, the product's uncertainty bands mislead."""
    cov = _MODEL.metrics["coverage_p10_p90"]
    assert 0.65 <= cov <= 0.92, f"coverage {cov} is outside a usable range"


def test_scenario_sampling_is_seed_deterministic():
    grid = _MODEL.predict_grid(day_of_week=4, is_raining=False, is_event=False,
                               window_start_hour=21, horizon_minutes=360)
    served = set(served_zone_ids(expansion_enabled=False))
    a = sample_scenario(grid, centre="p50", seed=11, served=served)
    b = sample_scenario(grid, centre="p50", seed=11, served=served)
    c = sample_scenario(grid, centre="p50", seed=12, served=served)
    assert a == b
    assert a != c


def test_p90_scenarios_are_busier_than_p10():
    grid = _MODEL.predict_grid(day_of_week=4, is_raining=False, is_event=False,
                               window_start_hour=21, horizon_minutes=360)
    served = set(served_zone_ids(expansion_enabled=False))
    lo = sum(sample_scenario(grid, centre="p10", seed=5, served=served).values())
    hi = sum(sample_scenario(grid, centre="p90", seed=5, served=served).values())
    assert hi > lo


def test_expansion_zones_only_appear_when_enabled():
    grid = _MODEL.predict_grid(day_of_week=4, is_raining=False, is_event=False,
                               window_start_hour=21, horizon_minutes=360)
    off = sample_scenario(grid, centre="p50", seed=1, served=set(served_zone_ids(expansion_enabled=False)))
    on = sample_scenario(grid, centre="p50", seed=1, served=set(served_zone_ids(expansion_enabled=True)))
    assert not any(z == "MB-09" for z, _ in off)
    assert any(z == "MB-09" for z, _ in on)
