"""Shared "how far is this from the event" math - used by both
scripts/export_outreach_list.py and the team dashboard (backend/app/team.py)
so the two never quietly disagree about what counts as "in range."

Straight-line ("as the crow flies"), not real driving time - no routing API
is wired into this project. EVENT_RADIUS_MILES is a documented proxy, not an
exact calculation - see its own comment.
"""
from __future__ import annotations

import math

# Wilkes Community College, 1328 S Collegiate Dr, Wilkesboro, NC - the actual
# Dec 4 event location (see backend/app/templates/register.html).
EVENT_LOCATION = (36.1355152, -81.1830366)

# A straight-line proxy for "30-minute drive," not driving time itself.
# Picked generously for Wilkes County's rural, winding secondary roads (a
# real drive covers less straight-line distance per minute than a highway
# would), so this errs toward including a genuinely-reachable place rather
# than wrongly excluding one.
EVENT_RADIUS_MILES = 20.0

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(a))


def miles_from_event(lat: float | None, lon: float | None) -> float | None:
    if lat is None or lon is None:
        return None
    return round(haversine_miles(*EVENT_LOCATION, lat, lon), 1)
