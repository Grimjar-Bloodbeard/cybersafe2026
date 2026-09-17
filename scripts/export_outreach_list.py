"""Exports the full outreach target list - Chamber businesses AND the
churches/community centers from the OSM scraper - to a plain CSV the
Outreach & Engagement Lead can actually open in Excel/Google Sheets.

Meeting action item, 2026-09-15, two real changes from the original version
of this script:

1. Scope grew from "Chamber-listed businesses in 3 towns" (a city-name
   filter) to "everything within a 30-minute drive of the event" (a real
   distance filter) - a name-based filter would never have caught the
   already-known case of a Chamber member with a Georgia address, and
   wouldn't include churches at all, since they were never Chamber members
   in the first place.
2. "Central tracking" now needs outreach-sequence progress, not just a
   signed/not-signed flag - added blank columns matching Jovan's 3-step
   method from the same meeting (see docs/architecture/PLAN.md).

Distance is straight-line ("as the crow flies"), not real driving time - no
routing API is wired in, and this project doesn't have one. Documented
honestly as an approximation rather than presented as exact: EVENT_RADIUS_MILES
is picked generously for this specific rural/mountainous county so a winding
road doesn't wrongly exclude somewhere genuinely reachable in ~30 minutes -
see its own comment for the reasoning. This is why: pandas earns its place
here doing exactly this kind of table math, without hand-writing CSV
formatting.

Output intentionally never gets committed to git (see .gitignore) - it's
real, not-yet-authorized contact info, and this repo is public.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cybersafe.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "outreach_list.csv"

# Wilkes Community College, 1328 S Collegiate Dr, Wilkesboro, NC - the actual
# Dec 4 event location (see backend/app/templates/register.html).
EVENT_LOCATION = (36.1355152, -81.1830366)

# A straight-line proxy for "30-minute drive," not driving time itself - no
# routing API is wired into this project. Picked generously for Wilkes
# County's rural, winding secondary roads (a real drive covers less straight-
# line distance per minute than a highway would), so this errs toward
# including a genuinely-reachable place rather than wrongly excluding one.
# The known Georgia address (~300 miles) is correctly excluded either way;
# this matters for the closer, more ambiguous cases near the boundary.
EVENT_RADIUS_MILES = 20.0

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(a))


def build_outreach_dataframe() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            legal_name AS "Name",
            CASE
                WHEN source = 'osm_community_scrape' THEN directory_category
                ELSE 'business'
            END AS "Type",
            city AS "City",
            phone AS "Phone",
            website_root_url AS "Website",
            profile_url AS "Chamber Profile",
            latitude AS "_lat",
            longitude AS "_lon"
        FROM businesses
        -- A business needs a phone or website to be a cold-outreach target.
        -- A church/community center doesn't need either - Jovan's outreach
        -- method explicitly includes in-person walk-ins, and a real
        -- location (which every OSM-sourced row has) is enough for that.
        WHERE phone IS NOT NULL OR website_root_url IS NOT NULL OR source = 'osm_community_scrape'
        ORDER BY legal_name
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    has_coords = df["_lat"].notna() & df["_lon"].notna()
    df["Miles from event"] = pd.NA
    df.loc[has_coords, "Miles from event"] = df.loc[has_coords].apply(
        lambda r: round(haversine_miles(*EVENT_LOCATION, r["_lat"], r["_lon"]), 1), axis=1
    )

    # Fail closed on distance, same principle as the authorization gate: an
    # address we couldn't geocode is NOT assumed to be in range. It's kept in
    # the list (real, potentially valid outreach data) but clearly flagged
    # for a human to check manually - never silently included or excluded.
    df["In 30-min range?"] = "UNKNOWN - check address manually"
    df.loc[has_coords & (df["Miles from event"] <= EVENT_RADIUS_MILES), "In 30-min range?"] = "Yes"
    df.loc[has_coords & (df["Miles from event"] > EVENT_RADIUS_MILES), "In 30-min range?"] = "No - too far"

    df = df.drop(columns=["_lat", "_lon"])

    # Blank columns for the Outreach Lead to actually use - matches Jovan's
    # 3-step method from the 2026-09-15 meeting (initial intro -> ~2wk
    # follow-up -> ~2wk final "breakup" email) plus the eventual outcome.
    for col in ["Step 1 Sent", "Step 2 Sent", "Step 3 Sent", "Outcome / Notes", "Signed?"]:
        df[col] = ""

    return df


def main() -> None:
    df = build_outreach_dataframe()
    in_range = df[df["In 30-min range?"] == "Yes"]
    print(f"Wrote {len(df)} total targets to {OUTPUT_PATH}")
    print(f"  {len(in_range)} confirmed within {EVENT_RADIUS_MILES:.0f} miles of the event")
    print(f"  {(df['In 30-min range?'] == 'No - too far').sum()} confirmed too far - excluded from active outreach, kept for the record")
    print(f"  {(df['In 30-min range?'].str.startswith('UNKNOWN')).sum()} need a manual address check (geocoding found no match)")
    print(f"\nBy type:\n{df['Type'].value_counts().to_string()}")
    df.to_csv(OUTPUT_PATH, index=False)


if __name__ == "__main__":
    main()
