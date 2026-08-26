"""Dispatch invariants that a policy change must never break."""

from meridian.dispatch import (
    Candidate,
    PendingRequest,
    assign_demand_aware,
    assign_nearest_available,
    reposition_targets,
)
from meridian.world import AIRPORT_ZONE_ID

C = lambda i, z, x, y, soc=0.9: Candidate(i, z, x, y, soc)  # noqa: E731
R = lambda i, o, d, w=0.0, ap=False: PendingRequest(i, o, d, w, ap)  # noqa: E731


def test_no_vehicle_is_double_assigned():
    cands = [C(0, "MB-02", 4, 4), C(1, "MB-02", 4, 4)]
    reqs = [R(10, "MB-02", "MB-03"), R(11, "MB-02", "MB-04"), R(12, "MB-02", "MB-01")]
    for out in (assign_nearest_available(cands, reqs, min_soc=0.1),
                assign_demand_aware(cands, reqs, min_soc=0.1, airport_priority=False,
                                    airport_battery_reserve=0.0)):
        assert len(set(out.values())) == len(out.values())
        assert len(out) <= len(cands)


def test_flat_battery_is_never_dispatched():
    cands = [C(0, "MB-02", 4, 4, soc=0.10)]
    reqs = [R(10, "MB-02", "MB-07")]
    assert assign_nearest_available(cands, reqs, min_soc=0.10) == {}


def test_optimiser_handles_more_requests_than_vehicles():
    """The solver is infeasible on a rectangular problem; overflow must still be served."""
    cands = [C(0, "MB-02", 4, 4)]
    reqs = [R(i, "MB-02", "MB-03", w=float(i)) for i in range(6)]
    out = assign_demand_aware(cands, reqs, min_soc=0.1, airport_priority=False,
                              airport_battery_reserve=0.0)
    assert len(out) == 1, "exactly one vehicle exists, so exactly one request is served"


def test_airport_priority_breaks_a_near_tie():
    """Priority is a cost bonus, not an override.

    The vehicle sits between a core pickup and the airport, close enough that the bonus
    is decisive but not so far that diverting it would be absurd. Without priority the
    nearer core rider wins; with it, the airport does. A vehicle parked beside a waiting
    rider should still never be sent across the metro, which is asserted separately.
    """
    cands = [C(0, "MB-05", 8.0, 3.0)]
    reqs = [R(1, "MB-05", "MB-02"), R(2, AIRPORT_ZONE_ID, "MB-02", ap=True)]
    plain = assign_demand_aware(cands, reqs, min_soc=0.1, airport_priority=False,
                                airport_battery_reserve=0.0)
    primed = assign_demand_aware(cands, reqs, min_soc=0.1, airport_priority=True,
                                 airport_battery_reserve=0.0)
    assert 1 in plain and 2 not in plain, "without priority the nearer core rider wins"
    assert 2 in primed and 1 not in primed, "with priority the airport wins the near tie"


def test_airport_priority_does_not_cause_absurd_diversion():
    """When supply allows both riders to compete, cost still decides sensibly.

    Priority influences which requests get into a capped batch. Once inside it, the cost
    function arbitrates, and it must not send the vehicle parked beside a core rider off
    to the airport when another vehicle is already sitting there.
    """
    cands = [C(0, "MB-05", 7.0, 3.0), C(1, AIRPORT_ZONE_ID, 10.5, 3.0)]
    reqs = [R(1, "MB-05", "MB-02"), R(2, AIRPORT_ZONE_ID, "MB-02", ap=True)]
    primed = assign_demand_aware(cands, reqs, min_soc=0.1, airport_priority=True,
                                 airport_battery_reserve=0.0)
    assert primed == {1: 0, 2: 1}, "each vehicle should take the rider beside it"


def test_scarce_supply_lets_priority_decide_who_is_served():
    """With one vehicle and two riders, someone waits. Priority says who does not."""
    cands = [C(0, "MB-05", 8.0, 3.0)]
    reqs = [R(1, "MB-05", "MB-02"), R(2, AIRPORT_ZONE_ID, "MB-02", ap=True)]
    plain = assign_demand_aware(cands, reqs, min_soc=0.1, airport_priority=False,
                                airport_battery_reserve=0.0)
    primed = assign_demand_aware(cands, reqs, min_soc=0.1, airport_priority=True,
                                 airport_battery_reserve=0.0)
    assert list(plain) == [1], "without priority the longest-waiting core rider is taken"
    assert list(primed) == [2], "with priority the airport rider is taken"


def test_repositioning_needs_a_real_deficit():
    idle = [C(i, "MB-02", 4, 4) for i in range(6)]
    supply = {"MB-02": 6}
    served = {"MB-02", "MB-03"}
    flat = reposition_targets(idle, {"MB-02": 1.0, "MB-03": 0.0}, supply, served=served)
    assert flat == {}, "no forecast deficit means no empty miles"


def test_repositioning_moves_toward_deficit():
    idle = [C(i, "MB-02", 4, 4) for i in range(12)]
    supply = {"MB-02": 12, "MB-03": 0}
    served = {"MB-02", "MB-03"}
    moves = reposition_targets(idle, {"MB-02": 0.0, "MB-03": 9.0}, supply, served=served)
    assert moves and set(moves.values()) == {"MB-03"}
