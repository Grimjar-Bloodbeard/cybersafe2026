"""Proves the team dashboard's access control and write restrictions - same
"prove the negative, not just the happy path" instinct as test_gate.py.

Doesn't test the actual WebAuthn cryptographic ceremony (finish_registration/
finish_authentication) - that's the `webauthn` library's own well-audited
job, not something to re-verify here. What's tested is everything this
project's own code is responsible for: fail-closed session gating, the
enrollment token lifecycle, and the dashboard's narrow write scope (it must
never be able to authorize a real scan).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.auth import passkeys
from backend.app.auth.team_session import create_session
from backend.app.db.models import Base, Business, Engagement, TeamPasskeyEnrollToken, TeamUser
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.team import _hash_token, _user_for_enroll_token


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_session():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    # https base_url, not the default http://testserver: the session cookie
    # is marked Secure (correct for the real deployment, which is genuinely
    # HTTPS) - over a plain-http test client, httpx's own cookie jar quietly
    # refuses to resend a Secure cookie on the next request, which looks
    # identical to the real bug this file exists to catch. Match production.
    yield TestClient(app, base_url="https://testserver"), TestSession
    app.dependency_overrides.clear()


def _make_user(db, email="zack@example.com", display_name="Zack"):
    user = TeamUser(email=email, display_name=display_name, created_at=datetime.now(timezone.utc).isoformat())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_business_with_engagement(db, name="Test Biz", status="draft", latitude=None, longitude=None):
    business = Business(
        legal_name=name,
        source="chamber_directory_scrape",
        sourced_at=datetime.now(timezone.utc).isoformat(),
        created_at=datetime.now(timezone.utc).isoformat(),
        phone="555-1234",
        latitude=latitude,
        longitude=longitude,
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    engagement = Engagement(
        business_id=business.id,
        status=status,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(engagement)
    db.commit()
    return business, engagement


# ---- session gating (fail-closed) ----

def test_dashboard_page_requires_login(client):
    test_client, _ = client
    resp = test_client.get("/team/outreach", follow_redirects=False)
    assert resp.status_code == 401


def test_dashboard_api_requires_login(client):
    test_client, _ = client
    resp = test_client.get("/api/team/outreach")
    assert resp.status_code == 401


def test_update_endpoint_requires_login(client):
    test_client, _ = client
    resp = test_client.post("/api/team/outreach/1", json={"outreach_notes": "hi"})
    assert resp.status_code == 401


def test_garbage_cookie_is_rejected_not_trusted(client):
    test_client, _ = client
    test_client.cookies.set("cybersafe_team_session", "not-a-real-token")
    resp = test_client.get("/api/team/outreach")
    assert resp.status_code == 401


def test_valid_session_reaches_the_dashboard(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        # create_session sets a cookie on a Response object - build one the
        # same way login_verify does, then copy it onto the test client.
        from fastapi import Response

        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.get("/api/team/outreach")
    assert resp.status_code == 200
    assert resp.json()["you"] == "Zack"


# ---- enrollment token lifecycle ----

def test_enroll_request_is_enumeration_safe(client):
    # Same response whether the email is a real team account or not - never
    # confirm/deny an email's existence to an unauthenticated caller.
    test_client, _ = client
    real_resp = test_client.post("/api/team/enroll/request", json={"email": "nobody@example.com"})
    assert real_resp.status_code == 200
    assert "sent" in real_resp.json()["message"].lower()


def test_expired_enroll_token_is_rejected(client):
    with_TestSession = client[1]
    with with_TestSession() as db:
        user = _make_user(db)
        db.add(
            TeamPasskeyEnrollToken(
                user_id=user.id,
                token_hash=_hash_token("a" * 64),
                expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            )
        )
        db.commit()
        assert _user_for_enroll_token(db, "a" * 64) is None


def test_used_enroll_token_is_rejected(client):
    with_TestSession = client[1]
    with with_TestSession() as db:
        user = _make_user(db)
        db.add(
            TeamPasskeyEnrollToken(
                user_id=user.id,
                token_hash=_hash_token("b" * 64),
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                used_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        db.commit()
        assert _user_for_enroll_token(db, "b" * 64) is None


def test_valid_unused_enroll_token_is_accepted(client):
    with_TestSession = client[1]
    with with_TestSession() as db:
        user = _make_user(db)
        db.add(
            TeamPasskeyEnrollToken(
                user_id=user.id,
                token_hash=_hash_token("c" * 64),
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            )
        )
        db.commit()
        found = _user_for_enroll_token(db, "c" * 64)
        assert found is not None
        assert found[0].email == user.email


# ---- the dashboard's write scope must never reach "authorized" ----

def test_dashboard_cannot_set_status_to_authorized(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        business, engagement = _make_business_with_engagement(db)
        business_id = business.id

        from fastapi import Response
        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.post(f"/api/team/outreach/{business_id}", json={"status": "authorized"})
    assert resp.status_code == 400

    with TestSession() as db:
        assert db.query(Engagement).filter(Engagement.business_id == business_id).one().status == "draft"


def test_dashboard_can_move_draft_to_pending_signature(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        business, engagement = _make_business_with_engagement(db)
        business_id = business.id

        from fastapi import Response
        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.post(f"/api/team/outreach/{business_id}", json={"status": "pending_signature"})
    assert resp.status_code == 200

    with TestSession() as db:
        assert (
            db.query(Engagement).filter(Engagement.business_id == business_id).one().status
            == "pending_signature"
        )


def test_marking_a_step_sent_records_a_timestamp(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        business, engagement = _make_business_with_engagement(db)
        business_id = business.id

        from fastapi import Response
        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.post(f"/api/team/outreach/{business_id}", json={"mark_step1_sent": True})
    assert resp.status_code == 200

    with TestSession() as db:
        updated = db.query(Engagement).filter(Engagement.business_id == business_id).one()
        assert updated.outreach_step1_sent_at is not None
        assert updated.outreach_step2_sent_at is None


# ---- real regression test: login must actually leave the browser logged in ----
# Found live, 2026-09-18: /api/team/login/verify returned 200 every time, but
# the session cookie never reached the browser, so the very next request
# looked logged out. Root cause: the route set the cookie on the Response
# injected via Depends, then returned a *different* JSONResponse instance -
# silently discarding the Set-Cookie header. The unit-level tests above
# never would have caught this, since they call create_session() directly
# and construct their own Response - they bypass the route entirely. This
# test goes through the real HTTP route, the only way to catch it.

def test_login_verify_cookie_actually_works_for_the_next_request(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        user_id, display_name = user.id, user.display_name

    # A plain stand-in, not a real ORM object: login_verify/create_session
    # only ever touch .id and .display_name on what finish_authentication
    # returns, and a detached SQLAlchemy row would just add unrelated
    # session-lifecycle noise to a test that's about cookies, not the ORM.
    fake_user = SimpleNamespace(id=user_id, display_name=display_name)

    with patch.object(passkeys, "finish_authentication", return_value=fake_user):
        resp = test_client.post("/api/team/login/verify", json={"response": {}})
        assert resp.status_code == 200
        assert "cybersafe_team_session" in resp.cookies

    # The real regression: without the fix, this next request comes back 401
    # even though login/verify just reported success.
    resp2 = test_client.get("/api/team/outreach")
    assert resp2.status_code == 200


def test_logout_cookie_deletion_reaches_the_response(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        from fastapi import Response

        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.post("/api/team/logout")
    assert resp.status_code == 200
    # A real Set-Cookie header clearing the cookie must be on THIS response -
    # same bug class as login: it's easy to set/delete a cookie on the wrong
    # Response object and have it silently vanish.
    assert "cybersafe_team_session" in resp.headers.get("set-cookie", "")

    resp2 = test_client.get("/api/team/outreach")
    assert resp2.status_code == 401


# ---- Cody's call, 2026-09-18: confirmed-too-far businesses are dropped ----

def test_confirmed_too_far_is_excluded_but_unconfirmed_still_shows(client):
    # Cody's call, 2026-09-19 (reversed from an earlier call the same day):
    # confirmed-too-far is a real exclusion (the meeting's 30-minute-drive
    # rule), but unconfirmed-address businesses are real, uncategorized data
    # and belong in the list too - just without a distance to rank by.
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        # Aiken, SC - a real address seen in testing, ~184 miles from the
        # event per scripts/export_outreach_list.py's own distance check.
        _make_business_with_engagement(db, name="Way Too Far LLC", latitude=33.5157, longitude=-81.7368)
        # WCC's own coordinates - definitely in range.
        _make_business_with_engagement(db, name="Right Next Door LLC", latitude=36.1355152, longitude=-81.1830366)
        # No coordinates at all - unconfirmed, but still a real target.
        _make_business_with_engagement(db, name="Unknown Address LLC")

        from fastapi import Response
        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.get("/api/team/outreach")
    targets = resp.json()["targets"]
    by_name = {t["name"]: t for t in targets}

    assert "Way Too Far LLC" not in by_name
    assert "Right Next Door LLC" in by_name
    assert "Unknown Address LLC" in by_name
    assert by_name["Unknown Address LLC"]["miles_from_event"] is None
    # Confirmed-distance ones still come first - unconfirmed trails behind,
    # never claiming a rank it can't support.
    names_in_order = [t["name"] for t in targets]
    assert names_in_order.index("Right Next Door LLC") < names_in_order.index("Unknown Address LLC")


def test_targets_are_sorted_closest_first(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        # All three genuinely within EVENT_RADIUS_MILES, at increasing real
        # distances from WCC, added out of order on purpose.
        _make_business_with_engagement(db, name="Farthest", latitude=36.30, longitude=-81.30)
        _make_business_with_engagement(db, name="Closest", latitude=36.1360, longitude=-81.1835)
        _make_business_with_engagement(db, name="Middle", latitude=36.20, longitude=-81.22)

        from fastapi import Response
        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.get("/api/team/outreach")
    ordered_names = [t["name"] for t in resp.json()["targets"]]

    assert ordered_names == ["Closest", "Middle", "Farthest"]


# ---- dividing the list among the team, 2026-09-19 ----

def test_auto_assign_splits_into_contiguous_closest_first_chunks(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        # 4 targets, distinct real distances from WCC, added out of order.
        _make_business_with_engagement(db, name="4th closest", latitude=36.30, longitude=-81.30)
        _make_business_with_engagement(db, name="1st closest", latitude=36.1360, longitude=-81.1835)
        _make_business_with_engagement(db, name="3rd closest", latitude=36.20, longitude=-81.22)
        _make_business_with_engagement(db, name="2nd closest", latitude=36.16, longitude=-81.20)

        from fastapi import Response
        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.post("/api/team/outreach/auto-assign", json={"names": ["Alice", "Bob"]})
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "assigned": 4, "per_person": 2}

    listed = {t["name"]: t["outreach_owner"] for t in test_client.get("/api/team/outreach").json()["targets"]}
    assert listed["1st closest"] == "Alice"
    assert listed["2nd closest"] == "Alice"
    assert listed["3rd closest"] == "Bob"
    assert listed["4th closest"] == "Bob"


def test_auto_assign_requires_at_least_two_names(client):
    test_client, TestSession = client
    with TestSession() as db:
        user = _make_user(db)
        from fastapi import Response

        response = Response()
        create_session(db, response, user)
        raw_cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    test_client.cookies.set("cybersafe_team_session", raw_cookie)
    resp = test_client.post("/api/team/outreach/auto-assign", json={"names": ["OnlyOne"]})
    assert resp.status_code == 400
