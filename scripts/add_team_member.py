"""Adds one team member who's allowed to log into the outreach dashboard,
bypassing the TEAM_INVITE_CODE self-service path in backend/app/team.py.

Self-service (2026-09-19, Cody's call - let each person pick whatever email
they actually check, since a school address might not reliably receive mail
from this sender) is now the normal way someone gets added: they visit
/team/enroll themselves with the shared invite code. This script is for the
exception - adding someone directly (e.g. bootstrapping the first account,
which is how Cody was added, since nobody could invite him) or adding
someone without needing to share the invite code with them at all.

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
        # Matches backend/app/team.py's identity model: (email, display_name)
        # together, not email alone - the team shares one inbox, so the same
        # email legitimately belongs to more than one real account.
        existing = (
            db.query(TeamUser)
            .filter(TeamUser.email == email, TeamUser.display_name.ilike(display_name))
            .one_or_none()
        )
        if existing:
            print(f"{display_name} ({email}) is already a team member - nothing to do.")
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
