# CyberSafe 2026

> 🗺️ **[Open the team Battleplan](https://claude.ai/code/artifact/4e1380d0-e875-4f1a-b02f-5d6e9bbeb180)** - the week-by-week plan, onboarding guide, and live progress tracker. Start there, not here, if you're new or just need to know where things stand. It's also linked as this repo's "Website" (top of the GitHub page, right sidebar).

A permissioned reconnaissance/security-assessment tool, built as a 5-tier web scraping
ladder for the "How Complex Can You Go? (Complexity Tiers)" capstone presentation. The
full architecture, database design, and 11-week plan live at
[`docs/architecture/PLAN.md`](docs/architecture/PLAN.md) - read that for the *why*
behind every decision below. This README is the map; the module READMEs are the guided
tours; the plan doc is the reference.

## Team

Picked by each person, not assigned - see [Issue #1](https://github.com/Grimjar-Bloodbeard/cybersafe2026/issues/1) if yours isn't filled in yet.

| Role | Who | Owns |
|---|---|---|
| Lead Scripter / Infrastructure | *TBD* | Core scraping/backend logic, hosting, deployment |
| OSINT Analyst / Data Modeler | Zack | Business research, target profiles, data shape |
| UI / Presentation Wrangler | *TBD* | The live dashboard + the actual presentation |
| Outreach & Engagement Lead | *TBD* | The business pipeline - contact through signature |

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
| `docs/security_writeup/` | The scope-of-engagement template businesses sign, the tier explainer, and (coming) the ethics/legal write-up | [`docs/security_writeup/README.md`](docs/security_writeup/README.md) - **start here for outreach paperwork** |
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

This tracks the *program's* actual week numbers (11 weeks total, mostly outreach/OSINT/
presentation work - only the first 2 weeks are scraper-focused per the curriculum), not a
generic engineering sprint count. See `docs/architecture/PLAN.md` Section 9 for the full
reconciliation and why.

- **Week 1-2** (done, combined): repo scaffolded; Chamber of Commerce sourcing scraper
  built and run - 536 businesses, 397 in the three target towns, all landing as
  unauthorized `draft` engagements. Matches the curriculum's own "functional scraper /
  usable business data" outcome for these weeks.
- **Week 3** (done, ahead of schedule): full database schema applied via Alembic (data
  preserved - verified 536/536 rows intact after migration); `assert_engagement_authorized()`
  gate built with 8 passing tests; scope-of-engagement template written. The program's real
  Week 3 focus is OSINT/community mapping - this gives the real leads somewhere structured
  to land instead of a spreadsheet.
- **Week 4** (next): `/engagements` CRUD, so a real signature can flip a row to
  `authorized` without hand-editing SQL - outreach starts for real this week.
- **Week 7 is the hard deadline**: the full pipeline through Tier 5 (Ollama synthesis) plus
  a fast, live-usable "RFA mode" UI needs to work by the program's mock Rapid Fire
  Assessments week - that's what a student actually runs in front of a business owner.

Full plan: [`docs/architecture/PLAN.md`](docs/architecture/PLAN.md#9-11-week-plan--reconciled-with-the-programs-actual-curriculum-2026-09-04).
