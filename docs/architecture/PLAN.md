# CyberSafe 2026 — Permissioned Recon-as-a-Service Capstone

## Context

11-week cybersecurity capstone (4-person team), presentation titled "How Complex Can You Go?
(Complexity Tiers)". The assignment's own framing is a 5-tier scraper complexity ladder
(static -> headless browser -> concurrent crawl -> evasion -> AI-driven extraction). Rather
than implement one tier, the team is building the full ladder as a live, demoable pipeline —
the tier progression itself is the presentation's narrative device.

The tool is a real reconnaissance/security-assessment pipeline: scrape a business's site
(only once they've signed a written scope-of-engagement), fingerprint its tech stack,
cross-reference findings against vulnerability/config-grading APIs, and have a locally-hosted
LLM synthesize everything into a plain-English risk report. Positioning is the classic
external-recon pentest sales pitch — real, legally-obtained findings make the risk concrete —
kept clean by delivering reports privately to the business and never publishing real findings.

Target businesses are concrete and local: the Wilkes County, NC area (Wilkesboro, North
Wilkesboro, Miller's Creek), starting from the local Chamber of Commerce's business directory.
Hardware for the AI tier is already confirmed (AMD RX 6700 XT / 12GB VRAM, 96GB RAM, Ollama
already running with `llama3.1:8b` and the `qwen2.5-coder` family already pulled).

**Architecture decision (2026-09-04)**: the instructor/team requirement of "just build python
scripts" was weighed directly against using Apify as the Tier 2-4 execution backend. Verdict:
**self-hosted Python throughout**, not Apify. Even framed as authored Python deployed as an
"Apify Actor," a Dockerized cloud deployment reads as "configured a SaaS platform" to a grader
regardless of what's underneath — a real optics/grading-risk problem, not just a technical one.
Self-hosted also maps 1:1 onto the exact tools the assignment names per tier, with zero
ambiguity, and is architecturally simpler (no Docker, no cloud dataset-pull/webhook plumbing).
Apify survives only as an optional, non-critical-path Week 8-10 stretch appendix if time allows.

---

## 1. Tier stack — all self-hosted, literal named tools

| Tier | Literal tools (real authored code) | Notes |
|---|---|---|
| 1 | `requests` + `BeautifulSoup4` (`lxml`) | Two jobs: (a) the Week 1 Chamber-of-Commerce directory scraper, (b) fast static pre-check/fallback fetcher before escalating |
| 2 | `Playwright` for Python (async API) + `playwright-stealth` | Chosen over Selenium: modern auto-wait, first-class async, built-in network/response interception (useful for the assessment itself). Note the choice + rationale in the write-up since Selenium is the assignment's other named option |
| 3 | `Scrapy` (genuine spider project: `CrawlSpider`, `LinkExtractor`, custom `ItemPipeline`) **and** `asyncio` + `aiohttp` recon-sweep module | Two distinct authored artifacts, hitting both named toolsets. Scrapy's `ROBOTSTXT_OBEY=True` + `AUTOTHROTTLE` double as the assignment's required rate-limiting/robots-compliance component |
| 4 | `playwright-stealth` (fingerprint realism), hand-written `RateLimiter` (token bucket), `protego` (robots.txt parsing — same lib Scrapy uses internally), hand-written `ProxyRotator` (sandbox-only), `tenacity` (retry/backoff on 403/429/5xx), descriptive contact-info User-Agent constant | All real authored integrations. Framed as "good scraper citizenship," not WAF-bypass — no proxy rotation/evasion against real permissioned targets, only demoed against the team's own sandbox |
| 5 | `crawl4ai` (`AsyncWebCrawler` + `LLMExtractionStrategy`) pointed at local Ollama (`ollama/llama3.1:8b`, escalating to `ollama/qwen2.5-coder:14b`), Pydantic schema validation | Runs as one self-contained local module — no cross-machine handoff |

**Cross-cutting point for the write-up**: the Tier 4 "good citizenship" utilities
(`rate_limiter`, `robots_check`, `retry`, descriptive UA) wrap Tiers 1-3 from the start, not
just Tier 4. Tier 4 is really where fingerprint-realism and proxy-rotation-*capability* get
added on top of a foundation that was already well-behaved — stronger ethical narrative than
"citizenship only shows up at the advanced tier."

**Known implementation gotcha (flag at Week 1, don't discover mid-project)**: Scrapy runs its
own Twisted reactor, which can't cleanly co-exist inside an `asyncio`-based FastAPI process if
invoked in-process. Pattern: the backend triggers Scrapy as a **subprocess**
(`scrapy crawl <spider> -a engagement_id=...`), with the spider's pipeline writing findings
directly to the shared SQLite DB (or JSON Lines the backend ingests on subprocess exit) —
standard pattern for embedding Scrapy in a larger app, avoids reactor conflicts.

**Tech fingerprinting note**: Wappalyzer's free API/ruleset is gone (now $250/mo). Build
fingerprinting in-house from headers/meta-generator tags/known asset paths, and lean on Tier 5
for ambiguous cases ("what CMS/framework does this page appear to run, given this HTML and
these headers?") — folds Wappalyzer-style work into the AI tier instead of a paywalled vendor.

---

## 2. Target sourcing: Chamber of Commerce scrape (Week 1 — done)

Built as a real, ungated Tier 1 exercise: `scrapers/tier1_static/directory_scraper.py` scrapes
the Wilkes Chamber of Commerce directory (business.wilkeschamber.org, GrowthZone/ChamberMaster
platform). Extracts business name, category, phone, address, website, and profile URL. Output
lands in `businesses` with a corresponding `engagements` row at `status='draft'` — the
code-level gate (Section 8) already blocks any scan against these until a real signature moves
status to `authorized`. **The scraper's output literally is the outreach list.**

**robots.txt finding worth keeping in the write-up**: the obvious route (the alphabetical
browse pages at `/list/searchalpha/<letter>`) turned out to be disallowed — the site's
`Disallow: /list/search` rule is a prefix match, and `/list/searchalpha/...` starts with those
same characters, so it's covered even though that probably wasn't the site owner's intent.
Rather than treat that as a technicality to route around, the scraper instead uses the site's
own `Sitemap.xml` (explicitly allowed) to enumerate all 538 individual member profile pages at
`/list/member/<slug>.htm`, which aren't covered by any Disallow rule — fully compliant, and the
profile pages carry richer data (category, fax) than the listing cards did anyway. Good real
example of "good scraper citizenship" for the presentation: robots.txt said no to the easy
path, so the tool found a compliant one instead of ignoring it.

Note: Chamber membership isn't strictly limited to the three target towns (some members are
regional — includes at least one Georgia address seen in testing). City/state are captured per
record, so filtering to Wilkesboro/North Wilkesboro/Miller's Creek for actual outreach is a
simple query, not a scraping concern.

**Sourcing broadened, 2026-09-16, per the 2026-09-15 team meeting's action items.** The
outreach target grew from "Chamber-listed businesses" to "businesses, churches, town
establishments, and community stakeholders," and a hard rule was added: nothing further than a
30-minute drive from the event. Neither was something the Chamber scraper could give us — it
only ever lists paying Chamber members (no churches), and a city-name filter can't express a
drive-time boundary (it already missed the known Georgia address above).

Two real additions, not a rework of the Chamber scraper:

- `scrapers/tier1_static/community_scraper.py` — sources churches/community centers/social
  facilities across Wilkes County via OpenStreetMap's Overpass API (free, no key, same
  self-hosted-friendly spirit as the rest of this project). 242 real entries added. Needed a
  real retry/backoff addition for the first time in this project (`scrapers/common/retry.py`,
  `tenacity`) after Overpass returned a genuine 504 under load — exactly the Tier 4 utility this
  section already named but hadn't actually needed yet.
- `scrapers/common/geocode.py` — backfills latitude/longitude (new `businesses` columns) for
  the ~536 Chamber-sourced rows, which only ever had a street address. Uses OSM Nominatim (1
  req/sec, per its own usage policy — respected the same way robots.txt is). Honest about
  misses: 225 of 536 addresses found no match and are left `NULL`, not guessed.

`scripts/export_outreach_list.py` now computes real straight-line distance from the event
location (Wilkes Community College) instead of filtering by city name, flags anything beyond 20
miles (a documented, generous proxy for "30-minute drive" on this county's rural roads, not a
real routing calculation) as excluded, and — fail-closed, same principle as the authorization
gate — flags anything that couldn't be geocoded as "needs manual check" rather than assuming
either way. Also added blank tracking columns for Jovan's 3-step outreach sequence from the same
meeting (initial intro → ~2wk follow-up → ~2wk final email), since "central tracking" now means
outreach-cadence progress, not just a signed/not-signed flag.

---

## 3. Repository structure

```
D:\cybersafe2026\
  main.py                          # local dev CLI (typer/click) — manual tier-run entrypoint
  pyproject.toml / README.md / .env.example / .gitignore

  scrapers/
    common/
      rate_limiter.py              # Tier 4: token-bucket limiter, used from Tier 1 onward
      robots_check.py              # Tier 4: protego-based compliance, used from Tier 1 onward
      proxy_rotator.py             # Tier 4: pluggable rotation — sandbox-only demo
      fingerprint.py               # Tier 4: descriptive UA constant, playwright-stealth wiring
      retry.py                     # Tier 4: tenacity-based backoff wrapper
    tier1_static/
      directory_scraper.py         # Chamber of Commerce sourcing — Week 1, DONE
      static_fetch.py              # requests+BS4 quick-check / fallback fetcher
    tier2_playwright/
      browser_crawler.py           # Playwright renderer, form/click/scroll handling
      selectors/
    tier3_scrapy/                  # genuine Scrapy project
      scrapy.cfg
      tier3_scrapy/
        spiders/engagement_spider.py
        pipelines.py
        settings.py                # ROBOTSTXT_OBEY, AUTOTHROTTLE, custom UA
    tier3_asyncio/
      recon_sweep.py                # aiohttp/asyncio concurrent path+header sweep
    tier5_ai/
      crawl4ai_extractor.py         # crawl4ai + Ollama LLMExtractionStrategy, model escalation
      schemas.py                    # Pydantic extraction schemas
      synthesis.py                  # cross-source report synthesis prompt/call

  backend/                          # FastAPI orchestrator — Tailscale-gated; calls scrapers/ directly
    app/
      main.py
      api/
        engagements.py
        scans.py                    # trigger gate -> pipeline_runner
        sourcing.py                 # trigger/review directory_scraper.py runs -> businesses table
        reports.py
      pipeline/
        pipeline_runner.py          # tier-escalation orchestration: 1 -> 2 -> 3 -> (4 wraps all) -> 5 fallback
        enrichment/
          nvd_client.py
          ssl_labs_client.py
          crtsh_client.py
          shodan_internetdb_client.py
          headers_grader.py
          securitytrails_client.py
        anomaly_detect.py
      db/
        models.py
        migrations/
        session.py
      auth/
        gate.py
    tests/
    requirements.txt

  frontend_public/                  # showcase, linked from codynoah.net — static, no live DB access
  frontend_admin/                   # live-execution/admin UI — Tailscale-only, talks only to backend/

  docs/
    security_writeup/
      scope_of_engagement_template.md
      ethics_and_legal.md
      tier4_good_citizenship_stack.md   # how rate_limiter+robots_check+retry+stealth compound, self-hosted
      data_handling_policy.md
    architecture/PLAN.md              # this file
    presentation/

  scripts/
    seed_demo_data.py             # generates anonymized public-showcase dataset
```

---

## 4. Database schema (SQLite, SQLAlchemy + Alembic in Week 2; minimal raw-sqlite3 version live now)

- **`businesses`** — id, legal_name, contact_name, contact_email, website_root_url,
  **source** (`chamber_directory_scrape`/`referral`/`manual`/`other`), **sourced_at**,
  **directory_category**, created_at
- **`engagements`** — id, business_id FK, scope_document_text, in_scope_hosts (JSON),
  out_of_scope_notes, authorized_by_signature_name, authorized_at (nullable),
  authorization_expires_at, **status** (`draft`/`pending_signature`/`authorized`/`revoked`/
  `expired`/`completed`), **max_tier_allowed**, rate_limit_override, **outreach_notes** (free
  text) — the literal legal/code gate
- **`scan_runs`** — id, engagement_id FK, tier_requested, target_url, started_at/completed_at,
  status, triggered_by, aborted_reason
- **`raw_findings`** — id, scan_run_id FK, page_url, http_status, extraction_method
  (`css_selector`/`tier5_llama3.1`/`tier5_qwen2.5-coder`/`manual_review_needed`),
  extraction_confidence, raw_html_ref, extracted_json
- **`tech_fingerprints`**, **`http_headers_findings`**, **`tls_findings`** — per-scan detail tables
- **`cve_matches`** — scan_run_id, tech_fingerprint_id, cve_id, cvss_score, severity,
  match_confidence, status (`unreviewed`/`confirmed_relevant`/`false_positive`)
- **`anomalies`** — rule-based (missing/misconfigured headers, outdated TLS, exposed-but-not-
  exploited paths like `.git`/`.env`, vulnerable server-version strings, stale/dangling
  subdomains from crt.sh) — no ML needed at this scope
- **`reports`** — engagement_id, scan_run_id, executive_summary_text, full_report_markdown,
  risk_rating, delivered_at, access_token (UUID), is_public (default false),
  **reviewed_by_human** (bool — enforced gate before delivery)
- **`demo_showcase_runs`** — anonymized_business_label, tier_demonstrated,
  synthetic_or_redacted (always true), summary_text — the *only* table the public frontend
  can read, fully decoupled from live engagement data

---

## 5. Enrichment APIs (vetted)

| API | Gives | Notes |
|---|---|---|
| NVD API 2.0 | CVE lookup by CPE/keyword | Request free API key Week 1 (approval isn't instant); no key = 5 req/30s, keyed = 50 req/30s; cache matches, always store `match_confidence`, human review before a match reaches a report |
| Qualys SSL Labs API v4 | TLS/cert grading (A-F) | Free for infra you/a consenting party own; async start+poll, ~1-2 min/host |
| crt.sh | Subdomain discovery via CT logs | No auth/official limit but community infra — space requests as Tier-4 good-citizen practice |
| Shodan InternetDB | Passive open-ports/services/CVE snapshot per IP | No key needed; ethically clean — lookup against existing passive data, not an active scan we initiate |
| In-house header grading | CSP/HSTS/X-Frame-Options/etc. scoring | securityheaders.com's public API was discontinued — build the rubric in-house from data the crawler already has |
| SecurityTrails (stretch, Week 8-9) | Passive DNS/subdomain corroboration | Free tier 2,500 queries/mo |
| SpiderFoot (added 2026-09-14) | Cross-check via 200+ OSINT modules — CVEs, exposed files, TLS issues, malicious-host flags | See `scrapers/enrichment/` |

**Deliberately excluded**: Have I Been Pwned (paid now, and breach/credential data brushes
the "no credential attacks" scope boundary — document as a conscious exclusion). CAPTCHA
solvers/residential proxies against real targets.

**Architecture decision (2026-09-14): SpiderFoot, self-hosted, run as a subprocess.**
The team's mentors showed SpiderFoot (github.com/smicallef/spiderfoot, MIT licensed) in
a meeting. Unlike the earlier Apify call, this isn't a hosted/configured SaaS platform —
it's self-hosted, open-source Python run on our own machine, the same category as Scrapy
or Playwright, which this project already treats as legitimate frameworks to build real
orchestration around. `scrapers/enrichment/spiderfoot_scan.py` runs it exactly the way
Scrapy is already planned to run (subprocess, own code owns the gate check + parsing),
curates its `-u passive`-only module output down to this project's 4 report categories
(`EVENT_CATEGORY_MAP`), and feeds it into the same Tier 5 Ollama synthesis every other
source uses. Vendored at gitignored `vendor/spiderfoot/` (own dependencies, own venv,
never committed) rather than a git submodule — one clone away from a beginner-hostile
git workflow. One real gap found while mapping its event types: SpiderFoot checks SPF
but has no dedicated DMARC/DKIM check, so that part of the phishing-exposure category
still needs our own DNS enrichment client.

---

## 6. Ollama / Tier 5 integration

1. Selector hit/miss check after Tiers 1-3 run (or DOM structure diverging from a
   previously-seen layout) flags a page for Tier 5 instead of silently dropping it.
2. `crawl4ai_extractor.py` fetches flagged pages directly (or reuses already-fetched HTML if
   the pinned crawl4ai version supports it without a second network hit — worth a Week 7 spike
   to confirm and avoid double-fetching), converts to markdown, calls Ollama's `/api/chat` with
   a Pydantic-derived JSON schema via `format=` (constrains generation; Pydantic validates
   after). Prompt instructs `null` for anything absent — never guess.
3. **Model routing**: `llama3.1:8b` default, `keep_alive` tuned to stay resident. On validation
   failure or a known-messy page, escalate to `qwen2.5-coder:14b` (on-demand, fits 12GB VRAM).
   Second failure -> `manual_review_needed`, raw content retained, nothing fabricated.
4. Separate synthesis pass after a full scan run + enrichment completes: one larger-context
   call takes all structured findings and produces the plain-English executive summary/report
   prose — distinct from and after per-page extraction.
5. `qwen2.5-coder:32b` documented as an escape hatch (spills into 96GB system RAM, slower),
   not in the default flow. Vision models (`llama3.2-vision:11b`, `minicpm-v`) noted as an
   optional stretch, not critical path.

---

## 7. Web UI split

**Public showcase** (`frontend_public`, linked from codynoah.net, e.g. `cybersafe.codynoah.net`)
— static build, reads only a periodically-generated static JSON export of
`demo_showcase_runs`, zero live DB access. Content: tier-ladder explainer, methodology/ethics
page, 2-3 anonymized example runs, sample report layout, contact form that only emails the
team (never touches the pipeline).

**Status, 2026-09-12**: the demo report + registration pages (not yet the real scan-triggering
tool described below) are live at `cybersafe.codynoah.net` — see
`docs/architecture/DEPLOYMENT.md` for the full runbook. That's safe to be public precisely
because it can't trigger a real scan against a real business. **The Tailscale-gating
requirement below still applies in full** the day the real admin/live-execution tool
(Tiers 2-5 against authorized engagements) actually gets built — don't skip it then just
because the demo page didn't need it.

**Admin/live-execution** (`frontend_admin`) — talks only to `backend/`, runs at a Tailscale
MagicDNS name, **tailnet-only by default** (`tailscale serve`), basic auth in front even
within the tailnet. During an actual presentation, enable `tailscale funnel` on that one port
for the demo window only, then disable it — a runbook step, not standing config. Only place
engagements get authorized, scans get triggered (through the gate), and reports get
reviewed/marked delivered.

**Report delivery** — never published publicly; generated as Markdown/PDF and emailed
directly to the business contact, or a time-boxed Funnel-only token link. `reviewed_by_human`
must be true before delivery fires. Report includes an explicit "what we did NOT test" section
reinforcing scope boundaries structurally.

**Explicit UI requirement**: once a scan's synthesis pass completes, `frontend_admin` shows a
"Download Report" action (renders `reports.full_report_markdown` to PDF on demand, e.g. via
`weasyprint`/`markdown-pdf`) directly on the scan's detail page — the team can pull the
finished, plain-English document immediately after a scan, review it, then decide whether to
email it or hand it over live. This is the literal "translate the raw scraper output into
something a business owner can read" deliverable, and doubles as the artifact you hand a
non-technical audience during the presentation itself.

---

## 8. Code-level authorization gate (not just a paper process)

`backend/app/auth/gate.py`: `assert_engagement_authorized(engagement_id, requested_tier, target_url)`,
called at the top of `POST /engagements/{id}/scans` before any scraper module runs. Checks:
status == `authorized`, not expired, `requested_tier <= max_tier_allowed`, target host is in
`in_scope_hosts`. On failure: raise, log to `scan_runs.aborted_reason`, **never runs a
scraper**. Direct unit tests (Week 3-4) asserting no scraper call happens for
unauthorized/expired/wrong-tier/wrong-host cases — this is also the literal thing standing
between the Week 1 directory-scrape output and any real scan being possible.

---

## 9. 11-week plan — reconciled with the program's actual curriculum (2026-09-04)

**Superseded the original version of this section**, which was scheduled against generic
software-engineering milestones with no connection to what the program actually has
planned each week. The real curriculum (provided by the program, ~14.5 team-hours/week
covering *everything* - outreach, OSINT, presentation prep, and tech, not just coding)
spends only its first two weeks on the scraper itself, then shifts almost entirely to
outreach, community research, cybersecurity literacy, and presentation/consulting
skills - with **Week 7 ("Rapid Fire Assessments") as the real hard deadline** for the
AI pipeline to be live and usable, not an arbitrary sprint boundary. Technical work from
here on is scheduled to *support* each week's actual curriculum focus, not compete with it.

**Decision (2026-09-04): keep the full AI-driven tier ladder - not scaled back - but
reframed as the engine that makes a Rapid Fire Assessment actually rapid.** Instead of a
student manually working through a security questionnaire with a business owner, they
run the tool live (in person, per the program), get a plain-English report in minutes,
and spend their actual skill-building time on the part the curriculum teaches - reading
the report to a non-technical owner, handling questions, making the case. The tech
should make their in-person delivery look sharp, not be a second, competing project.

| Program Week | Curriculum focus | Tech build target | Status |
|---|---|---|---|
| 1 | Welcome, Python foundations, team orientation | Repo scaffolded, Ollama sanity-checked | **Done** |
| 2 | Python + scraper build → "functional scraper / usable business data" | Chamber of Commerce directory scraper - 536 businesses sourced, 397 in the 3 target towns | **Done** |
| 3 | OSINT + community mapping, build a flyer, initial lead lists | Full DB schema + Alembic (data preserved) + the authorization gate (8/8 tests) - so real leads land somewhere structured, not a spreadsheet | **Done, ahead of schedule** |
| 4 | Outreach foundations - elevator pitch, first calls, real outreach begins | `/engagements` CRUD so a real signature can flip a row to `authorized` without hand-editing SQL; scope-of-engagement doc ready to send | Next |
| 5 | Outreach + presentation building - story structure, event planning | Tier 2 (Playwright, render + extract) + Tier 1 fallback fetcher, tested against a team sandbox while real signatures are still coming in | |
| 6 | Small business cybersecurity - MFA, phishing, backups, ransomware, translating tech to non-technical people | Tier 3 (Scrapy + asyncio/aiohttp) + enrichment APIs (NVD, header grading, crt.sh, SSL Labs, Shodan InternetDB), **organized around exactly these 4 categories** - not a generic CVE dump. See the mapping below. | |
| 7 | **Rapid Fire Assessments - mock RFAs** | **Hard deadline**: Tier 5 (Ollama synthesis) + a fast, guided "RFA mode" UI a student can run live with a business owner sitting there, ending in a plain-English report | |
| 8 | Public speaking + presentation development | Tool stability/bugfix only - no new features competing with practice time | |
| 9 | Presentation readiness + outreach push | Same - polish based on what breaks during real mock-RFA use | |
| 10 | Final prep + consulting skills, dress rehearsal | Full dry run of the RFA flow end-to-end; presentation-ready state locked | |
| 11 | **Community event** - live delivery, real RFAs performed | Tool used live. Nothing new ships this week. | |

**How Week 6's 4 categories map onto what the tool actually checks and reports on** (so
the report a student hands a business owner speaks the exact language they were just
taught to translate, not a generic security scan):

- **MFA** - can we tell from public signals whether login pages support/enforce MFA
  (e.g. presence of an MFA prompt path, known IdP integration)? Framed as "can we tell
  if an attacker who guessed a password would be stopped."
- **Phishing exposure** - SPF/DKIM/DMARC DNS record presence (a real, checkable, public
  signal of whether the business's domain can be spoofed in phishing emails).
- **Backups/ransomware exposure** - publicly exposed admin panels, default logins, or
  known-vulnerable software versions that are common ransomware entry points; framed as
  "what's the front door an attacker would try first."
- **General hygiene** - HTTPS enforcement, security headers, TLS grade, exposed
  `.git`/`.env` files - the baseline "how careful is this business's web presence."

Every finding in the eventual report should be traceable to one of these 4 buckets, so
the report *is* the plain-language translation exercise Week 6 teaches, not a separate
artifact from it.

---

## Verification

- **Gate tests** (Week 3-4): `pytest` against `assert_engagement_authorized` — assert no
  scraper module is invoked for unauthorized/expired/wrong-tier/wrong-host inputs.
- **End-to-end scan**: trigger a scan against a sandbox/test engagement through the real gate,
  confirm findings land correctly in SQLite.
- **Scrapy subprocess isolation**: confirm `scrapy crawl` runs cleanly as a subprocess from
  the FastAPI backend without reactor conflicts.
- **Tier 5 fallback proof**: run against an intentionally selector-hostile test page, confirm
  routing to `llama3.1:8b`, escalation to `qwen2.5-coder:14b` on forced validation failure,
  and landing in `manual_review_needed` on a forced second failure — never fabricates data.
- **Report gate**: confirm delivery endpoint refuses to fire while `reviewed_by_human` is false.
- **Public/private isolation**: confirm `frontend_public` build has no code path capable of
  querying anything but the static `demo_showcase_runs` export.
- **Tailscale posture**: confirm the admin UI is unreachable from outside the tailnet by
  default, and that Funnel is only ever enabled manually per the runbook.
