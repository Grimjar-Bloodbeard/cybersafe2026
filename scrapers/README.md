# `scrapers/`

This is the actual scraping code: one folder per complexity tier, plus `common/`, the
utilities every tier shares. If you're new to web scraping, read this top to bottom -
it walks through real code that's already running, not toy examples.

## The shape of every tier

Every tier answers the same question - "get me the content of this page" - with a
progressively more capable (and more expensive) tool:

| Tier | Question it answers | Tool |
|---|---|---|
| 1 (`tier1_static/`) | Can I just download the raw HTML? | `requests` + `BeautifulSoup4` |
| 2 (`tier2_playwright/`, coming Week 3) | Does the page need JavaScript to render its real content? | `Playwright` (drives a real browser) |
| 3 (`tier3_scrapy/`, `tier3_asyncio/`, coming Week 4) | I need many pages, fast - how do I not do this one at a time? | `Scrapy`, `asyncio`/`aiohttp` |
| 4 (`common/`, wraps every tier) | How do I behave like a careful, identifiable visitor instead of a flood? | rate limiting, robots.txt compliance, realistic fingerprints |
| 5 (`tier5_ai/`, started ahead of schedule) | The page's structure is too inconsistent for fixed selectors, or raw findings need translating into plain English - now what? | a local LLM (Ollama) reads it like a person would |

**Tier 4 is not a separate step you reach later.** `common/rate_limiter.py` and
`common/robots_check.py` are already used by the Tier 1 scraper - every tier we build
from here on wraps itself in the same good-citizenship layer from its first line of
code, not as an afterthought once the "real" tiers are done.

## `common/` - the shared "good citizenship" layer

### `robots_check.py` - why this exists

`robots.txt` is a plain text file a site publishes (e.g.
`https://example.com/robots.txt`) listing paths it asks automated tools not to visit.
It's not a technical barrier - nothing stops you from ignoring it - which is exactly why
honoring it anyway is the baseline test of whether a scraper is being a good citizen.

`is_allowed(url, user_agent)` fetches and caches the target site's `robots.txt`, then
asks: would this specific URL be allowed for this specific User-Agent? We use `protego`
to parse it (the same library Scrapy uses internally, so our Tier 1 and future Tier 3
code agree on what "allowed" means).

**A real gotcha we hit, worth understanding:** `robots.txt` rules match by *prefix*, not
by exact path or folder. The Wilkes Chamber of Commerce's `robots.txt` has
`Disallow: /list/search`. We initially wanted `/list/searchalpha/a` (their alphabetical
browse page) - and it turns out that's disallowed too, because the string
`/list/searchalpha/a` *starts with* the string `/list/search`. The site almost certainly
meant to block just their live AJAX search results, not the browse pages, but the rule
as written covers both. Our scraper caught this automatically (`is_allowed` returned
`False` and logged a warning) and we adapted by using their `Sitemap.xml` instead - a
route that's explicitly allowed and, as a bonus, led to individual profile pages with
*more* data than the browse pages had. That's the payoff of building the compliance
check as real code instead of eyeballing `robots.txt` once and assuming: it catches
things a human skim would miss.

### `rate_limiter.py` - why this exists

`RateLimiter(requests_per_second=0.5)` means "wait until at least 2 seconds have passed
since my last request, every time, no matter what." It's a token-bucket limiter: think
of it as a bucket that refills at a fixed rate, and every request has to "spend" a
token, blocking (sleeping) if the bucket's empty. This is deliberately conservative -
the target site might technically tolerate faster - because the point isn't "how fast
can we go without getting blocked," it's "behave like a single considerate visitor,"
which is both more ethical and a better long-term relationship with sites we might
scrape repeatedly.

### `storage.py`

Week 1's minimal persistence layer - raw `sqlite3`, no ORM. It exists because Tier 1
needed *somewhere* to put results before the full database schema (built in Week 2,
see `backend/README.md`) existed. Its field names deliberately match the final
SQLAlchemy schema, which is exactly why Alembic could extend this data in place instead
of needing to migrate it from scratch.

