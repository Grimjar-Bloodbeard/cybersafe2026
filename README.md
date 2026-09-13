# CyberSafe 2026

A student capstone project: a tool that scans a business's public website (only once
they've said yes) and writes a plain-English report on what it finds.

**Start here, not here**: 🗺️ **[Open the team Battleplan](https://claude.ai/code/artifact/4e1380d0-e875-4f1a-b02f-5d6e9bbeb180)** -
what this project is, where we stand, and what's next, explained simply. Everything
else in this repo is code and reference material for when you're actually working on
something specific.

**Not writing code for this project?** You don't need anything below this line - the
Battleplan link above has everything you need. This part is for whoever's touching the
scraper, the database, or the website.

## Run it

```
python -m pip install -e .
cp .env.example .env                                  # fill in the two values it asks for
python -m scrapers.tier1_static.directory_scraper --limit 5   # pulls 5 real businesses
python -m uvicorn backend.app.main:app --reload        # then open http://127.0.0.1:8000/
```

## If you're working on something specific

| Working on... | Read this |
|---|---|
| The scrapers (Tiers 1-5) | [`scrapers/README.md`](scrapers/README.md) |
| The database / who's allowed to be scanned | [`backend/README.md`](backend/README.md) |
| Outreach paperwork for a real business | [`docs/security_writeup/README.md`](docs/security_writeup/README.md) |
| The full architecture and why we made each choice | [`docs/architecture/PLAN.md`](docs/architecture/PLAN.md) |
| Hosting this on the live server | [`docs/architecture/DEPLOYMENT.md`](docs/architecture/DEPLOYMENT.md) |

That's it - the Battleplan has the story, this table has the reference material. Nobody
should have to read all five of those just to understand what the project does.
