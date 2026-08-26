"""Dispatch policies: the thing the experiment is actually comparing.

Two policies, deliberately different in kind rather than in tuning:

`nearest_available` is the greedy baseline most fleets start with. It assigns each
pending request, oldest first, to whichever idle vehicle is closest. It is fast, it is
easy to reason about, and it has no notion of what happens next.

`demand_aware` batches the pending requests and solves a min-cost assignment with
OR-Tools, so a vehicle that is marginally further from request A can be sent to request B
if that produces a better system-wide outcome. Cost is pickup distance plus penalties
that encode policy: airport requests can be prioritised, and vehicles below the airport
battery reserve are made expensive for airport work rather than forbidden outright.

Whether the optimisation is worth its complexity over greedy is a real question, which
is why the product runs them against each other instead of assuming.
"""

from __future__ import annotations

from dataclasses import dataclass

from ortools.graph.python import linear_sum_assignment

from .world import AIRPORT_ZONE_ID, INTRA_ZONE_MILES, ZONES_BY_ID, distance_miles, zone_distance

# Assignment costs are integers in OR-Tools. Miles are scaled so a hundredth of a mile is
# still a distinguishable cost, which is well inside the noise of the travel model.
COST_SCALE = 100
# Must stay inside rider patience: at this metro's speeds a longer assignment commits a
# vehicle to a rider who will have cancelled before it arrives. See sim.RIDER_PATIENCE.
MAX_PICKUP_MILES = 5.5
# Repositioning acts on a two-interval (30 minute) lookahead, so it can commit to a
# longer move than dispatch, which must arrive inside rider patience. At this metro's
# speeds 10 miles is ~25 minutes, which still lands before the demand it is sent for.
REPOSITION_MAX_MILES = 10.0
_UNREACHABLE = 10**7


@dataclass
class Candidate:
    """A vehicle offered to the assignment problem this tick."""
    vehicle_id: int
    zone_id: str
    x: float
    y: float
    soc: float


@dataclass
class PendingRequest:
    request_id: int
    origin_zone: str
    dest_zone: str
    waiting_minutes: float
    is_airport: bool


def _pickup_miles(c: Candidate, r: PendingRequest) -> float:
    """Must match what sim.py actually charges, floor included, or the optimiser is
    minimising a different quantity than the one being measured."""
    z = ZONES_BY_ID[r.origin_zone]
    return distance_miles(c.x, c.y, z.x, z.y) + INTRA_ZONE_MILES


def _trip_soc_cost(r: PendingRequest) -> float:
    """Rough SoC a trip will consume, used to decide whether a vehicle can take it."""
    return zone_distance(r.origin_zone, r.dest_zone) * SOC_PER_MILE


SOC_PER_MILE = 0.0042  # ~240 mile usable range


def assign_nearest_available(
    candidates: list[Candidate], requests: list[PendingRequest], *, min_soc: float
) -> dict[int, int]:
    """Greedy baseline: oldest request first, nearest eligible vehicle wins."""
    taken: set[int] = set()
    out: dict[int, int] = {}
    for r in sorted(requests, key=lambda x: -x.waiting_minutes):
        best, best_d = None, float("inf")
        for c in candidates:
            if c.vehicle_id in taken:
                continue
            if c.soc - _trip_soc_cost(r) < min_soc:
                continue
            d = _pickup_miles(c, r)
            if d < best_d and d <= MAX_PICKUP_MILES:
                best, best_d = c, d
        if best is not None:
            taken.add(best.vehicle_id)
            out[r.request_id] = best.vehicle_id
    return out


