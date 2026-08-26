"""End-to-end guarantees: reproducibility, paired arms, and honest labelling."""

import pytest

from meridian.demand import generate_history, train_quantile_models
from meridian.library import list_experiments, load_by_id
from meridian.runner import execute

_MODEL = train_quantile_models(generate_history(days=24, seed=2), seed=2)


@pytest.fixture(scope="module")
def small_cfg():
    cfg = load_by_id("late-night-airport-expansion")
    cfg.run.replications = 2
    cfg.run.horizon_minutes = 120
    return cfg


def test_every_shipped_experiment_validates():
    experiments = list_experiments()
    assert len(experiments) >= 4
    for cfg in experiments:
        assert cfg.id and cfg.title and cfg.question


def test_run_is_reproducible(small_cfg):
    a = execute(small_cfg, model=_MODEL).to_dict()
    b = execute(small_cfg, model=_MODEL).to_dict()
    assert a["baseline"] == b["baseline"]
    assert a["proposed"] == b["proposed"]
    assert a["recommendation"]["verdict"] == b["recommendation"]["verdict"]


def test_seed_change_changes_results(small_cfg):
    a = execute(small_cfg, model=_MODEL).to_dict()
    other = small_cfg.model_copy(deep=True)
    other.run.seed += 991
    b = execute(other, model=_MODEL).to_dict()
    assert a["baseline"] != b["baseline"]


def test_output_carries_full_provenance(small_cfg):
    out = execute(small_cfg, model=_MODEL).to_dict()
    p = out["provenance"]
    for key in ("seed", "replications", "input_snapshot", "policy_version",
                "demand_model_version", "sim_engine_version"):
        assert p.get(key), f"missing provenance field {key}"
    assert "Simulated" in p["disclaimer"]


def test_metrics_are_intervals_not_points(small_cfg):
    out = execute(small_cfg, model=_MODEL).to_dict()
    m = out["baseline"]["completion_rate"]
    assert {"mean", "p10", "p50", "p90"} <= set(m)
    assert m["p10"] <= m["p90"]


def test_verdict_is_one_of_three(small_cfg):
    out = execute(small_cfg, model=_MODEL).to_dict()
    assert out["recommendation"]["verdict"] in {"launch", "pilot", "do_not_launch"}
    assert out["recommendation"]["guardrails"]
