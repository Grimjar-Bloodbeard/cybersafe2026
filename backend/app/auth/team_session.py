"""Session handling for the team dashboard - FastAPI has no built-in
server-side session store the way Express does, so this is a small,
deliberately simple equivalent to Summit's session.regenerate()/req.session
pattern: an opaque random token in an HttpOnly cookie, with only its SHA-256
hash stored server-side (same reasoning as the enroll token in models.py -
the raw token only ever exists in the browser).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.app.db.models import TeamSession, TeamUser

SESSION_COOKIE_NAME = "cybersafe_team_session"
SESSION_TTL_DAYS = 30


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_session(db: Session, response: Response, user: TeamUser) -> None:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        TeamSession(
            session_token_hash=_hash_token(raw_token),
            user_id=user.id,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
        )
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
    )


def destroy_session(db: Session, request: Request, response: Response) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token:
        db.query(TeamSession).filter(TeamSession.session_token_hash == _hash_token(raw_token)).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)


def get_current_team_user(request: Request, db: Session) -> TeamUser:
    """Raises 401 (never returns None/guesses) if there's no valid session -
    fail-closed, same principle as the authorization gate.
    """
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="not logged in")

    session_row = (
        db.query(TeamSession).filter(TeamSession.session_token_hash == _hash_token(raw_token)).one_or_none()
    )
    if session_row is None:
        raise HTTPException(status_code=401, detail="session not recognized")

    expires_at = datetime.fromisoformat(session_row.expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=401, detail="session expired")

    user = db.query(TeamUser).filter(TeamUser.id == session_row.user_id).one_or_none()
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="account no longer active")
    return user
