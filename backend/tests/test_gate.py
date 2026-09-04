"""Proves the authorization gate actually blocks unauthorized scans - not just
that it raises an exception, but that a would-be caller never reaches a scraper
module when it does. See docs/architecture/PLAN.md, "Verification".
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.auth.gate import ScanNotAuthorized, assert_engagement_authorized
from backend.app.db.models import Base, Business, Engagement, EngagementStatus


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_business(db) -> Business:
    now = datetime.now(timezone.utc).isoformat()
    biz = Business(legal_name="Test Biz", source="manual", sourced_at=now, created_at=now)
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def _make_engagement(db, biz: Business, **overrides) -> Engagement:
    defaults = dict(
        business_id=biz.id,
        status=EngagementStatus.DRAFT.value,
        max_tier_allowed=0,
        in_scope_hosts=json.dumps(["example.com"]),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    eng = Engagement(**defaults)
    db.add(eng)
    db.commit()
    db.refresh(eng)
    return eng


class ScraperCalledError(Exception):
    """Raised by the fake scraper below if it's ever actually invoked - turns
    "the gate leaked through" into a loud test failure instead of a silent bug.
    """


def fake_scraper_call(target_url: str) -> None:
    raise ScraperCalledError(f"a scraper module was called against {target_url!r}")


def maybe_run_scan(db, engagement_id: int, tier: int, target_url: str) -> None:
    """Mirrors the shape every real caller (the future /scans endpoint) must
    follow: gate first, scraper second, never the other order.
    """
    assert_engagement_authorized(db, engagement_id, tier, target_url)
    fake_scraper_call(target_url)


def test_draft_engagement_is_blocked(db_session):
    biz = _make_business(db_session)
    eng = _make_engagement(db_session, biz, status=EngagementStatus.DRAFT.value, max_tier_allowed=5)
    with pytest.raises(ScanNotAuthorized):
        maybe_run_scan(db_session, eng.id, 1, "https://example.com")


def test_pending_signature_engagement_is_blocked(db_session):
    biz = _make_business(db_session)
    eng = _make_engagement(
        db_session, biz, status=EngagementStatus.PENDING_SIGNATURE.value, max_tier_allowed=5
    )
    with pytest.raises(ScanNotAuthorized):
        maybe_run_scan(db_session, eng.id, 1, "https://example.com")


def test_revoked_engagement_is_blocked(db_session):
    biz = _make_business(db_session)
    eng = _make_engagement(db_session, biz, status=EngagementStatus.REVOKED.value, max_tier_allowed=5)
    with pytest.raises(ScanNotAuthorized):
        maybe_run_scan(db_session, eng.id, 1, "https://example.com")


def test_expired_authorization_is_blocked(db_session):
    biz = _make_business(db_session)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    eng = _make_engagement(
        db_session,
        biz,
        status=EngagementStatus.AUTHORIZED.value,
        max_tier_allowed=5,
        authorization_expires_at=expired,
    )
    with pytest.raises(ScanNotAuthorized):
        maybe_run_scan(db_session, eng.id, 1, "https://example.com")


def test_tier_above_max_allowed_is_blocked(db_session):
    biz = _make_business(db_session)
    eng = _make_engagement(db_session, biz, status=EngagementStatus.AUTHORIZED.value, max_tier_allowed=2)
    with pytest.raises(ScanNotAuthorized):
        maybe_run_scan(db_session, eng.id, 3, "https://example.com")


def test_out_of_scope_host_is_blocked(db_session):
    biz = _make_business(db_session)
    eng = _make_engagement(
        db_session,
        biz,
        status=EngagementStatus.AUTHORIZED.value,
        max_tier_allowed=5,
        in_scope_hosts=json.dumps(["example.com"]),
    )
    with pytest.raises(ScanNotAuthorized):
        maybe_run_scan(db_session, eng.id, 1, "https://not-in-scope.com")


def test_nonexistent_engagement_is_blocked(db_session):
    with pytest.raises(ScanNotAuthorized):
        maybe_run_scan(db_session, 999999, 1, "https://example.com")


def test_authorized_in_scope_engagement_reaches_the_scraper(db_session):
    """The positive case: proves the gate isn't just blocking everything - a
    genuinely authorized, in-scope, in-tier request must actually get through.
    """
    biz = _make_business(db_session)
    eng = _make_engagement(
        db_session,
        biz,
        status=EngagementStatus.AUTHORIZED.value,
        max_tier_allowed=5,
        in_scope_hosts=json.dumps(["example.com"]),
    )
    with pytest.raises(ScraperCalledError):
        maybe_run_scan(db_session, eng.id, 2, "https://example.com")
