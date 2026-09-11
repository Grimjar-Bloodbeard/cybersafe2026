"""Proves the Tier 5 pipeline end to end: raw findings in, formatted report out.

Uses SYNTHETIC sample findings, not a real business - nothing has been scanned,
and nothing will be until a real engagement is authorized. This is exactly the
kind of synthetic example the public showcase site (demo_showcase_runs table)
is meant to use, per docs/architecture/PLAN.md Section 4.
"""
from __future__ import annotations

from scrapers.tier5_ai.synthesis import render_markdown, synthesize_report

SAMPLE_BUSINESS = "Sample Local Business (synthetic demo data - not a real company)"

SAMPLE_FINDINGS = [
    {
        "category": "general_hygiene",
        "detail": "The website does not redirect HTTP to HTTPS - visitors can load an unencrypted version of the site.",
    },
    {
        "category": "general_hygiene",
        "detail": "No Content-Security-Policy header is set, which normally helps block certain kinds of malicious script injection.",
    },
    {
        "category": "phishing_exposure",
        "detail": "The domain has no SPF or DMARC DNS records, meaning attackers can send emails that appear to come from this business's own domain.",
    },
    {
        "category": "backups_ransomware",
        "detail": "The site's generator meta tag shows WordPress 5.2, a version with publicly known critical vulnerabilities in later CVE databases.",
    },
    {
        "category": "mfa",
        "detail": "The login page at /wp-admin/ shows no visible multi-factor authentication prompt.",
    },
]


def main() -> None:
    print(f"Synthesizing report for: {SAMPLE_BUSINESS}\n")
    report = synthesize_report(SAMPLE_BUSINESS, SAMPLE_FINDINGS)

    print(f"Risk rating: {report.risk_rating}")
    print(f"Executive summary: {report.executive_summary}\n")
    print(f"{len(report.findings)} findings synthesized across categories.\n")

    markdown = render_markdown(SAMPLE_BUSINESS, report)
    output_path = "data/sample_report.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"Full report written to {output_path}")
    print("\n" + "=" * 60 + "\n")
    print(markdown)


if __name__ == "__main__":
    main()
