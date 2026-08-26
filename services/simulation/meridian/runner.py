"""Orchestration: config in, decision out.

A run is N independent replications per arm. Both arms of a replication see the *same*
demand draw, which is what makes the comparison paired: any difference between them is
policy, not luck of the weather. Seeds derive deterministically from the root seed and
the replication index, so a run id can be replayed exactly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from . import __version__
from .config import POLICY_VERSION, SIM_ENGINE_VERSION, ArmConfig, ExperimentConfig
from .demand import INTERVAL_MINUTES, DemandModel, sample_scenario
from .metrics import ArmMetrics, Interval, aggregate, aggregate_zones, summarise
from .model_store import load_model
from .recommend import Recommendation
from .recommend import build as build_recommendation
from .sim import FleetSim
from .world import ZONES_BY_ID, served_zone_ids


@dataclass
class RunOutput:
    run_id: str
    experiment_id: str
    created_at: float
    config: dict
    baseline: dict[str, Interval]
    proposed: dict[str, Interval]
    baseline_zones: dict[str, dict[str, float]]
    proposed_zones: dict[str, dict[str, float]]
    recommendation: Recommendation
    provenance: dict
    replication_samples: dict[str, list[float]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "created_at": self.created_at,
            "config": self.config,
            "baseline": {k: v.to_dict() for k, v in self.baseline.items()},
            "proposed": {k: v.to_dict() for k, v in self.proposed.items()},
            "baseline_zones": self.baseline_zones,
            "proposed_zones": self.proposed_zones,
            "zones": [
                {"id": z.id, "name": z.name, "x": z.x, "y": z.y, "tier": str(z.tier)}
                for z in ZONES_BY_ID.values()
            ],
            "recommendation": self.recommendation.to_dict(),
            "provenance": self.provenance,
            "replication_samples": self.replication_samples,
        }


def make_run_id(cfg: ExperimentConfig) -> str:
    """Deterministic in the config, unique per wall-clock submission."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"run-{stamp}-{cfg.input_snapshot_hash()[:6]}"


def _run_arm(
    arm: ArmConfig, cfg: ExperimentConfig, model: DemandModel, rep: int
) -> ArmMetrics:
    served = set(served_zone_ids(expansion_enabled=arm.policy.service_area_expansion))
    grid = model.predict_grid(
        day_of_week=cfg.demand.day_of_week,
        is_raining=cfg.demand.rain,
        is_event=cfg.demand.event_surge,
        window_start_hour=cfg.run.window_start_hour,
        horizon_minutes=cfg.run.horizon_minutes,
    )
    # Same replication index -> same demand seed, so both arms face the same night.
    demand_seed = cfg.run.seed * 1_000_003 + rep
    arrivals = sample_scenario(grid, centre=cfg.demand.percentile, seed=demand_seed, served=served)
    forecast_p50 = {
        (r.zone_id, int(r.interval)): float(r.p50)
        for r in grid.itertuples(index=False)
        if r.zone_id in served
    }
    rng = np.random.default_rng(demand_seed + 17)
    sim = FleetSim(
        arm=arm, demand_cfg=cfg.demand, run_cfg=cfg.run,
        arrivals=arrivals, forecast_p50=forecast_p50, served=served, rng=rng,
    )
    return summarise(sim.run(), arm=arm, run=cfg.run)


def execute(cfg: ExperimentConfig, *, model: DemandModel | None = None) -> RunOutput:
    model = model or load_model()
    base_runs: list[ArmMetrics] = []
    prop_runs: list[ArmMetrics] = []
    for rep in range(cfg.run.replications):
        base_runs.append(_run_arm(cfg.baseline, cfg, model, rep))
        prop_runs.append(_run_arm(cfg.proposed, cfg, model, rep))

    base_agg = aggregate(base_runs)
    prop_agg = aggregate(prop_runs)
    rec = build_recommendation(cfg, base_agg, prop_agg)

    # Per-replication series power the uncertainty chart in the results view.
    keys = ("airport_p90_pickup_minutes", "p90_charge_queue_minutes",
            "completion_rate", "cost_per_completed_trip")
    samples: dict[str, list[float]] = {}
    for k in keys:
        samples[f"baseline.{k}"] = [float(getattr(r, k)) for r in base_runs]
        samples[f"proposed.{k}"] = [float(getattr(r, k)) for r in prop_runs]

    return RunOutput(
        run_id=make_run_id(cfg),
        experiment_id=cfg.id,
        created_at=time.time(),
        config=cfg.model_dump(mode="json"),
        baseline=base_agg,
        proposed=prop_agg,
        baseline_zones=aggregate_zones(base_runs),
        proposed_zones=aggregate_zones(prop_runs),
        recommendation=rec,
        provenance={
            "seed": cfg.run.seed,
            "replications": cfg.run.replications,
            "input_snapshot": cfg.input_snapshot_hash(),
            "config_version": cfg.config_version,
            "policy_version": POLICY_VERSION,
            "demand_model_version": model.version,
            "sim_engine_version": SIM_ENGINE_VERSION,
            "package_version": __version__,
            "demand_model_metrics": model.metrics or {},
            "interval_minutes": INTERVAL_MINUTES,
            "disclaimer": "Simulated output from synthetic demand. Not observed fleet performance.",
        },
        replication_samples=samples,
    )
