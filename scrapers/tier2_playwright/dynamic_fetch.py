"""Tier 2 dynamic scraper: renders a page in a real (headless) browser instead of just
downloading raw HTML, for sites whose real content only shows up after JavaScript runs.

Tier 1's `requests.get()` sees exactly what the server sent, before any client-side code
runs - fine for a page that's already complete HTML, useless for one that starts as an
empty shell and fills itself in with JavaScript (a menu that loads after the page opens,
a report that only appears after clicking a button and waiting on an API call - see our
own demo report page for a real example of the second one). Playwright drives an actual
Chromium browser, so it sees the page the exact way a real visitor's browser would,
JavaScript and all.

Chosen over Selenium (the assignment's other named option) per
docs/architecture/PLAN.md: modern auto-wait (no manual sleep/poll loops for an element to
show up), first-class async support, and built-in network interception - useful for the
assessment itself later, not just this fetch.

playwright-stealth patches over the small tells (a `navigator.webdriver` flag, missing
browser plugins, etc.) that mark an automated Chromium as a bot rather than a person.
Demonstrated only against our own sandbox here, same as Tier 1's User-Agent docstring:
this is about not getting misidentified as something hostile while doing permitted,
polite scraping - never about disguising traffic against a real, permissioned engagement
target.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, str(__file__.rsplit("scrapers", 1)[0]))

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from scrapers.common.rate_limiter import RateLimiter
from scrapers.common.robots_check import is_allowed

# Same "real, honest contact string" reasoning as tier1_static/directory_scraper.py -
# see that file's docstring for why this isn't evasion.
USER_AGENT = (
    "CyberSafe2026-DynamicBot/1.0 "
    f"(Wilkes Community College capstone project; contact: {os.environ.get('SCRAPER_CONTACT', 'set SCRAPER_CONTACT env var')})"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dynamic_fetch")

# Same 2-second-per-request pace as Tier 1 (scrapers/common/rate_limiter.py) - a real
# browser is heavier per request, but "how polite are we being" doesn't change with tier.
_rate_limiter = RateLimiter(requests_per_second=0.5)


async def fetch_rendered(
    url: str,
    click_selector: str | None = None,
    wait_selector: str | None = None,
    timeout_ms: int = 15000,
) -> str | None:
    """Load `url` in a real headless browser and return the fully rendered HTML,
    including anything JavaScript added after the initial page load. Runs through the
    same robots.txt + rate-limit checks as Tier 1 first - a heavier tool doesn't mean a
    less polite one.

    click_selector: an optional element to click after the page loads (e.g. a
    "show more" or "run" button) before capturing - some content only appears after a
    real user interaction, not just page-load JavaScript.
    wait_selector: an optional element to wait for before capturing - more reliable
    than a fixed sleep, since it says "don't grab the page until THIS specific thing
    has actually shown up" instead of just guessing how long that might take.
    """
    if not is_allowed(url, USER_AGENT):
        log.warning("robots.txt disallows %s - skipping", url)
        return None
    _rate_limiter.wait()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=USER_AGENT)
            await Stealth().apply_stealth_async(page)

            try:
                await page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            except Exception as exc:
                log.warning("navigation failed for %s: %s", url, exc)
                return None

            if click_selector:
                try:
                    await page.click(click_selector, timeout=timeout_ms)
                except Exception as exc:
                    log.warning("could not click %r on %s: %s", click_selector, url, exc)

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=timeout_ms)
                except Exception as exc:
                    log.warning("never saw %r on %s: %s", wait_selector, url, exc)

            return await page.content()
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Tier 2 prototype: render a page with a real browser and compare how much "
            "content shows up versus a plain Tier 1 download of the same URL."
        )
    )
    parser.add_argument("url", help="Page to render")
    parser.add_argument("--click", dest="click_selector", default=None, help="CSS selector to click after load, e.g. '#run-btn'")
    parser.add_argument("--wait-for", dest="wait_selector", default=None, help="CSS selector to wait for before capturing, e.g. '#report-card.active'")
    args = parser.parse_args()

    rendered = asyncio.run(fetch_rendered(args.url, args.click_selector, args.wait_selector))
    if rendered is None:
        print("Fetch failed or was disallowed by robots.txt - see the warning above.")
        return

    import requests

    plain = requests.get(args.url, headers={"User-Agent": USER_AGENT}, timeout=15).text

    print(f"Tier 1 (plain download):  {len(plain):>8,} characters of HTML")
    print(f"Tier 2 (real browser):    {len(rendered):>8,} characters of HTML")
    if len(rendered) > len(plain) * 1.05:
        print("-> Tier 2 saw real content Tier 1 missed. This is exactly why Tier 2 exists.")
    else:
        print("-> Not much difference here - this page doesn't need JavaScript to show its real content.")


if __name__ == "__main__":
    main()
