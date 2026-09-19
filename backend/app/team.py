"""Team dashboard: passkey-only login (see backend/app/auth/passkeys.py) and
the interactive outreach tracker (who to call, distance from the event,
Jovan's 3-step sequence progress) - meeting action item, 2026-09-15/18.

Password-protected-vs-Tailscale was a real decision (see PLAN.md): Cody chose
a simpler access model than the future real scan-admin tool needs, but
"simpler" still means real WebAuthn passkeys here, not a shared static
password - real business contact info deserves it, and the team already has
a proven passkey pattern (Summit Gaming's webauthn.js) to build from.
"""
from __future__ import annotations

import math
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from backend.app.auth import passkeys
from backend.app.auth.team_session import create_session, destroy_session, get_current_team_user
from backend.app.db.models import Business, Engagement, TeamPasskeyEnrollToken, TeamUser
from backend.app.db.session import get_session
from backend.app.email_sender import send_email
from backend.app.rate_limit import PerIPRateLimiter, client_ip
from scrapers.common.distance import EVENT_RADIUS_MILES, miles_from_event

router = APIRouter()

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)

# Same throttling philosophy as backend/app/rate_limit.py's existing limiters,
# and the same enumeration-safe pattern Summit's enroll/request route uses.
ENROLL_REQUEST_LIMIT = PerIPRateLimiter(max_requests=3, per_seconds=600)
LOGIN_LIMIT = PerIPRateLimiter(max_requests=10, per_seconds=600)
ENROLL_TOKEN_TTL_MINUTES = 15


def _dep_get_current_team_user(request: Request, db: Session = Depends(get_session)) -> TeamUser:
    return get_current_team_user(request, db)


def _hash_token(raw_token: str) -> str:
    import hashlib

    return hashlib.sha256(raw_token.encode()).hexdigest()


def _user_for_enroll_token(db: Session, raw_token: str | None) -> tuple[TeamUser, TeamPasskeyEnrollToken] | None:
    if not raw_token or len(raw_token) != 64:
        return None
    token_row = (
        db.query(TeamPasskeyEnrollToken)
        .filter(TeamPasskeyEnrollToken.token_hash == _hash_token(raw_token))
        .one_or_none()
    )
    if token_row is None or token_row.used_at is not None:
        return None
    expires_at = datetime.fromisoformat(token_row.expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return None
    user = db.query(TeamUser).filter(TeamUser.id == token_row.user_id, TeamUser.status == "active").one_or_none()
    if user is None:
        return None
    return user, token_row


# ---- pages ----

@router.get("/team/login", response_class=HTMLResponse)
def show_team_login():
    return _env.get_template("team_login.html").render()


@router.get("/team/enroll", response_class=HTMLResponse)
def show_team_enroll():
    return _env.get_template("team_enroll.html").render()


@router.get("/team/outreach", response_class=HTMLResponse)
def show_team_outreach(user: TeamUser = Depends(_dep_get_current_team_user)):
    return _env.get_template("team_outreach.html").render(display_name=user.display_name)


# ---- enrollment (bootstrapping a passkey via an emailed link) ----

@router.post("/api/team/enroll/request")
def enroll_request(payload: dict, request: Request, db: Session = Depends(get_session)):
    ENROLL_REQUEST_LIMIT.check(client_ip(request))
    # Enumeration-safe, same pattern as Summit's enroll/request: always the
    # same response regardless of what actually happened underneath -
    # whether the email already existed, got newly created, or the invite
    # code was wrong. Never confirms or denies any of that to the caller.
    safe_response = {"message": "If that's valid, an enrollment link has been sent."}
    email = (payload.get("email") or "").strip().lower()
    display_name = (payload.get("display_name") or "").strip()
    invite_code = payload.get("invite_code") or ""
    if not email:
        return JSONResponse(safe_response)

    user = db.query(TeamUser).filter(TeamUser.email == email, TeamUser.status == "active").one_or_none()
    if user is None:
        # Self-service, 2026-09-19: Cody's call - teammates pick their own
        # email (a school address might not reliably receive mail from this
        # sender) rather than being pre-added one at a time. Not fully open
        # signup, though - this still holds real business contact data, so
        # creating an account requires TEAM_INVITE_CODE, a shared secret
        # only told to the actual 4 team members. A wrong or missing code
        # gets the exact same response as a valid email that's already
        # enrolled - never reveals which case actually happened.
        expected_code = os.environ.get("TEAM_INVITE_CODE", "")
        if not expected_code or not secrets.compare_digest(invite_code, expected_code) or not display_name:
            return JSONResponse(safe_response)
        user = TeamUser(email=email, display_name=display_name, created_at=datetime.now(timezone.utc).isoformat())
        db.add(user)
        db.commit()
        db.refresh(user)

    raw_token = secrets.token_hex(32)
    db.query(TeamPasskeyEnrollToken).filter(
        TeamPasskeyEnrollToken.user_id == user.id, TeamPasskeyEnrollToken.used_at.is_(None)
    ).delete()
    db.add(
        TeamPasskeyEnrollToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=ENROLL_TOKEN_TTL_MINUTES)).isoformat(),
        )
    )
    db.commit()

    enroll_link = f"https://cybersafe.codynoah.net/team/enroll?token={raw_token}"
    send_email(
        user.email,
        "Set up your CyberSafe 2026 team passkey",
        f"Hi {user.display_name},\n\n"
        f"Click below to set up a passkey for the team outreach dashboard "
        f"(expires in {ENROLL_TOKEN_TTL_MINUTES} minutes):\n\n{enroll_link}\n\n"
        f"Didn't request this? Ignore this email - nothing happens without you clicking through.",
    )
    return JSONResponse(safe_response)


