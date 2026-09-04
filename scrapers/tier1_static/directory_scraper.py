"""Tier 1 static scraper: sources the initial business/prospect list from the Wilkes
Chamber of Commerce directory (Wilkesboro / North Wilkesboro / Miller's Creek, NC).

This is deliberately the project's very first scraper: reading a public business
directory (name/category/phone/address/website) is categorically different from
scanning a live company's own infrastructure, so it needs no signed authorization.
Its output *is* the outreach list - every business lands in the DB with a draft,
unauthorized engagement (see scrapers/common/storage.py) that the Week 2 code-level
gate will refuse to scan until a real signature changes that.

Site: business.wilkeschamber.org, built on the GrowthZone/ChamberMaster platform.

robots.txt gotcha found and respected (2026-09-04): "Disallow: /list/search" is a
prefix match per the robots.txt spec, so it also covers /list/searchalpha/<letter> -
the alphabetical browse pages initially looked like the obvious route, but they're
disallowed. Real 'good citizenship' example for the write-up: instead of treating that
as a technicality to route around, this scraper uses the site's own Sitemap.xml
(explicitly allowed) to enumerate individual member profile pages at
/list/member/<slug>.htm, which are NOT covered by any Disallow rule - fully compliant,
and the profile pages carry richer data (category, fax) than the listing cards did.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(__file__.rsplit("scrapers", 1)[0]))

from scrapers.common.rate_limiter import RateLimiter
from scrapers.common.robots_check import is_allowed
from scrapers.common.storage import get_connection, init_db, upsert_business

BASE_URL = "https://business.wilkeschamber.org"
SITEMAP_URL = BASE_URL + "/SiteMap.xml"
MEMBER_ID_RE = re.compile(r"-(\d+)\.htm$")

# A real, honest contact string, not evasion - set SCRAPER_CONTACT via .env/environment
# so the target site's own logs can identify this as the class project's traffic.
USER_AGENT = (
    "CyberSafe2026-DirectoryBot/1.0 "
    f"(Wilkes Community College capstone project; contact: {os.environ.get('SCRAPER_CONTACT', 'set SCRAPER_CONTACT env var')})"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("directory_scraper")

_rate_limiter = RateLimiter(requests_per_second=0.5)  # one request every 2s - deliberately gentle


def fetch(url: str) -> str | None:
    if not is_allowed(url, USER_AGENT):
        log.warning("robots.txt disallows %s - skipping", url)
        return None
    _rate_limiter.wait()
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except requests.RequestException as exc:
        log.warning("request failed for %s: %s", url, exc)
        return None
    if resp.status_code != 200:
        log.warning("unexpected status %s for %s", resp.status_code, url)
        return None
    return resp.text


def discover_member_urls() -> list[str]:
    xml = fetch(SITEMAP_URL)
    if not xml:
        return []
    soup = BeautifulSoup(xml, "xml")
    urls = [
        loc.get_text(strip=True)
        for loc in soup.find_all("loc")
        if "/list/member/" in loc.get_text(strip=True)
    ]
    log.info("Discovered %d member profile URLs from sitemap", len(urls))
    return urls


def parse_profile(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1.gz-pagetitle")
    if not title_el:
        return None
    legal_name = title_el.get_text(strip=True)

    categories = [c.get_text(strip=True) for c in soup.select("span.gz-cat")]
    directory_category = ", ".join(categories) if categories else None

    street = city = state = postal_code = None
    addr_el = soup.select_one("li.gz-card-address")
    if addr_el:
        street_el = addr_el.select_one("[itemprop='streetAddress']")
        city_el = addr_el.select_one("[itemprop='addressLocality']")
        state_el = addr_el.select_one("[itemprop='addressRegion']")
        zip_el = addr_el.select_one("[itemprop='postalCode']")
        street = street_el.get_text(strip=True) if street_el else None
        city = city_el.get_text(strip=True) if city_el else None
        state = state_el.get_text(strip=True) if state_el else None
        postal_code = zip_el.get_text(strip=True) if zip_el else None

    phone = None
    phone_el = soup.select_one("li.gz-card-phone [itemprop='telephone']")
    if phone_el:
        phone = phone_el.get_text(strip=True)

    website = None
    website_el = soup.select_one("li.gz-card-website a[itemprop='url']")
    if website_el:
        website = website_el.get("href")

    match = MEMBER_ID_RE.search(url)
    member_id = match.group(1) if match else url

    return {
        "directory_member_id": member_id,
        "legal_name": legal_name,
        "profile_url": url,
        "website_root_url": website,
        "phone": phone,
        "street_address": street,
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "directory_category": directory_category,
        "source": "chamber_directory_scrape",
    }


def run(limit: int | None = None) -> dict:
    init_db()
    member_urls = discover_member_urls()
    if limit:
        member_urls = member_urls[:limit]

    total_seen = 0
    total_new = 0
    with get_connection() as conn:
        for url in member_urls:
            html = fetch(url)
            if not html:
                continue
            parsed = parse_profile(html, url)
            if not parsed:
                log.warning("could not parse profile at %s", url)
                continue
            total_seen += 1
            _, was_new = upsert_business(conn, parsed)
            if was_new:
                total_new += 1

    log.info("Done. Seen: %d, newly added: %d", total_seen, total_new)
    return {"seen": total_seen, "new": total_new}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape the Wilkes Chamber of Commerce directory")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only scrape the first N member profiles (for testing)",
    )
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
