"""Backfills latitude/longitude for businesses that only have a street
address - the Chamber of Commerce scraper's entries, which predate the
lat/long columns and have no coordinates of their own (unlike the OSM
community scraper, which gets them for free from the source data).

Uses OSM Nominatim, the same open-data ecosystem as the community scraper's
Overpass queries - free, no API key, but with a real usage policy: max 1
request/second, and a descriptive User-Agent identifying the project. Both
are respected here the same way every other scraper in this project respects
its source's stated limits.

Run once (or whenever new addressed-but-uncoordinated businesses appear):
    python -m scrapers.common.geocode
"""
from __future__ import annotations

import logging
import os
import sys

import requests

sys.path.insert(0, str(__file__.rsplit("scrapers", 1)[0]))

from scrapers.common.rate_limiter import RateLimiter
from scrapers.common.retry import retry_transient
from scrapers.common.storage import get_connection

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

USER_AGENT = (
    "CyberSafe2026-GeocodeBot/1.0 "
    f"(Wilkes Community College capstone project; contact: {os.environ.get('SCRAPER_CONTACT', 'set SCRAPER_CONTACT env var')})"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("geocode")

# Nominatim's usage policy caps the public instance at 1 request/second -
# this is a hard limit, not a suggestion, since it's shared community infra.
_rate_limiter = RateLimiter(requests_per_second=1.0)


def _build_query(business: dict) -> str | None:
    parts = [business.get("street_address"), business.get("city"), business.get("state") or "NC"]
    parts = [p for p in parts if p]
    if not business.get("street_address") or not business.get("city"):
        return None  # not enough to geocode reliably - don't guess
    return ", ".join(parts)


@retry_transient
def _query_nominatim(query: str) -> requests.Response:
    _rate_limiter.wait()
    resp = requests.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return resp


def geocode_one(business: dict) -> tuple[float, float] | None:
    query = _build_query(business)
    if query is None:
        return None
    try:
        resp = _query_nominatim(query)
    except requests.RequestException as exc:
        log.warning("geocoding failed for %r after retries: %s", query, exc)
        return None
    results = resp.json()
    if not results:
        log.info("no geocoding match for %r", query)
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def run(limit: int | None = None) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, street_address, city, state FROM businesses WHERE latitude IS NULL"
        ).fetchall()
        if limit:
            rows = rows[:limit]

        geocoded = 0
        skipped = 0
        for business_id, street_address, city, state in rows:
            coords = geocode_one({"street_address": street_address, "city": city, "state": state})
            if coords is None:
                skipped += 1
                continue
            lat, lon = coords
            conn.execute(
                "UPDATE businesses SET latitude = ?, longitude = ? WHERE id = ?",
                (lat, lon, business_id),
            )
            geocoded += 1

    log.info("Done. Geocoded: %d, skipped (no address or no match): %d", geocoded, skipped)
    return {"geocoded": geocoded, "skipped": skipped}


if __name__ == "__main__":
    run()
