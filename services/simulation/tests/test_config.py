"""Config is the reproducibility contract, so its guarantees are tested directly."""

import pytest
from pydantic import ValidationError

from meridian.config import ArmConfig, ExperimentConfig, FleetConfig, PolicyConfig


def _cfg(**over) -> ExperimentConfig:
    base = dict(
        id="t", title="t", question="q",
        baseline=ArmConfig(label="base"),
        proposed=ArmConfig(label="prop", policy=PolicyConfig(dispatch="demand_aware")),
    )
    base.update(over)
    return ExperimentConfig(**base)


def test_identical_arms_are_rejected():
    with pytest.raises(ValidationError, match="answer nothing"):
        ExperimentConfig(id="t", title="t", question="q",
                         baseline=ArmConfig(label="a"), proposed=ArmConfig(label="b"))


def test_battery_reserve_without_priority_is_rejected():
    """A reserve that can never be claimed is a silent no-op, which is worse than an error."""
    with pytest.raises(ValidationError, match="airport_priority is off"):
        ExperimentConfig(
            id="t", title="t", question="q",
            baseline=ArmConfig(label="a"),
            proposed=ArmConfig(label="b", policy=PolicyConfig(
                dispatch="demand_aware", airport_priority=False, airport_battery_reserve=0.2)),
        )


def test_snapshot_hash_is_stable_and_sensitive():
    a, b = _cfg(), _cfg()
    assert a.input_snapshot_hash() == b.input_snapshot_hash()
    c = _cfg()
    c.run.seed += 1
    assert c.input_snapshot_hash() != a.input_snapshot_hash()


def test_fleet_bounds_are_enforced():
    with pytest.raises(ValidationError):
        FleetConfig(vehicles=0)
    with pytest.raises(ValidationError):
        FleetConfig(chargers=-1)