@router.get("/api/team/enroll/validate")
def enroll_validate(token: str, db: Session = Depends(get_session)):
    found = _user_for_enroll_token(db, token)
    return JSONResponse({"valid": found is not None, "display_name": found[0].display_name if found else None})


@router.post("/api/team/enroll/options")
def enroll_options(payload: dict, db: Session = Depends(get_session)):
    found = _user_for_enroll_token(db, payload.get("token"))
    if found is None:
        raise HTTPException(status_code=400, detail="This enrollment link has expired or already been used.")
    user, _ = found
    return JSONResponse(passkeys.start_registration(db, user))


@router.post("/api/team/enroll/verify")
def enroll_verify(payload: dict, db: Session = Depends(get_session)):
    found = _user_for_enroll_token(db, payload.get("token"))
    if found is None:
        raise HTTPException(status_code=400, detail="This enrollment link has expired or already been used.")
    user, token_row = found
    try:
        passkeys.finish_registration(db, user, payload["response"], payload.get("device_label"))
    except passkeys.PasskeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token_row.used_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    return JSONResponse({"success": True})


# ---- login ----

@router.post("/api/team/login/options")
def login_options(request: Request):
    LOGIN_LIMIT.check(client_ip(request))
    return JSONResponse(passkeys.start_authentication())


@router.post("/api/team/login/verify")
def login_verify(payload: dict, request: Request, db: Session = Depends(get_session)):
    LOGIN_LIMIT.check(client_ip(request))
    try:
        user = passkeys.finish_authentication(db, payload["response"])
    except passkeys.PasskeyError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    # Real bug found live, 2026-09-18: a Response injected via Depends only
    # carries its headers/cookies through when the route returns nothing (or
    # a plain dict) and lets FastAPI populate that same object - returning a
    # separate JSONResponse instance here silently discarded the Set-Cookie
    # header. Login itself succeeded every time; the session cookie just
    # never reached the browser, so the very next request looked logged out.
    # Fix: build the real response object first, set the cookie on IT.
    response = JSONResponse({"success": True, "display_name": user.display_name})
    create_session(db, response, user)
    return response


@router.post("/api/team/logout")
def logout(request: Request, db: Session = Depends(get_session)):
    response = JSONResponse({"success": True})
    destroy_session(db, request, response)
    return response


# ---- the outreach dashboard itself ----

# Dashboard writes are deliberately narrow: notes, outreach-step timestamps,
# and status only between "draft" and "pending_signature". Never
# "authorized" - that stays a real signed-paperwork event handled outside
# this tool, never a dashboard click (see backend/app/auth/gate.py).
_DASHBOARD_SETTABLE_STATUSES = {"draft", "pending_signature"}


