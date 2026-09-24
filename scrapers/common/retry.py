"""Tier 4 'good citizenship' utility, used from Tier 1 onward (see
docs/architecture/PLAN.md Section 1): retry/backoff for a request that failed
transiently (403/429/5xx) - never for a request that was flatly refused
(404, robots.txt disallow), where retrying just adds pointless load.

Built for real, 2026-09-16: the community scraper's Overpass API calls hit a
real 504 (server-side load on a shared public API, not our fault and not
something more traffic from us fixes on the first try) - this is that first
genuine need, not a speculative addition.
"""
from __future__ import annotations

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_transient_http_error(exc: BaseException) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is not None:
        return status_code == 429 or status_code >= 500
    # A connection-level failure (timeout, reset) is also worth one retry -
    # a single dropped packet shouldn't fail an entire scrape run.
    return isinstance(exc, (ConnectionError, TimeoutError))


# 3 attempts total, waiting 2s/4s/8s (capped) between them - long enough to
# ride out a brief spike on shared community infrastructure like Overpass,
# short enough not to stall a scrape run for minutes over one bad request.
retry_transient = retry(
    retry=retry_if_exception(_is_transient_http_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, max=8),
    reraise=True,
)
