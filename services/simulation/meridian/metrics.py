"""Turning raw simulation output into the numbers an operator actually argues about."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

from .config import ArmConfig, RunConfig
from .sim import SimResult

# Illustrative unit economics for a fictional fleet. These drive cost-per-trip and
# nothing else; they are stated in docs/assumptions.md and are not benchmarks.
COST_PER_VEHICLE_HOUR = 4.10     # depreciation, insurance, remote ops, overhead
COST_PER_MILE = 0.19             # energy, tyres, cleaning, maintenance
COST_PER_CHARGE_SESSION = 1.35   # depot handling


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass
class ArmMetrics:
    """One replication's outcome, in the units the decision is made in."""
    completed_trips: int
    canceled_trips: int
    requested_trips: int
    completion_rate: float
    median_pickup_minutes: float
    p90_pickup_minutes: float
    airport_median_pickup_minutes: float   # curbside at the terminal, origin-side only
    airport_p90_pickup_minutes: float
    vehicle_utilization: float
    empty_miles: float
    loaded_miles: float
    deadhead_ratio: float
    charge_sessions: int
    median_charge_queue_minutes: float
    p90_charge_queue_minutes: float
    constrained_vehicle_hours: float
    cost_per_completed_trip: float
    zone_service: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def summarise(result: SimResult, *, arm: ArmConfig, run: RunConfig) -> ArmMetrics:
    horizon_hours = run.horizon_minutes / 60.0
    fleet_hours = arm.fleet.vehicles * horizon_hours
    total_miles = result.loaded_miles + result.empty_miles

    operating_cost = (
        fleet_hours * COST_PER_VEHICLE_HOUR
        + total_miles * COST_PER_MILE
        + result.charge_sessions * COST_PER_CHARGE_SESSION
    )
    completed = max(result.completed, 1)

    zone_service: dict[str, dict[str, float]] = {}
    for zid, b in result.zone_stats.items():
        req = b["requested"] or 1.0
        zone_service[zid] = {
            "requested": b["requested"],
            "completed": b["completed"],
            "canceled": b["canceled"],
            "completion_rate": round(b["completed"] / req, 4),
            "mean_pickup_minutes": round(b["wait_sum"] / b["wait_n"], 2) if b["wait_n"] else 0.0,
        }

    return ArmMetrics(
        completed_trips=result.completed,
        canceled_trips=result.canceled,
        requested_trips=result.requested,
        completion_rate=round(result.completed / max(result.requested, 1), 4),
        median_pickup_minutes=round(_pct(result.pickup_waits, 0.5), 2),
        p90_pickup_minutes=round(_pct(result.pickup_waits, 0.9), 2),
        airport_median_pickup_minutes=round(_pct(result.airport_pickup_waits, 0.5), 2),
        airport_p90_pickup_minutes=round(_pct(result.airport_pickup_waits, 0.9), 2),
        vehicle_utilization=round(result.vehicle_busy_minutes / max(fleet_hours * 60.0, 1.0), 4),
        empty_miles=round(result.empty_miles, 1),
        loaded_miles=round(result.loaded_miles, 1),
        deadhead_ratio=round(result.empty_miles / max(total_miles, 1.0), 4),
        charge_sessions=result.charge_sessions,
        median_charge_queue_minutes=round(_pct(result.charge_queue_waits, 0.5), 2),
        p90_charge_queue_minutes=round(_pct(result.charge_queue_waits, 0.9), 2),
        constrained_vehicle_hours=round(result.constrained_vehicle_minutes / 60.0, 2),
        cost_per_completed_trip=round(operating_cost / completed, 3),
        zone_service=zone_service,
    )


@dataclass
class Interval:
    """Mean with a percentile band across replications. Never a single number."""
    mean: float
    p10: float
    p50: float
    p90: float

    def to_dict(self) -> dict:
        return asdict(self)


def aggregate(runs: list[ArmMetrics]) -> dict[str, Interval]:
    """Collapse replications into intervals, one per scalar metric."""
    if not runs:
        return {}
    fields = [
        k for k, v in runs[0].to_dict().items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    out: dict[str, Interval] = {}
    for f in fields:
        vals = [float(getattr(r, f)) for r in runs]
        out[f] = Interval(
            mean=round(statistics.fmean(vals), 3),
            p10=round(_pct(vals, 0.1), 3),
            p50=round(_pct(vals, 0.5), 3),
            p90=round(_pct(vals, 0.9), 3),
        )
    return out


def aggregate_zones(runs: list[ArmMetrics]) -> dict[str, dict[str, float]]:
    """Mean zone-level service across replications."""
    acc: dict[str, dict[str, list[float]]] = {}
    for r in runs:
        for zid, stats in r.zone_service.items():
            for k, v in stats.items():
                acc.setdefault(zid, {}).setdefault(k, []).append(float(v))
    return {
        zid: {k: round(statistics.fmean(vs), 3) for k, vs in stats.items()}
        for zid, stats in acc.items()
    }
