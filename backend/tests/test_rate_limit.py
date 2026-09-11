"""Proves the two protections added for the public deployment actually work -
same "prove the negative, not just the happy path" instinct as test_gate.py.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.models import Base
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.rate_limit import PerIPRateLimiter


def test_second_rapid_call_from_same_ip_is_blocked():
    limiter = PerIPRateLimiter(max_requests=1, per_seconds=60)
    limiter.check("1.2.3.4")  # first call: allowed
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("1.2.3.4")  # second, immediate call: blocked
    assert exc_info.value.status_code == 429


def test_different_ips_are_tracked_independently():
    limiter = PerIPRateLimiter(max_requests=1, per_seconds=60)
    limiter.check("1.2.3.4")
    limiter.check("5.6.7.8")  # a different IP - must not be blocked by the first one's hit


@pytest.fixture
def client():
    # StaticPool + check_same_thread=False: FastAPI runs sync route handlers
    # in a worker thread, which would otherwise get its own separate
    # in-memory database under SQLite's default per-thread pooling - the
    # schema created below would be invisible to the actual request. This
    # pins everything to one shared connection regardless of thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


def _registration_payload(**overrides):
    payload = {
        "group_size": 1,
        "attendee_names": ["Test Person"],
        "organization": "N/A",
        "email": "test@example.com",
    }
    payload.update(overrides)
    return payload


def test_honeypot_field_fakes_success_without_saving(client):
    test_client, TestSession = client
    resp = test_client.post(
        "/api/register", json=_registration_payload(hp_website="http://spam.example")
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "registered"}

    with TestSession() as session:
        from backend.app.db.models import EventRegistration

        assert session.query(EventRegistration).count() == 0


def test_real_registration_without_honeypot_is_saved(client):
    test_client, TestSession = client
    resp = test_client.post("/api/register", json=_registration_payload())
    assert resp.status_code == 200

    with TestSession() as session:
        from backend.app.db.models import EventRegistration

        saved = session.query(EventRegistration).one()
        assert saved.organization == "N/A"
        assert json.loads(saved.attendee_names) == ["Test Person"]
