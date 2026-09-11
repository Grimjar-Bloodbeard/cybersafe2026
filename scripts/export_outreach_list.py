"""Exports the reachable, in-target-town business list to a plain CSV that the
Outreach & Engagement Lead can actually open in Excel/Google Sheets - the raw
data/cybersafe.db file isn't usable by anyone who isn't comfortable with SQL.

This is where pandas earns its place: it's not a scraping tool, it's the
standard library for exactly this - pulling rows into a table, filtering,
sorting, and writing out a clean file - without hand-writing CSV formatting.

Output intentionally never gets committed to git (see .gitignore) - it's real,
not-yet-authorized business contact info, and this repo is public.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cybersafe.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "outreach_list.csv"

# Real spelling variants found in the scraped city field - see project memory,
# corrected 2026-09-11 after the first count (397) undercounted these.
TARGET_CITY_VARIANTS = [
    "Wilkesboro", "WILKESBORO",
    "North Wilkesboro", "N Wilkesboro", "N. Wilkesboro",
    "Millers Creek",
]


def build_outreach_dataframe() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" for _ in TARGET_CITY_VARIANTS)
    query = f"""
        SELECT
            legal_name AS "Business Name",
            city AS "City",
            phone AS "Phone",
            website_root_url AS "Website",
            directory_category AS "Category",
            profile_url AS "Chamber Profile"
        FROM businesses
        WHERE city IN ({placeholders})
        AND (phone IS NOT NULL OR website_root_url IS NOT NULL)
        ORDER BY city, legal_name
    """
    df = pd.read_sql_query(query, conn, params=TARGET_CITY_VARIANTS)
    conn.close()

    # Blank columns for the Outreach Lead to actually use - this file is meant
    # to be opened and worked from, not just read once.
    df["Contact Attempted?"] = ""
    df["Outcome / Notes"] = ""
    df["Signed?"] = ""

    return df


def main() -> None:
    df = build_outreach_dataframe()
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} reachable businesses to {OUTPUT_PATH}")
    print(f"\nBy city:\n{df['City'].value_counts().to_string()}")


if __name__ == "__main__":
    main()
