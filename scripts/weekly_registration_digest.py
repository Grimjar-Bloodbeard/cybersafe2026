"""Weekly email digest of new Dec 4 event registrations.

Why email instead of a web page: registrants' real names and emails are real personal
data, so a page showing this would need real access control (a password, or a
private-network gate) - see docs/architecture/PLAN.md Section 7 for the same reasoning
on the future scan-admin tool. A script that reads the database and sends one email
needs no new public web page at all, so there's nothing new to secure - "kill the path
before you guard it" (see Vault security notes, same principle).

Reads straight from the same database the registration API writes to
(backend/app/db/session.py's DB_PATH - one source of truth, not a copy). Remembers the
highest registration id already reported in data/digest_state.json (gitignored) so
re-running this never double-reports the same signups, even if the weekly task runs
twice by accident.

Run manually any time: python -m scripts.weekly_registration_digest
Scheduled: see docs/architecture/PLAN.md or ask whoever set up the Windows Scheduled
Task (runs weekly via pythonw.exe, no console window pops up).
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backend.app.db.session import DB_PATH  # noqa: E402 - needs load_dotenv() first
from backend.app.email_sender import send_email  # noqa: E402 - same reason

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "digest_state.json"

RECIPIENTS = [r.strip() for r in os.environ.get("DIGEST_RECIPIENTS", "").split(",") if r.strip()]


def _load_last_reported_id() -> int:
    try:
        return json.loads(STATE_PATH.read_text())["last_reported_id"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return 0


def _save_last_reported_id(last_id: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"last_reported_id": last_id}))


def fetch_new_registrations(since_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM event_registrations WHERE id > ? ORDER BY id", (since_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_total_attendees() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(group_size), 0) FROM event_registrations"
        ).fetchone()[0]
    finally:
        conn.close()


def build_email_body(new_rows: list[dict], total_attendees: int) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"CyberSafe 2026 - Weekly Registration Digest ({today})",
        "",
        f"Total attendees expected so far (all signups): {total_attendees}",
        f"New registrations since last digest: {len(new_rows)}",
        "",
    ]
    if not new_rows:
        lines.append("No new registrations this week.")
    else:
        for r in new_rows:
            names = ", ".join(json.loads(r["attendee_names"]))
            plural = "s" if r["group_size"] != 1 else ""
            lines.append(
                f"- {r['organization']} ({r['group_size']} attendee{plural}: {names}) "
                f"- {r['email']}, signed up {r['submitted_at']}"
            )
    return "\n".join(lines)


def main() -> None:
    last_id = _load_last_reported_id()
    new_rows = fetch_new_registrations(last_id)
    total_attendees = fetch_total_attendees()

    body = build_email_body(new_rows, total_attendees)
    subject = f"CyberSafe 2026: {len(new_rows)} new registration(s) this week"

    sent = bool(RECIPIENTS) and send_email(RECIPIENTS, subject, body)
    print(body)
    print("\n(email sent)" if sent else "\n(email NOT sent - see message above)")

    if new_rows:
        _save_last_reported_id(max(r["id"] for r in new_rows))


if __name__ == "__main__":
    main()
