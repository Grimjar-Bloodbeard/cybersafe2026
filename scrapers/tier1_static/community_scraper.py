"""Tier 1 static scraper: sources churches and community centers across Wilkes
County via OpenStreetMap's Overpass API - a free, public, no-API-key data
source, self-hosted-friendly in spirit (queries a community-run mirror of
open map data, not a paid SaaS).

Meeting action item, 2026-09-15: the outreach target explicitly grew beyond
"Chamber of Commerce businesses" to include "churches, town establishments,
and community stakeholders" - the Chamber directory scraper
(directory_scraper.py) only ever listed paying Chamber members, so churches
were never going to appear there no matter how thoroughly it ran. This is a
genuinely different source, not a bigger version of the same one.

Good citizenship, same standard as directory_scraper.py: a real, descriptive
User-Agent naming this project and a contact address, and a rate limiter -
Overpass has no robots.txt (it's an API, not a crawled site), but its own
usage policy asks for reasonable pacing and no parallel requests, which the
existing RateLimiter already gives us for free.

Lands in the same `businesses` table as the Chamber scraper (source=
"osm_community_scrape"), each with a draft, unauthorized engagement - same
code-level gate applies, nothing here is scannable until a real signature
changes that. Comes with real latitude/longitude for free (OSM nodes carry
coordinates directly), unlike the Chamber scrape, which only has a street
address - see scripts/filter_by_drive_distance.py for what that coordinate
buys: enforcing the meeting's "no further than a 30-minute drive" rule.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import requests

sys.path.insert(0, str(__file__.rsplit("scrapers", 1)[0]))

from scrapers.common.rate_limiter import RateLimiter
from scrapers.common.retry import retry_transient
from scrapers.common.storage import get_connection, init_db, upsert_business

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

USER_AGENT = (
    "CyberSafe2026-CommunityBot/1.0 "
    f"(Wilkes Community College capstone project; contact: {os.environ.get('SCRAPER_CONTACT', 'set SCRAPER_CONTACT env var')})"
)

# One amenity type per query keeps each request small and lets a failure on
# one type not lose the others - Overpass's own usage policy prefers several
# modest queries over one large one anyway.
AMENITY_TYPES = ["place_of_worship", "community_centre", "social_facility"]

QUERY_TEMPLATE = """
[out:json][timeout:60];
area["name"="Wilkes County"]["admin_level"="6"]["boundary"="administrative"]->.searchArea;
node["amenity"="{amenity}"](area.searchArea);
out center;
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("community_scraper")

_rate_limiter = RateLimiter(requests_per_second=0.2)  # one request every 5s - Overpass is shared community infra


@retry_transient
def _post_query(amenity: str) -> requests.Response:
    _rate_limiter.wait()
    resp = requests.post(
        OVERPASS_URL,
        data={"data": QUERY_TEMPLATE.format(amenity=amenity)},
        headers={"User-Agent": USER_AGENT},
        timeout=90,
    )
    resp.raise_for_status()  # lets retry_transient see 429/5xx and retry with backoff
    return resp


def fetch_amenity(amenity: str) -> list[dict]:
    try:
        resp = _post_query(amenity)
    except requests.RequestException as exc:
        log.warning("request failed for amenity=%s after retries: %s", amenity, exc)
        return []
    return resp.json().get("elements", [])


def parse_element(element: dict, amenity: str) -> dict | None:
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        return None  # unnamed nodes aren't useful outreach targets

    street = tags.get("addr:housenumber", "")
    street_name = tags.get("addr:street")
    street_address = f"{street} {street_name}".strip() if street_name else None

    return {
        # Stable across re-runs (OSM's own node id), distinct namespace from
        # the Chamber scraper's numeric member IDs so the two sources can
        # never collide in the UNIQUE directory_member_id column.
        "directory_member_id": f"osm:{element['type']}/{element['id']}",
        "legal_name": name,
        "website_root_url": tags.get("website") or tags.get("contact:website"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "street_address": street_address,
        "city": tags.get("addr:city"),
        "state": tags.get("addr:state", "NC"),
        "postal_code": tags.get("addr:postcode"),
        "directory_category": amenity,
        "source": "osm_community_scrape",
        "latitude": element.get("lat") or element.get("center", {}).get("lat"),
        "longitude": element.get("lon") or element.get("center", {}).get("lon"),
    }


def run(limit: int | None = None) -> dict:
    init_db()
    total_seen = 0
    total_new = 0

    with get_connection() as conn:
        for amenity in AMENITY_TYPES:
            elements = fetch_amenity(amenity)
            log.info("amenity=%s: %d raw elements from Overpass", amenity, len(elements))
            if limit:
                elements = elements[:limit]
            for element in elements:
                parsed = parse_element(element, amenity)
                if not parsed:
                    continue
                total_seen += 1
                _, was_new = upsert_business(conn, parsed)
                if was_new:
                    total_new += 1

    log.info("Done. Seen: %d, newly added: %d", total_seen, total_new)
    return {"seen": total_seen, "new": total_new}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape churches/community centers in Wilkes County via OSM Overpass")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only keep the first N results per amenity type (for testing)",
    )
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
