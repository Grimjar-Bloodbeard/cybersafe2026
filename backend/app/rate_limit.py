"""In-process rate limiting for the two public POST endpoints. Deliberately
hand-rolled, not slowapi - mirrors scrapers/common/rate_limiter.py's token-
bucket idea for outbound scraping, just keyed by inbound client IP instead.

In-process means: state resets on a PM2 restart (acceptable - worst case is
a brief window of no extra throttling, not a security hole), and does NOT
share across multiple uvicorn workers - this is exactly why
ecosystem.config.js pins --workers 1. If that ever gets bumped up for
performance, this limiter silently becomes N times weaker with no error -
do not raise --workers without rethinking this design.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request


class PerIPRateLimiter:
    def __init__(self, max_requests: int, per_seconds: float):
        self._max_requests = max_requests
        self._window = per_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, client_ip: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._hits[client_ip] if now - t < self._window]
            if len(recent) >= self._max_requests:
                retry_after = int(self._window - (now - recent[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests - please wait before trying again.",
                    headers={"Retry-After": str(retry_after)},
                )
            recent.append(now)
            self._hits[client_ip] = recent


def client_ip(request: Request) -> str:
    # Trustworthy only because nginx's cybersafe.conf is the sole path any
    # real client reaches this app through, and it's the one setting this
    # header from $remote_addr - never a value a client could supply itself.
    return request.headers.get("x-real-ip") or (
        request.client.host if request.client else "unknown"
    )
