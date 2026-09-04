# CyberSafe 2026

Permissioned reconnaissance/security-assessment capstone project. Full architecture,
tier-by-tier stack, database schema, and 11-week milestone plan live at
`docs/architecture/` (mirrors the approved design doc).

## What this is

A tier-laddered web scraping/assessment pipeline ("How Complex Can You Go?"):

1. **Tier 1** - static fetch (`requests` + `BeautifulSoup4`). First real artifact: the
   Chamber of Commerce directory scraper (`scrapers/tier1_static/directory_scraper.py`)
   that sources the initial Wilkes County business/outreach list.
2. **Tier 2** - headless browser rendering (Playwright).
3. **Tier 3** - concurrent/recursive crawling (Scrapy + asyncio/aiohttp).
4. **Tier 4** - "good scraper citizenship" - rate limiting, robots.txt compliance,
   retry/backoff, realistic fingerprinting. Wraps Tiers 1-3 from the start, not just
   bolted on at the end.
5. **Tier 5** - AI-driven extraction/synthesis via a local Ollama model
   (`llama3.1:8b` default, `qwen2.5-coder:14b` on-demand specialist).

**Every scan requires a signed scope-of-engagement.** No business gets scanned past
Tier 1 sourcing until its `engagements.status` is explicitly `authorized` - enforced in
code (`backend/app/auth/gate.py`, coming Week 2), not just as a policy document.

## Setup

```
python -m pip install -e .
cp .env.example .env   # fill in SCRAPER_CONTACT and NVD_API_KEY
```

## Week 1: Chamber of Commerce sourcing scraper

```
python -m scrapers.tier1_static.directory_scraper          # full run
python -m scrapers.tier1_static.directory_scraper --limit 5  # quick test
```

Populates `data/cybersafe.db` with a `businesses` row and a draft (unauthorized)
`engagements` row per Chamber of Commerce member. This is the literal outreach list -
nothing in it can be scanned until a real business signs a scope-of-engagement and its
row is manually moved to `status='authorized'`.
