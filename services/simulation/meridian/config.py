"""Experiment configuration: the versioned, human-readable contract for a run.

Every experiment is fully described by this object. It is what gets stored, diffed,
shown in the UI's YAML preview, and hashed into the run's input snapshot. If a field is
not here, it cannot influence a result, which is what makes runs reproducible.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DispatchPolicy = Literal["nearest_available", "demand_aware"]
Percentile = Literal["p10", "p50", "p90"]

POLICY_VERSION = "dispatch-2026.02.1"
SIM_ENGINE_VERSION = "meridian-sim-0.1.0"


class FleetConfig(BaseModel):
    vehicles: int = Field(220, ge=20, le=1200, description="Vehicles available at window start.")
    depots: int = Field(2, ge=1, le=2, description="Depots in service. Meridian Bay has two.")
    chargers: int = Field(36, ge=4, le=200, description="Charging stalls across all depots.")
    starting_soc: float = Field(0.70, ge=0.3, le=1.0, description="Mean battery state of charge at window start. The fleet has already worked the evening peak.")


class PolicyConfig(BaseModel):
    dispatch: DispatchPolicy = "nearest_available"
    airport_priority: bool = Field(False, description="Hold a queue position and vehicles for airport demand.")
    airport_battery_reserve: float = Field(
        0.0, ge=0.0, le=0.6,
        description="Fraction of SoC withheld above the minimum so a vehicle can take an airport trip.",
    )
    demand_aware_repositioning: bool = Field(False, description="Move idle vehicles toward forecast demand.")
    service_area_expansion: bool = Field(False, description="Add the three expansion zones to the service area.")


class DemandConfig(BaseModel):
    percentile: Percentile = Field("p50", description="Which forecast quantile centres the scenario.")
    rain: bool = Field(False, description="Wet-weather demand multiplier and slower speeds.")
    event_surge: bool = Field(False, description="Stadium event letting out inside the window.")
    day_of_week: int = Field(4, ge=0, le=6, description="0=Monday. The flagship experiment uses Friday.")


class RunConfig(BaseModel):
    replications: int = Field(20, ge=1, le=200, description="Independent scenario draws per arm.")
    seed: int = Field(20260214, description="Root seed. Same seed plus same config gives the same result.")
    horizon_minutes: int = Field(360, ge=60, le=1440, description="Length of the simulated window.")
    window_start_hour: int = Field(21, ge=0, le=23, description="Local hour the window opens.")


class ArmConfig(BaseModel):
    """One side of the comparison. An experiment always runs two."""
    label: str
    fleet: FleetConfig = Field(default_factory=FleetConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)


class Targets(BaseModel):
    """What "good" means for this decision. Recommendations are graded against these."""
    p50_pickup_minutes: float = Field(5.5, gt=0)
    p90_pickup_minutes: float = Field(7.0, gt=0, description="The seven-minute airport target.")
    max_completion_loss_pct: float = Field(0.0, description="Proposed must not complete fewer trips than baseline by more than this.")
    max_charger_queue_minutes: float = Field(12.0, gt=0)


class ExperimentConfig(BaseModel):
    id: str
    title: str
    question: str
    owner: str = "ops-strategy"
    config_version: str = "1.0.0"
    baseline: ArmConfig
    proposed: ArmConfig
    demand: DemandConfig = Field(default_factory=DemandConfig)
    run: RunConfig = Field(default_factory=RunConfig)
    targets: Targets = Field(default_factory=Targets)

    @model_validator(mode="after")
    def _check_arms_differ(self) -> "ExperimentConfig":
        # Compare what the simulation actually reads. Labels are for humans, so two arms
        # that differ only by name still compare a configuration to itself.
        def substantive(arm: ArmConfig) -> dict:
            return {"fleet": arm.fleet.model_dump(), "policy": arm.policy.model_dump()}

        if substantive(self.baseline) == substantive(self.proposed):
            raise ValueError("baseline and proposed are identical; the experiment would answer nothing")
        return self

    @model_validator(mode="after")
    def _check_reserve_needs_priority(self) -> "ExperimentConfig":
        for arm in (self.baseline, self.proposed):
            p = arm.policy
            if p.airport_battery_reserve > 0 and not p.airport_priority:
                raise ValueError(
                    f"arm '{arm.label}': airport_battery_reserve is set but airport_priority is off, "
                    "so the reserve would never be claimed"
                )
        return self

    def input_snapshot_hash(self) -> str:
        """Stable digest of everything that can change a result. Shown as the run's input snapshot."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:12]
