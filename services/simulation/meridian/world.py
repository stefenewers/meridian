"""The fictional service geography Meridian experiments run against.

Meridian Bay is invented. Zone coordinates are abstract miles on a flat grid, chosen to
produce the operational tension the product exists to study: an airport far from the
core, depots that are convenient for some zones and not others, and expansion zones that
stretch the fleet's reach before they pay for themselves.

Distances use a road-circuity multiplier over Euclidean distance. That is deliberately
crude, and `docs/assumptions.md` says so: routing fidelity is not what this tool is for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ZoneTier(StrEnum):
    CORE = "core"           # always in the service area
    AIRPORT = "airport"     # always served, but policy-sensitive
    EXPANSION = "expansion" # only served when an experiment turns expansion on


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    x: float
    y: float
    tier: ZoneTier
    # Mean requests per 15-minute interval at the window's busiest point. The demand
    # model learns a shape around this; it is not used directly at simulation time.
    peak_intensity: float


@dataclass(frozen=True)
class Depot:
    id: str
    name: str
    x: float
    y: float
    chargers: int


ZONES: tuple[Zone, ...] = (
    Zone("MB-01", "Harbor Flats", 2.0, 3.0, ZoneTier.CORE, 17.0),
    Zone("MB-02", "Downtown Crossing", 4.0, 4.0, ZoneTier.CORE, 31.0),
    Zone("MB-03", "Mission Row", 3.0, 6.0, ZoneTier.CORE, 23.0),
    Zone("MB-04", "University Hill", 6.0, 7.0, ZoneTier.CORE, 19.0),
    Zone("MB-05", "Stadium District", 7.0, 3.0, ZoneTier.CORE, 21.0),
    Zone("MB-06", "Riverside", 1.0, 7.0, ZoneTier.CORE, 11.0),
    Zone("MB-07", "Tech Corridor", 8.0, 6.0, ZoneTier.CORE, 14.0),
    Zone("MB-08", "Northgate", 5.0, 9.0, ZoneTier.CORE, 11.0),
    Zone("MB-AP", "Meridian Intl Airport", 10.5, 3.0, ZoneTier.AIRPORT, 26.0),
    Zone("MB-09", "Eastvale", 10.0, 6.5, ZoneTier.EXPANSION, 7.0),
    Zone("MB-10", "Foothill Park", 7.5, 9.5, ZoneTier.EXPANSION, 5.0),
    Zone("MB-11", "Lakeshore", 10.0, 9.5, ZoneTier.EXPANSION, 4.0),
)

DEPOTS: tuple[Depot, ...] = (
    Depot("DEP-A", "Harbor Depot", 3.0, 4.5, chargers=20),
    Depot("DEP-B", "Northgate Depot", 6.0, 9.0, chargers=16),
)

ZONES_BY_ID: dict[str, Zone] = {z.id: z for z in ZONES}
DEPOTS_BY_ID: dict[str, Depot] = {d.id: d for d in DEPOTS}
AIRPORT_ZONE_ID = "MB-AP"

# A vehicle "in" a zone sits at its centroid, but the rider is somewhere inside it.
# Without this floor every same-zone pickup is instantaneous and the median pickup time
# collapses to zero, which is not a result, it is a modelling artifact.
INTRA_ZONE_MILES = 0.55

# Straight-line miles understate street distance. 1.35 is a common planning circuity
# factor for a grid-ish metro; it is a stand-in for a routing engine, not a claim.
ROAD_CIRCUITY = 1.35

# Average speed in this window. Late-night traffic is light, which is part of why the
# flagship experiment is scoped to it.
AVG_SPEED_MPH = 24.0


def distance_miles(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by) * ROAD_CIRCUITY


def zone_distance(a: str, b: str) -> float:
    za, zb = ZONES_BY_ID[a], ZONES_BY_ID[b]
    return distance_miles(za.x, za.y, zb.x, zb.y)


def travel_minutes(miles: float) -> float:
    return (miles / AVG_SPEED_MPH) * 60.0


def served_zone_ids(*, expansion_enabled: bool) -> list[str]:
    """Zones in the service area for a given experiment arm."""
    return [
        z.id
        for z in ZONES
        if z.tier is not ZoneTier.EXPANSION or expansion_enabled
    ]


def nearest_depot(x: float, y: float) -> Depot:
    return min(DEPOTS, key=lambda d: distance_miles(x, y, d.x, d.y))
