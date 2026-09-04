"""The code-level authorization gate. No scraper module runs against a real
business until a call to assert_engagement_authorized() returns without raising.

See docs/architecture/PLAN.md Section 8 - this is what actually stands between
the Week 1 Chamber of Commerce sourcing output and any real scan being possible,
not just a policy document someone could ignore.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.app.db.models import Engagement, EngagementStatus


class ScanNotAuthorized(Exception):
    """Raised whenever a requested scan fails any authorization check. Callers
    must call assert_engagement_authorized() before invoking any scraper module -
    never after, never in parallel, never "just this once."
    """


def assert_engagement_authorized(
    db: Session, engagement_id: int, requested_tier: int, target_url: str
) -> Engagement:
    engagement = db.get(Engagement, engagement_id)
    if engagement is None:
        raise ScanNotAuthorized(f"engagement {engagement_id} does not exist")

    if engagement.status != EngagementStatus.AUTHORIZED.value:
        raise ScanNotAuthorized(
            f"engagement {engagement_id} is not authorized (status={engagement.status!r})"
        )

    if engagement.authorization_expires_at:
        expires = datetime.fromisoformat(engagement.authorization_expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise ScanNotAuthorized(f"engagement {engagement_id} authorization has expired")

    if requested_tier > engagement.max_tier_allowed:
        raise ScanNotAuthorized(
            f"tier {requested_tier} exceeds max_tier_allowed={engagement.max_tier_allowed} "
            f"for engagement {engagement_id}"
        )

    in_scope_hosts = json.loads(engagement.in_scope_hosts) if engagement.in_scope_hosts else []
    target_host = urlparse(target_url).netloc or target_url
    if target_host not in in_scope_hosts:
        raise ScanNotAuthorized(
            f"host {target_host!r} is not in engagement {engagement_id}'s in_scope_hosts"
        )

    return engagement