## `tier1_static/directory_scraper.py` - walked through

This is the project's first real scraper, and it's a good one to study because it's
short enough to read start to finish and touches every core idea:

1. **`discover_member_urls()`** fetches the Chamber of Commerce's `Sitemap.xml` (a
   standard file sites publish listing their own pages) and pulls out every URL that
   looks like an individual business profile page. This is *better* than crawling link
   by link - the site is directly telling us where everything is.
2. **`fetch(url)`** is the single choke point every request goes through: check
   `robots.txt` first, wait for the rate limiter, then make the request with a
   descriptive `User-Agent` (see below). If any step says no, we return `None` and move
   on - we never silently retry around a "no."
3. **`parse_profile(html, url)`** uses BeautifulSoup's CSS selectors (`soup.select_one`)
   to pull specific fields out of the HTML - business name, category, address, phone,
   website - by matching the CSS classes the Chamber's site actually uses (found by
   inspecting real pages, documented in the function's structure).
4. **`run()`** ties it together: discover URLs, fetch and parse each one, and hand the
   result to `storage.upsert_business()`, which inserts a `businesses` row *and* a
   matching `engagements` row at `status='draft'` - so from the moment a business is
   sourced, it already exists in a state the authorization gate will refuse to scan.

### Why the User-Agent string matters

```python
USER_AGENT = (
    "CyberSafe2026-DirectoryBot/1.0 "
    f"(Wilkes Community College capstone project; contact: {os.environ.get('SCRAPER_CONTACT', ...)})"
)
```

Every HTTP request identifies itself with this. It's the opposite of evasion: if
someone running the Chamber's site notices unusual traffic, this string tells them
exactly what it is and how to reach us. A scraper that fakes a browser's User-Agent to
blend in is doing something different - and for Tier 4 (Week 4-6), we'll draw that line
explicitly: realistic fingerprinting gets *demonstrated* against a sandbox we control,
never used to disguise traffic against a real, permissioned engagement target.

## `tier5_ai/` - translating findings into plain English

This is the piece that turns technical findings into the actual report a student hands
a business owner. It doesn't scrape anything itself - it takes findings (from any
tier) and asks a local AI model (via [Ollama](https://ollama.com), already running on
the team's dev machine, nothing sent to the cloud) to write them up.

- **`schemas.py`** defines the exact shape of a report (a `Pydantic` model - a Python
  class that validates its own data). This gets passed to Ollama as a JSON schema via
  the `format` parameter, which forces the model's response to be valid JSON matching
  that shape - it can't wander off into a paragraph of prose when we need structured
  fields to store in the database.
- **`synthesis.py`** builds the prompt, calls Ollama, and validates the response against
  the schema. If `llama3.1:8b` (the default) produces something that doesn't validate,
  it escalates once to `qwen2.5-coder:14b` before giving up loudly (`RuntimeError`) -
  fail-closed again, same principle as the authorization gate: never hand over a
  guessed or malformed report.
- **`render_markdown()`** turns the validated, structured report into the actual
  Markdown document - organized by the same 4 categories (MFA, phishing exposure,
  backups/ransomware, general hygiene) the team is learning about in Week 6.

Try it: `python -m scripts.demo_tier5_synthesis` runs the whole pipeline against
clearly synthetic sample findings (no real business involved - nothing's been
authorized yet) and writes the result to `data/sample_report.md`.

## Running it

```
python -m scrapers.tier1_static.directory_scraper --limit 5   # quick test
python -m scrapers.tier1_static.directory_scraper              # full run
```

Set `SCRAPER_CONTACT` in your `.env` first (copy `.env.example`) - the scraper works
without it but falls back to a placeholder string, which isn't real good-citizenship
practice for anything beyond local testing.
