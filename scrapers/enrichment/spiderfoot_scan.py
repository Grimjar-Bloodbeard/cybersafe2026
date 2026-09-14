"""Runs SpiderFoot (github.com/smicallef/spiderfoot, MIT licensed) in
passive-only mode against one host, and maps its findings onto the same
{"category", "detail"} shape scrapers/tier5_ai/synthesis.py expects.

This is enrichment, not one of the 5 authored complexity tiers - SpiderFoot
is a real, established OSINT tool someone else wrote (200+ modules, MIT
license, vendored at vendor/spiderfoot/, not committed to this repo - see
vendor/spiderfoot/README.md in this file's own folder for the one-time
setup). Our own authored work here is: curating which of its findings
actually matter for this project's 4 report categories, and mapping its
event taxonomy onto them - the same "translate raw technical output into
something a business owner can read" job every other source in this
pipeline does.

Not wired into the authorization gate yet, because the real scan-triggering
admin tool (docs/architecture/PLAN.md Section 7) doesn't exist yet either.
When it does: call backend.app.auth.gate.assert_engagement_authorized()
BEFORE run_passive_scan(), exactly like every other tier - never after,
never skipped. Until then, this only ever runs against domains Cody owns
outright (see scripts/demo_spiderfoot_synthesis.py).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parents[2] / "vendor" / "spiderfoot"
SF_PYTHON = VENDOR_ROOT / ".venv" / "Scripts" / "python.exe"
SF_ENTRYPOINT = VENDOR_ROOT / "sf.py"

DETAIL_MAX_LENGTH = 500

# SpiderFoot's human-readable event descriptions -> our 4 report categories
# (docs/architecture/PLAN.md Section 9). Anything not listed here is real
# data SpiderFoot found that we don't have a category for yet - it's real
# information, just not reported on until this mapping grows.
#
# Known gap worth stating outright: SpiderFoot's core modules check SPF but
# have no dedicated DMARC/DKIM check, so our own DNS enrichment still needs
# to cover those directly (PLAN.md Section 5) - this isn't fully redundant
# with what SpiderFoot gives us.
EVENT_CATEGORY_MAP: dict[str, str] = {
    # MFA / login security - no dedicated passive MFA signal exists; a
    # discovered login form is the closest thing, framed honestly in the
    # detail text below (see tier_explainer_one_pager.md's own phrasing).
    "URL (Accepts Passwords)": "mfa",
    # Phishing exposure - can this domain be spoofed in a phishing email?
    # Deliberately NOT mapped: "DNS SPF Record" and "Email Gateway (DNS MX
    # Records)". SpiderFoot only emits these when the record EXISTS - having
    # one is normal and not itself a finding (it's the ABSENCE of SPF that's
    # the real risk signal, which needs its own dedicated check, since
    # SpiderFoot has no "record missing" event to report). Mapping mere
    # presence into a risk category was tested directly against
    # codynoah.net and reliably produced a fabricated claim ("eforward is
    # known to be used by spammers") with nothing in the actual finding to
    # support it - the model filled the gap left by a neutral fact forced
    # into a risk-framed category. Left unmapped on purpose, not an oversight.
    "Hacked Email Address": "phishing_exposure",
    "Disposable Email Address": "phishing_exposure",
    "Malicious E-mail Address": "phishing_exposure",
    # Backups / ransomware exposure - known entry points and existing trouble
    "Vulnerability - CVE Critical": "backups_ransomware",
    "Vulnerability - CVE High": "backups_ransomware",
    "Vulnerability - CVE Medium": "backups_ransomware",
    "Vulnerability - CVE Low": "backups_ransomware",
    "Vulnerability - General": "backups_ransomware",
    "Vulnerability - Third Party Disclosure": "backups_ransomware",
    "Interesting File": "backups_ransomware",
    "Historic Interesting File": "backups_ransomware",
    "Defaced": "backups_ransomware",
    "Defaced IP Address": "backups_ransomware",
    "Open TCP Port": "backups_ransomware",
    "Software Used": "backups_ransomware",
    "Malicious IP Address": "backups_ransomware",
    "Malicious Internet Name": "backups_ransomware",
    # General hygiene - baseline web/TLS/header care
    "SSL Certificate Expired": "general_hygiene",
    "SSL Certificate Expiring": "general_hygiene",
    "SSL Certificate Host Mismatch": "general_hygiene",
    "HTTP Headers": "general_hygiene",
    "Non-Standard HTTP Header": "general_hygiene",
    "Web Technology": "general_hygiene",
    "Web Server": "general_hygiene",
}


class SpiderFootNotSetUp(Exception):
    """Raised when vendor/spiderfoot/.venv doesn't exist yet - see
    scrapers/enrichment/README.md for the one-time setup steps.
    """


def run_passive_scan(target_host: str, timeout_seconds: int = 600) -> list[dict]:
    """Runs SpiderFoot's own '-u passive' module selection (SpiderFoot's own
    curation of which of its modules are non-intrusive) against one host.
    Returns the raw events exactly as SpiderFoot reported them - mapping to
    our categories happens separately in to_report_findings(), so the raw
    data is always available even for event types we don't map yet.
    """
    if not SF_PYTHON.exists():
        raise SpiderFootNotSetUp(
            "vendor/spiderfoot/.venv doesn't exist - see "
            "scrapers/enrichment/README.md for the one-time setup."
        )

    result = subprocess.run(
        [str(SF_PYTHON), str(SF_ENTRYPOINT), "-s", target_host, "-u", "passive", "-o", "json", "-q"],
        cwd=VENDOR_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SpiderFoot scan of {target_host!r} failed: {result.stderr.strip()[-2000:]}")

    decoder = json.JSONDecoder()
    events = []
    for line in result.stdout.splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        try:
            # raw_decode ignores trailing garbage after the first valid
            # object - SpiderFoot appends a stray "[]" after the final
            # event on completion, which plain json.loads() rejects.
            event, _ = decoder.raw_decode(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
    return events


def to_report_findings(events: list[dict]) -> list[dict]:
    """Maps raw SpiderFoot events onto the {"category", "detail"} shape
    synthesize_report() expects. Drops events with no category mapping
    (real data, just not one of the 4 report buckets yet) and de-duplicates
    identical (category, detail) pairs, since several modules often confirm
    the same fact independently.
    """
    seen: set[tuple[str, str]] = set()
    findings: list[dict] = []
    for event in events:
        category = EVENT_CATEGORY_MAP.get(event.get("type", ""))
        if category is None:
            continue
        detail = f"{event['type']}: {event.get('data', '')}".strip()
        if len(detail) > DETAIL_MAX_LENGTH:
            detail = detail[:DETAIL_MAX_LENGTH] + "…"
        key = (category, detail)
        if key in seen:
            continue
        seen.add(key)
        findings.append({"category": category, "detail": detail})
    return findings
