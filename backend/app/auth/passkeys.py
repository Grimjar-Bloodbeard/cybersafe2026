"""Passkey (WebAuthn) registration/authentication ceremony logic for the
team outreach dashboard.

Ported from Summit Gaming's real, proven webauthn.js
(C:\\summitserver\\modules\\core\\auth\\webauthn.js) - same design, same
hard-won UX choice (authenticator_attachment=PLATFORM, so the browser only
offers the device's own Windows Hello/Touch ID/Android biometric prompt,
never the confusing "use a security key" option a casual user doesn't have -
Summit hit that prompt live, 2026-08-29). Reimplemented in Python against the
`webauthn` package (the same kind of well-audited library Summit uses
`@simplewebauthn/server` for, so CBOR/COSE parsing and signature
verification are never hand-rolled here either) rather than literally
sharing code, since this project is FastAPI/SQLite, not Express/MySQL - see
docs/architecture/PLAN.md for why this isn't wired into Summit's actual auth
system.

Client side reuses Summit's exact vendored library
(backend/app/static/simplewebauthn-browser.min.js, MIT licensed, pure
browser-side WebAuthn API wrapper with no backend dependency) - legitimate
literal reuse, since that half genuinely doesn't care what server language
issued the JSON options it's given.
"""
from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json_dict
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from backend.app.db.models import TeamUser, TeamWebauthnCredential

RP_NAME = "CyberSafe 2026"
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "cybersafe.codynoah.net")
ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", f"https://{RP_ID}")

_AUTHENTICATOR_SELECTION = AuthenticatorSelectionCriteria(
    resident_key=ResidentKeyRequirement.PREFERRED,  # discoverable credential -> usernameless login
    user_verification=UserVerificationRequirement.PREFERRED,
    authenticator_attachment=AuthenticatorAttachment.PLATFORM,
)


class PasskeyError(Exception):
    """Raised for any ceremony failure - callers turn this into a 400/401,
    never a fabricated success. Fail-closed, same principle as the
    authorization gate.
    """


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _from_b64url(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---- registration (adding a passkey - via an emailed enrollment link) ----

def start_registration(db: Session, user: TeamUser) -> dict:
    existing = db.query(TeamWebauthnCredential).filter(TeamWebauthnCredential.user_id == user.id).all()
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(user.id).encode(),
        user_name=user.email,
        user_display_name=user.display_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=_from_b64url(c.credential_id)) for c in existing
        ],
        authenticator_selection=_AUTHENTICATOR_SELECTION,
    )
    user.webauthn_challenge = _b64url(options.challenge)
    db.commit()
    return options_to_json_dict(options)


def finish_registration(db: Session, user: TeamUser, response: dict, device_label: str | None) -> None:
    if not user.webauthn_challenge:
        raise PasskeyError("no pending registration challenge for this user")

    try:
        verification = verify_registration_response(
            credential=response,
            expected_challenge=_from_b64url(user.webauthn_challenge),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
        )
    except Exception as exc:  # the library raises its own InvalidRegistrationResponse etc.
        raise PasskeyError(f"passkey registration could not be verified: {exc}") from exc

    db.add(
        TeamWebauthnCredential(
            user_id=user.id,
            credential_id=_b64url(verification.credential_id),
            public_key=base64.b64encode(verification.credential_public_key).decode("ascii"),
            sign_count=verification.sign_count,
            device_label=device_label,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    user.webauthn_challenge = None
    db.commit()


# ---- authentication (usernameless login via a discoverable credential) ----
# No user is known yet when the challenge is issued, so it can't be stored on
# a user row - kept in an in-memory map instead, same lifetime class as
# Summit's identical design (webauthn.js's pendingLoginChallenges) and this
# project's own in-process rate limiter (backend/app/rate_limit.py).
_pending_login_challenges: dict[str, float] = {}
_CHALLENGE_TTL_SECONDS = 5 * 60


def _remember_challenge(challenge_b64url: str) -> None:
    _pending_login_challenges[challenge_b64url] = time.monotonic() + _CHALLENGE_TTL_SECONDS
    if len(_pending_login_challenges) > 500:
        now = time.monotonic()
        for k, exp in list(_pending_login_challenges.items()):
            if exp < now:
                del _pending_login_challenges[k]


def _consume_challenge(challenge_b64url: str) -> bool:
    expires_at = _pending_login_challenges.pop(challenge_b64url, None)
    return expires_at is not None and expires_at >= time.monotonic()


def start_authentication() -> dict:
    options = generate_authentication_options(
        rp_id=RP_ID,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _remember_challenge(_b64url(options.challenge))
    return options_to_json_dict(options)


def finish_authentication(db: Session, response: dict) -> TeamUser:
    client_data = json.loads(_from_b64url(response["response"]["clientDataJSON"]))
    challenge = client_data["challenge"]
    if not _consume_challenge(challenge):
        raise PasskeyError("login challenge expired or unknown - request a fresh one")

    stored = (
        db.query(TeamWebauthnCredential)
        .filter(TeamWebauthnCredential.credential_id == response["id"])
        .one_or_none()
    )
    if stored is None:
        raise PasskeyError("unrecognized passkey")

    try:
        verification = verify_authentication_response(
            credential=response,
            expected_challenge=_from_b64url(challenge),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64.b64decode(stored.public_key),
            credential_current_sign_count=stored.sign_count,
        )
    except Exception as exc:
        raise PasskeyError(f"passkey authentication failed: {exc}") from exc

    stored.sign_count = verification.new_sign_count
    stored.last_used_at = datetime.now(timezone.utc).isoformat()
    db.commit()

    user = db.query(TeamUser).filter(TeamUser.id == stored.user_id).one_or_none()
    if user is None or user.status != "active":
        raise PasskeyError("account no longer active")
    return user
