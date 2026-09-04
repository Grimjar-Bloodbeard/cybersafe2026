"""Tier 4 'good citizenship' utility, used from Tier 1 onward: robots.txt compliance.

Same parser (protego) Scrapy uses internally, so Tier 1-3 and the eventual Tier 3
Scrapy project honor the same robots.txt semantics.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from protego import Protego

_parser_cache: dict[str, Protego] = {}


def _get_parser(url: str, user_agent: str) -> Protego:
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if origin not in _parser_cache:
        robots_url = urljoin(origin, "/robots.txt")
        try:
            resp = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=10)
            content = resp.text if resp.status_code == 200 else ""
        except requests.RequestException:
            content = ""
        _parser_cache[origin] = Protego.parse(content)
    return _parser_cache[origin]


def is_allowed(url: str, user_agent: str) -> bool:
    return _get_parser(url, user_agent).can_fetch(url, user_agent)


def crawl_delay(url: str, user_agent: str) -> float | None:
    return _get_parser(url, user_agent).crawl_delay(user_agent)
