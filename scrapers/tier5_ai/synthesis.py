"""Tier 5: turns raw findings into the plain-English report a student hands a
business owner. This is the "translate it" step - everything upstream (Tiers
1-4, enrichment APIs) produces technical findings; this is what makes them
readable by someone who's never heard the word "CVE."

Model routing (see docs/architecture/PLAN.md Section 6): llama3.1:8b is the
default, already proven reliable for structured output on this hardware. If it
fails to produce valid output matching our schema, we escalate once to
qwen2.5-coder:14b before giving up - never fabricate a report, never guess.
"""
from __future__ import annotations

import logging

import ollama
from pydantic import ValidationError

from scrapers.tier5_ai.schemas import SynthesizedReport

DEFAULT_MODEL = "llama3.1:8b"
ESCALATION_MODEL = "qwen2.5-coder:14b"

log = logging.getLogger("tier5_synthesis")

SYSTEM_PROMPT = """You are writing a security assessment report for a small business \
owner who has no technical background. Translate the raw findings you're given into \
plain English - explain what each finding means and why it matters to their business, \
never using jargon without explaining it first. Organize findings into these four \
categories only: mfa, phishing_exposure, backups_ransomware, general_hygiene. Be \
accurate and proportionate - do not exaggerate severity to sound more alarming than \
the finding actually supports. You must respond with valid JSON matching the \
provided schema, nothing else."""


def _build_user_prompt(business_name: str, raw_findings: list[dict]) -> str:
    findings_text = "\n".join(f"- [{f['category']}] {f['detail']}" for f in raw_findings)
    return (
        f"Business: {business_name}\n\n"
        f"Raw findings from an automated, passive scan of this business's public "
        f"website (nothing was exploited or logged into - see the scope-of-engagement "
        f"for what this assessment covers):\n{findings_text}\n\n"
        f"Write the report now."
    )


def synthesize_report(business_name: str, raw_findings: list[dict]) -> SynthesizedReport:
    """Raises RuntimeError if both models fail - this is the fail-closed
    behavior: a bad report should never reach a business, so we'd rather crash
    loudly here than silently hand over something wrong or empty.
    """
    user_prompt = _build_user_prompt(business_name, raw_findings)
    schema = SynthesizedReport.model_json_schema()

    for attempt, model in enumerate((DEFAULT_MODEL, ESCALATION_MODEL), start=1):
        log.info("Synthesis attempt %d using %s", attempt, model)
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            format=schema,
            options={"temperature": 0.2},
        )
        raw_content = response["message"]["content"]
        try:
            return SynthesizedReport.model_validate_json(raw_content)
        except ValidationError as exc:
            log.warning("%s produced invalid output, escalating: %s", model, exc)

    raise RuntimeError(
        f"Both {DEFAULT_MODEL} and {ESCALATION_MODEL} failed to produce a valid "
        f"report for {business_name!r} - needs manual review, not a guess."
    )


def render_markdown(business_name: str, report: SynthesizedReport) -> str:
    """Turns the structured report into the actual document a student downloads
    and hands over - see docs/architecture/PLAN.md Section 7's "Download Report".
    """
    lines = [
        f"# Security Assessment Summary - {business_name}",
        "",
        f"**Overall risk rating: {report.risk_rating}**",
        "",
        report.executive_summary,
        "",
        "## What we found",
    ]
    category_labels = {
        "mfa": "Login security (MFA)",
        "phishing_exposure": "Phishing / email spoofing exposure",
        "backups_ransomware": "Backup & ransomware entry points",
        "general_hygiene": "General website hygiene",
    }
    for category, label in category_labels.items():
        matching = [f for f in report.findings if f.category == category]
        if not matching:
            continue
        lines.append(f"\n### {label}")
        for finding in matching:
            lines.append(f"- **{finding.title}** ({finding.severity}): {finding.plain_english_explanation}")

    lines += ["", "## What we did NOT test", report.what_we_did_not_test]
    return "\n".join(lines)
