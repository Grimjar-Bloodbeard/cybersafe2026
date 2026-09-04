"""Tier 4 'good citizenship' utility, used from Tier 1 onward: a simple token-bucket
rate limiter shared across every tier so nothing hammers a target faster than intended.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, requests_per_second: float = 1.0, min_delay_override: float | None = None):
        self._min_interval = (
            min_delay_override if min_delay_override is not None else (1.0 / requests_per_second)
        )
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            remaining = self._min_interval - (now - self._last_call)
            if remaining > 0:
                time.sleep(remaining)
            self._last_call = time.monotonic()
