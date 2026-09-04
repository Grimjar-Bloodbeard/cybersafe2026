# CyberSafe 2026

A permissioned reconnaissance/security-assessment tool, built as a 5-tier web scraping
ladder for the "How Complex Can You Go? (Complexity Tiers)" capstone presentation. The
full architecture, database design, and 11-week plan live at
[`docs/architecture/PLAN.md`](docs/architecture/PLAN.md) - read that for the *why*
behind every decision below. This README is the map; the module READMEs are the guided
tours; the plan doc is the reference.

## The idea in one paragraph

Most security assessment tools are either free-but-shallow (a single automated scanner)
or expensive-and-manual (a human pentester). This project explores a middle path: build
a real scraping pipeline that gets progressively smarter about *how* it looks at a
website - starting with a plain HTTP fetch and ending with an AI model that reads a page
the way a person would - and use that pipeline to produce plain-English security reports
for real local businesses who've explicitly agreed to be assessed. The 5 tiers aren't
just a grading rubric; they're a genuine engineering escalation path, where each tier
only kicks in when the previous one isn't enough.

## How the pieces fit together

```
Chamber of Commerce site  →  scrapers/tier1_static/  →  businesses + engagements
                                                          (status = "draft")
                                                                │
                                          [ a human sends the scope-of-engagement,
                                            the business signs it, someone marks the
                                            row status = "authorized" ]
                                                                │
                                                                ▼
                             backend/app/auth/gate.py checks status/tier/host/expiry
                                                                │
                                                    only if it passes ──▼
                                       scrapers/ (Tiers 1-5)  →  scan_runs + raw_findings
                                                                │
                                     enrichment APIs (NVD, SSL Labs, crt.sh, ...)
                                                                │
                                          local Ollama synthesizes everything  →  reports
```

Nothing below the dashed line runs for a business that hasn't signed. That's not a
comment in the code - it's an actual `pytest` suite proving it (see `backend/README.md`).

## Repo tour

| Where | What it is | Read next |
|---|---|---|
| `scrapers/` | The actual scraping code, one folder per tier, plus the shared "good citizenship" utilities every tier uses | [`scrapers/README.md`](scrapers/README.md) |
| `backend/` | The database schema, migrations, and the authorization gate | [`backend/README.md`](backend/README.md) |
| `docs/architecture/PLAN.md` | The full approved plan - stack choices, schema, API list, week-by-week milestones | read this for *why*, not just *what* |
| `docs/security_writeup/` | The scope-of-engagement template businesses sign, and (coming) the ethics/legal write-up | |
| `data/cybersafe.db` | The shared SQLite database - gitignored, lives only on the machine that ran the scrapers | |

## Setup

```
python -m pip install -e .
cp .env.example .env   # fill in SCRAPER_CONTACT (a real project contact, not evasion) and NVD_API_KEY
```

## Quick start

```
# Week 1 - source the outreach list from the Chamber of Commerce directory
python -m scrapers.tier1_static.directory_scraper --limit 5   # quick test, 5 businesses
python -m scrapers.tier1_static.directory_scraper              # full run, ~538 businesses

# Week 2 - apply the database schema and run the test suite
cd backend && python -m alembic upgrade head && cd ..
python -m pytest backend/tests/ -v
```

## A few terms, for anyone newer to this stack

- **ORM** (object-relational mapper) - lets you write `Engagement(status="authorized")`
  as a normal Python object instead of hand-writing SQL `INSERT`/`UPDATE` statements.
  We use SQLAlchemy. See `backend/README.md`.
- **Migration** - a versioned, committed-to-git file describing one schema change (e.g.
  "add these 3 columns"). Everyone on the team runs the same migrations in the same
  order, so nobody's local database silently drifts from anyone else's. We use Alembic.
- **`robots.txt`** - a file every website can publish at `/robots.txt` telling automated
  tools which paths they'd rather not be crawled. It's not legally binding, but honoring
  it is the baseline of "good scraper citizenship" - and it's genuinely useful: see
  `scrapers/README.md` for a real case where it caught something we'd have gotten wrong.
- **Rate limiting** - deliberately slowing your own requests down (we default to one
  every 2 seconds) so an automated tool never behaves like a flood of traffic, even
  against a site that would technically allow faster.
- **Fail-closed** - a system design principle: when something goes wrong or is
  ambiguous, the safe behavior is to *refuse* to act, not to proceed anyway. Our
  authorization gate is fail-closed - anything it can't positively confirm as
  authorized gets blocked, not allowed by default.

## Progress log

- **Week 1** (done): repo scaffolded; Chamber of Commerce sourcing scraper built and
  run - 536 businesses, 397 in the three target towns, all landing as unauthorized
  `draft` engagements.
- **Week 2** (done): full database schema applied via Alembic (data preserved - verified
  536/536 rows intact after migration); `assert_engagement_authorized()` gate built with
  8 passing tests; scope-of-engagement template written.
- **Week 3** (next): Tier 2 (Playwright) and the Tier 1 fallback fetcher, tested against
  a sandbox target while real outreach is underway.

Full week-by-week plan: [`docs/architecture/PLAN.md`](docs/architecture/PLAN.md#9-11-week-milestone-plan-from-2026-09-04).
