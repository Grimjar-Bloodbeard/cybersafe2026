"""Adds one team member who's allowed to log into the outreach dashboard.

No self-service account creation on purpose - only the 4 real team members
should ever exist here, and there's no public "sign up" path to abuse.
Run this once per person, then they enroll their own passkey at /team/enroll
using the email you give them here.

Usage: python -m scripts.add_team_member <email> "<display name>"
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from backend.app.db.models import TeamUser
from backend.app.db.session import SessionLocal


def main() -> None:
    if len(sys.argv) != 3:
        print('Usage: python -m scripts.add_team_member <email> "<display name>"')
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    display_name = sys.argv[2].strip()

    db = SessionLocal()
    try:
        existing = db.query(TeamUser).filter(TeamUser.email == email).one_or_none()
        if existing:
            print(f"{email} is already a team member ({existing.display_name}) - nothing to do.")
            return
        db.add(
            TeamUser(
                email=email,
                display_name=display_name,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        db.commit()
        print(f"Added {display_name} ({email}). They can now set up a passkey at /team/enroll.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
