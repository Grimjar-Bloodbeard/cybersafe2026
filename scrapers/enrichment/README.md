# `scrapers/enrichment/`

Cross-references a target against sources beyond what our own tiers directly fetch -
right now, that's [SpiderFoot](https://github.com/smicallef/spiderfoot) (MIT licensed),
a real, established OSINT tool with 200+ modules. We didn't write SpiderFoot - what we
wrote is the part that decides which of its findings actually matter for this project's
report, and translates its output into our own shape.

## One-time setup

SpiderFoot isn't a normal pip dependency - it's a full application with its own
requirements, so it lives in a gitignored `vendor/spiderfoot/` folder instead of being
committed to this repo (nobody wants a 900-file clone of someone else's project living
inside ours). Run this once, locally:

```
python -m scrapers.enrichment.setup_spiderfoot
```

This clones SpiderFoot and installs its dependencies into their own virtual
environment (`vendor/spiderfoot/.venv`), kept separate from this project's venv since
SpiderFoot pins some much older library versions that would otherwise conflict.

## What `spiderfoot_scan.py` actually does

1. **`run_passive_scan(target_host)`** runs SpiderFoot as a subprocess (`sf.py -s
   <host> -u passive -o json`) - the exact same "run an established framework as a
   subprocess, own code handles the orchestration" pattern this project already uses
   for Scrapy (see `docs/architecture/PLAN.md` Section 1). `-u passive` is SpiderFoot's
   own built-in selection of non-intrusive modules only - it never touches anything
   outside simple, passive lookups.
2. **`to_report_findings(events)`** maps SpiderFoot's ~150 event types onto this
   project's 4 report categories (MFA, phishing exposure, backups/ransomware, general
   hygiene - see `PLAN.md` Section 9). Most of SpiderFoot's findings aren't relevant to
   a small-business security report (WiFi access points nearby, Bitcoin addresses,
   Wikipedia edits) - `EVENT_CATEGORY_MAP` in `spiderfoot_scan.py` is the actual,
   readable list of what we kept and why.

**A real gap worth knowing about:** SpiderFoot's core modules check for an SPF DNS
record but have no dedicated DMARC/DKIM check. Our own planned DNS enrichment client
(`PLAN.md` Section 5) still needs to check those directly - SpiderFoot doesn't make
that redundant.

## Not wired into a real scan yet

There's no real scan-triggering admin tool built yet (`PLAN.md` Section 7), so this
only ever runs against a domain Cody genuinely owns (see
`scripts/demo_spiderfoot_synthesis.py`), never a real business's site. When the real
admin tool exists, `run_passive_scan()` must be called *after*
`assert_engagement_authorized()` succeeds - same non-negotiable rule as every other
tier.

## Try it

```
python -m scripts.demo_spiderfoot_synthesis codynoah.net
```

Runs a real passive scan, synthesizes it through the local Ollama pipeline exactly
like the existing demo, and writes a plain-English report to
`data/spiderfoot_report.md`.