def _ranked_engagements(db: Session) -> list[tuple[float | None, Business, Engagement]]:
    """Every real outreach target with a confirmed distance within range,
    closest first, followed by the unconfirmed-address ones (miles=None) at
    the end - real data, not hidden, just not claiming a rank it can't
    support. Confirmed-too-far is the one real exclusion (not a display
    preference - the meeting's own 30-minute-drive rule). Shared by the list
    endpoint and auto-assign, so the two can never disagree about "the list."
    """
    rows = (
        db.query(Business, Engagement)
        .join(Engagement, Engagement.business_id == Business.id)
        .filter(Business.phone.isnot(None) | Business.website_root_url.isnot(None) | (Business.source == "osm_community_scrape"))
        .all()
    )

    confirmed, unconfirmed = [], []
    for business, engagement in rows:
        miles = miles_from_event(business.latitude, business.longitude)
        if miles is not None and miles > EVENT_RADIUS_MILES:
            continue
        (confirmed if miles is not None else unconfirmed).append((miles, business, engagement))
    confirmed.sort(key=lambda r: r[0])
    return confirmed + unconfirmed


@router.get("/api/team/outreach")
def list_outreach(user: TeamUser = Depends(_dep_get_current_team_user), db: Session = Depends(get_session)):
    targets = [
        {
            "business_id": business.id,
            "name": business.legal_name,
            "type": "business" if business.source != "osm_community_scrape" else business.directory_category,
            "city": business.city,
            "phone": business.phone,
            "website": business.website_root_url,
            "miles_from_event": miles,
            "status": engagement.status,
            "outreach_owner": engagement.outreach_owner,
            "outreach_notes": engagement.outreach_notes,
            "step1_sent_at": engagement.outreach_step1_sent_at,
            "step2_sent_at": engagement.outreach_step2_sent_at,
            "step3_sent_at": engagement.outreach_step3_sent_at,
        }
        for miles, business, engagement in _ranked_engagements(db)
    ]
    return JSONResponse({"targets": targets, "you": user.display_name})


@router.post("/api/team/outreach/auto-assign")
def auto_assign_outreach(
    payload: dict,
    user: TeamUser = Depends(_dep_get_current_team_user),
    db: Session = Depends(get_session),
):
    """Splits the current full target list into len(names) contiguous,
    distance-sorted chunks - the closest chunk goes to names[0], and so on -
    and sets outreach_owner for every one of them. A coordination label, not
    a security-relevant field (unlike status), so overwriting existing
    assignments in one clean pass is fine - anyone can still hand-edit a
    single card afterward the normal way.
    """
    names = [n.strip() for n in payload.get("names", []) if n.strip()]
    if len(names) < 2:
        raise HTTPException(status_code=400, detail="Give at least 2 names to split the list between.")

    ranked = _ranked_engagements(db)
    chunk_size = math.ceil(len(ranked) / len(names))
    for i, (_, _, engagement) in enumerate(ranked):
        engagement.outreach_owner = names[i // chunk_size]
    db.commit()
    return JSONResponse({"success": True, "assigned": len(ranked), "per_person": chunk_size})


@router.post("/api/team/outreach/{business_id}")
def update_outreach(
    business_id: int,
    payload: dict,
    user: TeamUser = Depends(_dep_get_current_team_user),
    db: Session = Depends(get_session),
):
    engagement = db.query(Engagement).filter(Engagement.business_id == business_id).one_or_none()
    if engagement is None:
        raise HTTPException(status_code=404, detail="no engagement row for this business")

    if "status" in payload:
        if payload["status"] not in _DASHBOARD_SETTABLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="The dashboard can only set status to draft or pending_signature - "
                "authorizing a real scan requires the actual signed scope-of-engagement process.",
            )
        engagement.status = payload["status"]

    if "outreach_notes" in payload:
        engagement.outreach_notes = str(payload["outreach_notes"])[:2000]

    if "outreach_owner" in payload:
        engagement.outreach_owner = str(payload["outreach_owner"])[:100]

    now_iso = datetime.now(timezone.utc).isoformat()
    for step, field in (("step1", "outreach_step1_sent_at"), ("step2", "outreach_step2_sent_at"), ("step3", "outreach_step3_sent_at")):
        if payload.get(f"mark_{step}_sent"):
            setattr(engagement, field, now_iso)

    db.commit()
    return JSONResponse({"success": True})