def assign_demand_aware(
    candidates: list[Candidate],
    requests: list[PendingRequest],
    *,
    min_soc: float,
    airport_priority: bool,
    airport_battery_reserve: float,
) -> dict[int, int]:
    """Min-cost assignment over the pending batch, with policy encoded as cost."""
    if not candidates or not requests:
        return {}

    def selection_rank(r: PendingRequest) -> float:
        boost = AIRPORT_BATCH_BOOST_MINUTES if (r.is_airport and airport_priority) else 0.0
        return -(r.waiting_minutes + boost)

    batch = sorted(requests, key=selection_rank)[: len(candidates)]
    in_batch = {id(r) for r in batch}
    overflow = [r for r in requests if id(r) not in in_batch]

    solver = linear_sum_assignment.SimpleLinearSumAssignment()
    for ri, r in enumerate(batch):
        for ci, c in enumerate(candidates):
            miles = _pickup_miles(c, r)
            if miles > MAX_PICKUP_MILES or c.soc - _trip_soc_cost(r) < min_soc:
                cost = _UNREACHABLE
            else:
                cost = miles
                # Waiting riders get cheaper the longer they have waited, which keeps the
                # optimiser from starving an awkwardly-placed request forever.
                cost -= min(r.waiting_minutes, 12.0) * 0.18
                if r.is_airport and airport_priority:
                    cost -= 2.2
                    # The reserve is a soft constraint. A vehicle under it can still take
                    # an airport trip if nothing else can, it just has to be clearly best.
                    if c.soc < min_soc + airport_battery_reserve:
                        cost += 1.2
                cost = max(cost, 0.01)
            solver.add_arc_with_cost(ri, ci, int(round(cost * COST_SCALE)))

    if solver.solve() != solver.OPTIMAL:
        # A degenerate batch should still serve riders, not raise.
        return assign_nearest_available(candidates, requests, min_soc=min_soc)

    out: dict[int, int] = {}
    used: set[int] = set()
    for node in range(solver.num_nodes()):
        if solver.assignment_cost(node) >= _UNREACHABLE * COST_SCALE:
            continue
        r = batch[node]
        c = candidates[solver.right_mate(node)]
        out[r.request_id] = c.vehicle_id
        used.add(c.vehicle_id)

    # Anything the batch could not take gets a greedy pass over whatever is left, so a
    # capped batch never means an idle vehicle beside a waiting rider.
    if overflow:
        spare = [c for c in candidates if c.vehicle_id not in used]
        if spare:
            out.update(assign_nearest_available(spare, overflow, min_soc=min_soc))
    return out


# A vehicle completes roughly this many trips in one 15-minute forecast interval, given
# the pickup and trip distances in this metro. Used only to convert a demand forecast into
# a comparable vehicle count.
TRIPS_PER_VEHICLE_PER_INTERVAL = 0.85

# How much harder the airport pulls on contested supply when airport priority is on.
AIRPORT_NEED_WEIGHT = 2.1

# Effective head start, in minutes of apparent wait, that an airport request gets when
# competing for a place in a capped assignment batch.
AIRPORT_BATCH_BOOST_MINUTES = 6.0


def reposition_targets(
    idle: list[Candidate],
    forecast_next: dict[str, float],
    supply: dict[str, int],
    *,
    served: "list[str] | set[str]",
    airport_priority: bool = False,
    max_move_fraction: float = 0.22,
) -> dict[int, str]:
    """Move idle vehicles from forecast surplus to forecast deficit.

    This is a greedy allocation, not an optimisation, and that is a deliberate product
    decision: repositioning acts on a forecast that is itself uncertain, so spending
    compute to find the optimal move against a noisy target buys precision that the input
    does not support. Nearest-donor-to-largest-deficit is good enough and explainable.

    `airport_priority` weights the airport's deficit up. That is what the toggle means
    operationally: not a queue trick, but a standing instruction that airport demand wins
    contested supply. Without it, the airport loses every allocation to the larger core
    zones and the priority setting has nothing to act on.
    """
    # Sorted: iteration order here decides which zone wins a tied deficit, and a set
    # would make that vary between processes.
    served_order = sorted(served)
    need = {z: forecast_next.get(z, 0.0) / TRIPS_PER_VEHICLE_PER_INTERVAL for z in served_order}
    if airport_priority and AIRPORT_ZONE_ID in need:
        need[AIRPORT_ZONE_ID] *= AIRPORT_NEED_WEIGHT

    deficit = {z: need.get(z, 0.0) - supply.get(z, 0) for z in served_order}
    receivers = sorted(((z, d) for z, d in deficit.items() if d > 0.5), key=lambda kv: -kv[1])
    if not receivers:
        return {}
    remaining = dict(receivers)

    # A donor is an idle vehicle sitting where the forecast does not need it.
    donors = [c for c in idle if deficit.get(c.zone_id, 0.0) < -0.5]
    donors.sort(key=lambda c: -c.soc)  # send the vehicles best able to absorb the miles

    budget = max(1, int(len(idle) * max_move_fraction))
    moves: dict[int, str] = {}
    for c in donors:
        if len(moves) >= budget:
            break
        best, best_d = None, float("inf")
        for zid, _ in receivers:
            if remaining.get(zid, 0.0) <= 0 or zid == c.zone_id:
                continue
            z = ZONES_BY_ID[zid]
            d = distance_miles(c.x, c.y, z.x, z.y)
            if d <= REPOSITION_MAX_MILES and d < best_d:
                best, best_d = zid, d
        if best is not None:
            moves[c.vehicle_id] = best
            remaining[best] -= 1
    return moves


def is_airport_request(origin: str, dest: str) -> bool:
    return AIRPORT_ZONE_ID in (origin, dest)
