"""The discrete-event simulation: one night of fleet operations, one arm, one draw.

Time advances in 15-minute dispatch ticks. Within a tick, requests that arrived are
queued, the policy assigns whatever it can, and vehicles that finished a trip or a charge
become available again. Vehicles are SimPy processes; chargers are a SimPy Resource whose
capacity is the experiment's charger count, which is what produces queueing rather than
assuming it away.

What is modelled: pickup travel, trip travel, energy draw, charge decisions, charger
contention, request abandonment, service-area membership, airport policy.

What is not modelled: traffic, road networks, rider behaviour beyond a patience
threshold, vehicle faults, remote assistance, and anything to do with autonomous driving
itself. See docs/assumptions.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import simpy

from .config import ArmConfig, DemandConfig, RunConfig
from .demand import INTERVAL_MINUTES
from .dispatch import (
    SOC_PER_MILE,
    Candidate,
    PendingRequest,
    assign_demand_aware,
    assign_nearest_available,
    is_airport_request,
    reposition_targets,
)
from .world import (
    AIRPORT_ZONE_ID,
    INTRA_ZONE_MILES,
    ZONES_BY_ID,
    distance_miles,
    nearest_depot,
    travel_minutes,
    zone_distance,
)

# Dispatch runs far more often than the demand forecast is granular. The forecast is
# 15-minute; matching is near-continuous. Ticking the matcher at the forecast interval
# would batch every rider in a quarter hour into one instant and make wait times
# meaningless.
DISPATCH_TICK_MINUTES = 1.0
REPOSITION_EVERY_MINUTES = 15.0
# Crossing this metro takes longer than one forecast interval, so repositioning aims two
# intervals ahead. Aiming at the next interval sent vehicles that arrived after the peak
# they were dispatched for, which made the policy look worse than useless.
REPOSITION_LOOKAHEAD_INTERVALS = 2

MIN_SOC = 0.10               # below this a vehicle must charge
CHARGE_TRIGGER_SOC = 0.22    # at or below this an idle vehicle heads for a depot
CHARGE_TARGET_SOC = 0.80
CHARGE_RATE_PER_MIN = 0.0075  # ~90 minutes for a 10%->80% charge
RIDER_PATIENCE_MINUTES = 14.0
RAIN_SPEED_PENALTY = 1.12


@dataclass
class Trip:
    request_id: int
    origin: str
    dest: str
    requested_at: float
    is_airport: bool
    assigned_at: float | None = None
    picked_up_at: float | None = None
    completed_at: float | None = None
    pickup_miles: float = 0.0
    trip_miles: float = 0.0
    canceled: bool = False

    @property
    def pickup_wait(self) -> float | None:
        if self.picked_up_at is None or self.requested_at is None:
            return None
        return self.picked_up_at - self.requested_at


@dataclass
class Vehicle:
    id: int
    zone_id: str
    x: float
    y: float
    soc: float
    status: str = "idle"  # idle | to_pickup | on_trip | repositioning | to_depot | charging
    busy_minutes: float = 0.0
    loaded_miles: float = 0.0
    empty_miles: float = 0.0


@dataclass
class SimResult:
    completed: int = 0
    canceled: int = 0
    requested: int = 0
    pickup_waits: list[float] = field(default_factory=list)
    airport_pickup_waits: list[float] = field(default_factory=list)
    loaded_miles: float = 0.0
    empty_miles: float = 0.0
    charge_queue_waits: list[float] = field(default_factory=list)
    charge_sessions: int = 0
    vehicle_busy_minutes: float = 0.0
    zone_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    constrained_vehicle_minutes: float = 0.0


class FleetSim:
    def __init__(
        self,
        *,
        arm: ArmConfig,
        demand_cfg: DemandConfig,
        run_cfg: RunConfig,
        arrivals: dict[tuple[str, int], int],
        forecast_p50: dict[tuple[str, int], float],
        served: set[str],
        rng,
    ) -> None:
        self.arm = arm
        self.demand_cfg = demand_cfg
        self.run_cfg = run_cfg
        self.arrivals = arrivals
        self.forecast_p50 = forecast_p50
        self.served = served
        # Sorted once: any iteration that can influence a random draw must be ordered.
        self.served_order: list[str] = sorted(served)
        self.rng = rng
        self.env = simpy.Environment()
        self.chargers = simpy.Resource(self.env, capacity=arm.fleet.chargers)
        self.result = SimResult()
        self.trips: dict[int, Trip] = {}
        self.pending: list[Trip] = []
        self._next_request_id = 0
        self.speed_factor = RAIN_SPEED_PENALTY if demand_cfg.rain else 1.0

        self.arrival_plan = self._build_arrival_plan()

        self.vehicles: list[Vehicle] = []
        served_list = self.served_order
        weights = np.array([ZONES_BY_ID[z].peak_intensity for z in served_list], dtype=float)
        weights = weights / weights.sum()
        placements = rng.choice(len(served_list), size=arm.fleet.vehicles, p=weights)
        for i, idx in enumerate(placements):
            z = ZONES_BY_ID[served_list[int(idx)]]
            soc = min(1.0, max(0.22, rng.normal(arm.fleet.starting_soc, 0.17)))
            self.vehicles.append(Vehicle(id=i, zone_id=z.id, x=z.x, y=z.y, soc=soc))

    def _build_arrival_plan(self) -> list[tuple[float, str]]:
        """Explode per-interval counts into individual arrival times.

        Requests inside a 15-minute interval are spread uniformly across it rather than
        all landing on the boundary, so waiting time reflects matching latency instead of
        the forecast's granularity.
        """
        plan: list[tuple[float, str]] = []
        for (zid, interval), n in sorted(self.arrivals.items()):
            if zid not in self.served or n <= 0:
                continue
            base = interval * INTERVAL_MINUTES
            for offset in self.rng.uniform(0.0, INTERVAL_MINUTES, size=n):
                plan.append((base + float(offset), zid))
        plan.sort(key=lambda t: t[0])
        return plan

    # ---- helpers -------------------------------------------------------------

    def _minutes(self, miles: float) -> float:
        return travel_minutes(miles) * self.speed_factor

    def _gravity_choice(self, origin: str, pool: list[str]) -> str:
        """Pick a destination weighted by attraction over distance."""
        w = []
        for z in pool:
            d = zone_distance(origin, z)
            w.append(ZONES_BY_ID[z].peak_intensity / ((1.0 + d) ** 1.6))
        total = sum(w)
        if total <= 0:
            return pool[0]
        return pool[int(self.rng.choice(len(pool), p=[x / total for x in w]))]

    def _pick_destination(self, origin: str) -> str:
        """Where a rider is going.

        Airport arrivals head into the core, and a slice of core demand heads to the
        airport, which is what creates the long deadhead the experiment is about.
        Everything else follows a gravity model over the served zones.
        """
        core = [z for z in self.served_order if z != AIRPORT_ZONE_ID]
        if origin == AIRPORT_ZONE_ID:
            return self._gravity_choice(origin, core)
        if self.rng.random() < 0.16:
            return AIRPORT_ZONE_ID
        pool = [z for z in core if z != origin] or core
        return self._gravity_choice(origin, pool)

    def _zone_bucket(self, zid: str) -> dict[str, float]:
        return self.result.zone_stats.setdefault(
            zid, {"requested": 0.0, "completed": 0.0, "canceled": 0.0, "wait_sum": 0.0, "wait_n": 0.0}
        )

    # ---- processes -----------------------------------------------------------

    def _serve(self, v: Vehicle, trip: Trip) -> simpy.events.Event:
        def proc():
            v.status = "to_pickup"
            origin = ZONES_BY_ID[trip.origin]
            pickup_miles = distance_miles(v.x, v.y, origin.x, origin.y) + INTRA_ZONE_MILES
            trip.pickup_miles = pickup_miles
            yield self.env.timeout(self._minutes(pickup_miles))

            # A rider who has waited past patience is gone before the car arrives.
            if self.env.now - trip.requested_at > RIDER_PATIENCE_MINUTES:
                trip.canceled = True
                self.result.canceled += 1
                self._zone_bucket(trip.origin)["canceled"] += 1
                v.zone_id, v.x, v.y = origin.id, origin.x, origin.y
                v.soc -= pickup_miles * SOC_PER_MILE
                v.empty_miles += pickup_miles
                v.status = "idle"
                return

            trip.picked_up_at = self.env.now
            v.status = "on_trip"
            trip_miles = zone_distance(trip.origin, trip.dest)
            trip.trip_miles = trip_miles
            yield self.env.timeout(self._minutes(trip_miles))

            dest = ZONES_BY_ID[trip.dest]
            v.zone_id, v.x, v.y = dest.id, dest.x, dest.y
            v.soc -= (pickup_miles + trip_miles) * SOC_PER_MILE
            v.loaded_miles += trip_miles
            v.empty_miles += pickup_miles
            v.busy_minutes += self._minutes(pickup_miles + trip_miles)
            trip.completed_at = self.env.now

            self.result.completed += 1
            wait = trip.pickup_wait or 0.0
            self.result.pickup_waits.append(wait)
            if trip.origin == AIRPORT_ZONE_ID:
                self.result.airport_pickup_waits.append(wait)
            b = self._zone_bucket(trip.origin)
            b["completed"] += 1
            b["wait_sum"] += wait
            b["wait_n"] += 1
            v.status = "idle"

        return self.env.process(proc())

    def _charge(self, v: Vehicle) -> simpy.events.Event:
        def proc():
            v.status = "to_depot"
            depot = nearest_depot(v.x, v.y)
            miles = distance_miles(v.x, v.y, depot.x, depot.y)
            yield self.env.timeout(self._minutes(miles))
            v.soc -= miles * SOC_PER_MILE
            v.empty_miles += miles
            v.x, v.y = depot.x, depot.y

            queued_at = self.env.now
            with self.chargers.request() as req:
                yield req
                waited = self.env.now - queued_at
                self.result.charge_queue_waits.append(waited)
                # Time spent waiting for a stall is time the vehicle cannot serve demand.
                self.result.constrained_vehicle_minutes += waited
                v.status = "charging"
                needed = max(0.0, CHARGE_TARGET_SOC - v.soc)
                yield self.env.timeout(needed / CHARGE_RATE_PER_MIN)
                v.soc = min(CHARGE_TARGET_SOC, v.soc + needed)
                self.result.charge_sessions += 1
            v.status = "idle"

        return self.env.process(proc())

    def _reposition(self, v: Vehicle, target: str) -> simpy.events.Event:
        def proc():
            v.status = "repositioning"
            z = ZONES_BY_ID[target]
            miles = distance_miles(v.x, v.y, z.x, z.y)
            yield self.env.timeout(self._minutes(miles))
            v.soc -= miles * SOC_PER_MILE
            v.empty_miles += miles
            v.zone_id, v.x, v.y = z.id, z.x, z.y
            v.status = "idle"

        return self.env.process(proc())

    # ---- main loop -----------------------------------------------------------

    def _arrivals_proc(self):
        """Inject each request at its own arrival time."""
        prev = 0.0
        for at, zid in self.arrival_plan:
            if at > prev:
                yield self.env.timeout(at - prev)
                prev = at
            dest = self._pick_destination(zid)
            t = Trip(
                request_id=self._next_request_id,
                origin=zid,
                dest=dest,
                requested_at=self.env.now,
                is_airport=is_airport_request(zid, dest),
            )
            self._next_request_id += 1
            self.trips[t.request_id] = t
            self.pending.append(t)
            self.result.requested += 1
            self._zone_bucket(zid)["requested"] += 1

    def _dispatch_proc(self):
        """Match pending requests to idle vehicles, and send flat batteries to charge."""
        policy = self.arm.policy
        while True:
            # Riders who have waited past patience leave the queue.
            still: list[Trip] = []
            for t in self.pending:
                if self.env.now - t.requested_at > RIDER_PATIENCE_MINUTES:
                    t.canceled = True
                    self.result.canceled += 1
                    self._zone_bucket(t.origin)["canceled"] += 1
                else:
                    still.append(t)
            self.pending = still

            # Low battery outranks demand: a vehicle that cannot finish a trip is not
            # supply, and pretending otherwise is how a simulation hides a charging problem.
            for v in self.vehicles:
                if v.status != "idle" or v.soc > CHARGE_TRIGGER_SOC:
                    continue
                # The airport battery reserve holds charged vehicles at the airport
                # instead of releasing them to a depot during the arrival bank. This is
                # the half of the policy that adds supply; the dispatch-cost half only
                # rations it. A vehicle that is genuinely low still goes.
                if (
                    policy.airport_battery_reserve > 0.0
                    and v.zone_id == AIRPORT_ZONE_ID
                    and v.soc > MIN_SOC + policy.airport_battery_reserve
                ):
                    continue
                self._charge(v)

            idle = [v for v in self.vehicles if v.status == "idle"]
            if idle and self.pending:
                candidates = [Candidate(v.id, v.zone_id, v.x, v.y, v.soc) for v in idle]
                reqs = [
                    PendingRequest(t.request_id, t.origin, t.dest,
                                   self.env.now - t.requested_at, t.is_airport)
                    for t in self.pending
                ]
                if policy.dispatch == "demand_aware":
                    assignment = assign_demand_aware(
                        candidates, reqs,
                        min_soc=MIN_SOC,
                        airport_priority=policy.airport_priority,
                        airport_battery_reserve=policy.airport_battery_reserve,
                    )
                else:
                    assignment = assign_nearest_available(candidates, reqs, min_soc=MIN_SOC)

                by_id = {v.id: v for v in self.vehicles}
                assigned: set[int] = set()
                for rid, vid in assignment.items():
                    v = by_id[vid]
                    if v.status != "idle":
                        continue
                    t = self.trips[rid]
                    t.assigned_at = self.env.now
                    self._serve(v, t)
                    assigned.add(rid)
                self.pending = [t for t in self.pending if t.request_id not in assigned]

            yield self.env.timeout(DISPATCH_TICK_MINUTES)

    def _reposition_proc(self):
        """Nudge idle supply toward the next interval's forecast, on the forecast's clock."""
        intervals = self.run_cfg.horizon_minutes // INTERVAL_MINUTES
        for interval in range(intervals):
            yield self.env.timeout(REPOSITION_EVERY_MINUTES)
            target_interval = interval + REPOSITION_LOOKAHEAD_INTERVALS
            if not self.arm.policy.demand_aware_repositioning or target_interval >= intervals:
                continue
            still_idle = [v for v in self.vehicles if v.status == "idle"]
            if not still_idle:
                continue
            nxt = {z: self.forecast_p50.get((z, target_interval), 0.0) for z in self.served_order}
            supply: dict[str, int] = {}
            for v in still_idle:
                supply[v.zone_id] = supply.get(v.zone_id, 0) + 1
            moves = reposition_targets(
                [Candidate(v.id, v.zone_id, v.x, v.y, v.soc) for v in still_idle],
                nxt, supply, served=self.served_order,
                airport_priority=self.arm.policy.airport_priority,
            )
            by_id = {v.id: v for v in self.vehicles}
            for vid, target in moves.items():
                v = by_id[vid]
                if v.status == "idle":
                    self._reposition(v, target)

    def run(self) -> SimResult:
        self.env.process(self._arrivals_proc())
        self.env.process(self._dispatch_proc())
        self.env.process(self._reposition_proc())
        # Run past the horizon so trips already in flight finish rather than vanishing.
        self.env.run(until=self.run_cfg.horizon_minutes + 90)

        for t in self.pending:
            if not t.canceled and t.completed_at is None:
                t.canceled = True
                self.result.canceled += 1
                self._zone_bucket(t.origin)["canceled"] += 1

        self.result.loaded_miles = sum(v.loaded_miles for v in self.vehicles)
        self.result.empty_miles = sum(v.empty_miles for v in self.vehicles)
        self.result.vehicle_busy_minutes = sum(v.busy_minutes for v in self.vehicles)
        return self.result
