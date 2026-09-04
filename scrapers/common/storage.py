"""Minimal SQLite persistence for Week 1 scraper output.

Field names deliberately mirror the planned SQLAlchemy schema (see
C:\\Users\\cody\\.claude\\plans\\snappy-noodling-pike.md, Section 4) so this data
migrates cleanly once the backend's Alembic migrations land in Week 2 - this is not a
throwaway format.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cybersafe.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    legal_name TEXT NOT NULL,
    contact_name TEXT,
    contact_email TEXT,
    website_root_url TEXT,
    source TEXT NOT NULL,
    sourced_at TEXT NOT NULL,
    directory_category TEXT,
    directory_member_id TEXT UNIQUE,
    phone TEXT,
    street_address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    profile_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS engagements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    status TEXT NOT NULL DEFAULT 'draft',
    max_tier_allowed INTEGER NOT NULL DEFAULT 0,
    in_scope_hosts TEXT,
    outreach_notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def upsert_business(conn: sqlite3.Connection, business: dict) -> tuple[int, bool]:
    """Insert a business (and a draft engagement row) if new. Returns (business_id, was_new).

    Authorization is never granted here - every new engagement starts at
    status='draft', max_tier_allowed=0, which the code-level gate (Week 2) treats as
    unscannable until a real signature moves it to 'authorized'.
    """
    existing = conn.execute(
        "SELECT id FROM businesses WHERE directory_member_id = ?",
        (business["directory_member_id"],),
    ).fetchone()
    if existing:
        return existing[0], False

    cursor = conn.execute(
        """
        INSERT INTO businesses (
            legal_name, website_root_url, source, sourced_at, directory_category,
            directory_member_id, phone, street_address, city, state, postal_code, profile_url
        ) VALUES (?, ?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            business["legal_name"],
            business.get("website_root_url"),
            business.get("source", "chamber_directory_scrape"),
            business.get("directory_category"),
            business["directory_member_id"],
            business.get("phone"),
            business.get("street_address"),
            business.get("city"),
            business.get("state"),
            business.get("postal_code"),
            business.get("profile_url"),
        ),
    )
    business_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO engagements (business_id, status, max_tier_allowed) VALUES (?, 'draft', 0)",
        (business_id,),
    )
    return business_id, True
