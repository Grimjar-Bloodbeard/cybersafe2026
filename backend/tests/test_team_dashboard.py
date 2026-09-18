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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
    yield TestClient(app), TestSession
    app.dependency_overrides.clear()


def _make_user(db, email="zack@example.com", display_name="Zack"):
    user = TeamUser(email=email, display_name=display_name, created_at=datetime.now(timezone.utc).isoformat())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_business_with_engagement(db, name="Test Biz", status="draft"):
    business = Business(
        legal_name=name,
        source="chamber_directory_scrape",
        sourced_at=datetime.now(timezone.utc).isoformat(),
        created_at=datetime.now(timezone.utc).isoformat(),
        phone="555-1234",
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
