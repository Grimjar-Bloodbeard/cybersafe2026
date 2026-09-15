"""Runs SpiderFoot (github.com/smicallef/spiderfoot, MIT licensed) in
passive-only mode against one host, and maps its findings onto the same
{"category", "detail"} shape scrapers/tier5_ai/synthesis.py expects.

This is enrichment, not one of the 5 authored complexity tiers - SpiderFoot
is a real, established OSINT tool someone else wrote (200+ modules, MIT
license, vendored at vendor/spiderfoot/, not committed to this repo - see
vendor/spiderfoot/README.md in this file's own folder for the one-time
setup). Our own authored work here is: curating which of its findings
actually matter for this project's 4 report categories, and writing an
accurate, specific explanation for each one - the same "translate raw
technical output into something a business owner can read" job every other
source in this pipeline does.

Not wired into the authorization gate yet, because the real scan-triggering
admin tool (docs/architecture/PLAN.md Section 7) doesn't exist yet either.
When it does: call backend.app.auth.gate.assert_engagement_authorized()
BEFORE run_passive_scan(), exactly like every other tier - never after,
never skipped. Until then, this only ever runs against domains Cody owns
outright (see scripts/demo_spiderfoot_synthesis.py).

IMPORTANT lesson baked into this file's design (found twice, empirically,
against real domains - see docs/architecture/PLAN.md Section 5): handing the
model a bare "{event type}: {raw data}" string is not enough context for it
to explain a finding accurately. Both times, it filled the gap with a
confident, wrong, invented explanation instead of an accurate one - that's
exactly the "don't exaggerate beyond what the finding supports" failure the
report's own system prompt exists to prevent, and it slipped through because
the *input* was ambiguous, not because the model malfunctioned. The fix
isn't a prompt tweak - it's writing a real, specific, human-authored
explanation for each finding type, the same way SAMPLE_FINDINGS in
scripts/demo_tier5_synthesis.py already does. EXPLANATION_TEMPLATES below is
that authored explanation, one per event type - never let a raw SpiderFoot
string reach the model unexplained.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parents[2] / "vendor" / "spiderfoot"
SF_PYTHON = VENDOR_ROOT / ".venv" / "Scripts" / "python.exe"
SF_ENTRYPOINT = VENDOR_ROOT / "sf.py"

DETAIL_MAX_LENGTH = 600

# SpiderFoot's human-readable event descriptions -> (our category, an
# accurate explanation template with {data} for SpiderFoot's own payload).
# Only event types we're confident we can explain correctly belong here -
# see the two exclusions below for what didn't make the cut and why.
#
# Deliberately NOT mapped, and why:
#
# - "DNS SPF Record" / "Email Gateway (DNS MX Records)": SpiderFoot only
#   emits these when the record EXISTS - having one is normal, not a
#   finding (the real risk is an ABSENT record, which needs its own check,
#   since SpiderFoot has no "missing" event). Tested directly against
#   codynoah.net: mapping mere presence into phishing_exposure produced a
#   fabricated claim ("eforward is known to be used by spammers") with
#   nothing in the finding to support it.
#
# - "Malicious Internet Name" / "Blacklisted Internet Name" (from
#   sfp_comodo specifically): this module's logic is "resolves normally via
#   real DNS, but Comodo's own DNS servers fail to resolve it" - which is
#   just as likely to mean DNS propagation lag for a brand-new domain (the
#   case here: cybersafe.codynoah.net is about a week old) as an actual
#   threat-intel categorization. Tested directly against
#   cybersafe.codynoah.net: the model, given only "Malicious Internet Name:
#   Comodo Secure DNS [host]", invented a backwards explanation ("it's being
#   used maliciously... configured to use a DNS service that could be used
#   for malicious purposes") that doesn't match what the module even checks.
#   A single narrow vendor's DNS-resolution quirk isn't strong enough
#   evidence to report as a finding to a small business owner.
#
# - "Disposable Email Address" and raw "HTTP Headers": not yet triggered by
#   either real test scan, and HTTP_HEADERS in particular is a raw-data-dump
#   event type in SpiderFoot's own taxonomy (could be an entire header
#   block) - not including either until a real occurrence lets us verify
#   what a correct explanation actually looks like, per the two lessons
#   above.
#
# - SPF/DMARC absence still needs its own dedicated check - not something
#   SpiderFoot's core modules give us (see PLAN.md Section 5).
EXPLANATION_TEMPLATES: dict[str, tuple[str, str]] = {
    # MFA / login security - no dedicated passive MFA signal exists; a
    # discovered login form is the closest thing, framed as honestly as the
    # tier_explainer_one_pager.md's own phrasing: we can tell a login exists,
    # not whether it's protected.
    "URL (Accepts Passwords)": (
        "mfa",
        "A login page was found at {data}. From outside, there's no way to tell whether "
        "it requires anything beyond a password to sign in (like a text-message code) - "
        "that's worth asking about directly, since a stolen password alone shouldn't be "
        "enough to get in.",
    ),
    # Phishing exposure
    "Hacked Email Address": (
        "phishing_exposure",
        "The email address {data}, tied to this domain, has previously appeared in a "
        "known data breach. If that same password was ever reused anywhere else, an "
        "attacker may already have a working way in.",
    ),
    "Malicious E-mail Address": (
        "phishing_exposure",
        "An email address tied to this domain ({data}) has been flagged elsewhere as "
        "connected to malicious activity. Worth checking whether that address is still "
        "in active use and by whom.",
    ),
    # Backups / ransomware exposure - known entry points and existing trouble
    "Vulnerability - CVE Critical": (
        "backups_ransomware",
        "A specific, publicly documented security flaw was found in software this site "
        "runs: {data}. This isn't a guess - it's a known, catalogued weakness, and "
        "critical-rated ones are exactly the kind ransomware attacks use to get in.",
    ),
    "Vulnerability - CVE High": (
        "backups_ransomware",
        "A specific, publicly documented security flaw was found in software this site "
        "runs: {data}. This is a known, catalogued weakness, not a guess.",
    ),
    "Vulnerability - CVE Medium": (
        "backups_ransomware",
        "A specific, publicly documented security flaw was found in software this site "
        "runs: {data}. Lower severity than critical, but still worth patching.",
    ),
    "Vulnerability - CVE Low": (
        "backups_ransomware",
        "A specific, publicly documented security flaw was found in software this site "
        "runs: {data}. Low severity, but still worth knowing about.",
    ),
    "Vulnerability - General": (
        "backups_ransomware",
        "A general security weakness was identified: {data}.",
    ),
    "Vulnerability - Third Party Disclosure": (
        "backups_ransomware",
        "A security researcher or third party has already published a report describing "
        "a vulnerability tied to this site: {data}. If it's public, an attacker can find "
        "it just as easily as we did.",
    ),
    "Interesting File": (
        "backups_ransomware",
        "A file was found publicly reachable that usually shouldn't be: {data}. "
        "Depending on what it actually contains, this can hand an attacker a shortcut "
        "past normal defenses - worth confirming it's meant to be public.",
    ),
    "Historic Interesting File": (
        "backups_ransomware",
        "A file that usually shouldn't be publicly reachable was found here in the past: "
        "{data}. Worth confirming it's no longer exposed today.",
    ),
    "Defaced": (
        "backups_ransomware",
        "A record exists suggesting this site has been defaced (visibly altered by an "
        "attacker) at some point: {data}. Worth confirming this isn't still true today.",
    ),
    "Open TCP Port": (
        "backups_ransomware",
        "A network port is open and reachable from the internet: {data}. Not automatically "
        "a problem, but every open port is one more thing that has to be kept patched and "
        "watched.",
    ),
    "Software Used": (
        "backups_ransomware",
        "This site is running: {data}. If a security flaw is ever reported for this "
        "specific version, it becomes an easy, publicly-known target until it's updated - "
        "keeping software current is the main defense here.",
    ),
    # General hygiene - baseline web/TLS care
    "SSL Certificate Expired": (
        "general_hygiene",
        "This site's SSL/TLS certificate (what puts the padlock icon in a browser) has "
        "expired: {data}. Visitors will see a scary security warning until it's renewed.",
    ),
    "SSL Certificate Expiring": (
        "general_hygiene",
        "This site's SSL/TLS certificate is close to expiring: {data}. Best to renew it "
        "before it lapses and visitors start seeing warnings.",
    ),
    "SSL Certificate Host Mismatch": (
        "general_hygiene",
        "This site's SSL/TLS certificate doesn't match the address it's serving: {data}. "
        "That mismatch can trigger browser security warnings for visitors even though "
        "nothing was actually compromised.",
    ),
    "Non-Standard HTTP Header": (
        "general_hygiene",
        "This site sends an unusual, non-standard web server header: {data}. Not "
        "dangerous by itself, but it can reveal more about the server's setup than "
        "necessary.",
    ),
    "Web Technology": (
        "general_hygiene",
        "This site is built using: {data}. Knowing this helps track whether that "
        "specific software has any newly reported security issues going forward.",
    ),
    "Web Server": (
        "general_hygiene",
        "This site's web server software is: {data}.",
    ),
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
    synthesize_report() expects, using EXPLANATION_TEMPLATES so the model
    always gets a real, specific, human-authored sentence - never a bare
    "{type}: {data}" string (see this module's docstring for why that
    matters). Drops events with no template (real data, just not
    confidently explainable yet) and de-duplicates identical findings,
    since several modules often confirm the same fact independently.
    """
    seen: set[tuple[str, str]] = set()
    findings: list[dict] = []
    for event in events:
        template = EXPLANATION_TEMPLATES.get(event.get("type", ""))
        if template is None:
            continue
        category, explanation = template
        detail = explanation.format(data=event.get("data", "")).strip()
        if len(detail) > DETAIL_MAX_LENGTH:
            detail = detail[:DETAIL_MAX_LENGTH] + "…"
        key = (category, detail)
        if key in seen:
            continue
        seen.add(key)
        findings.append({"category": category, "detail": detail})
    return findings
