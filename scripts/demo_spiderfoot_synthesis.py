"""Proves the SpiderFoot enrichment integration end to end, using the real
local Ollama synthesis pipeline: run a real passive scan against a domain
Cody genuinely owns, map its findings into our 4 report categories, and
synthesize a plain-English report - the same pipeline
scripts/demo_tier5_synthesis.py demonstrates with synthetic data, fed by
real (but explicitly owned, low-stakes) findings this time.

Usage: python -m scripts.demo_spiderfoot_synthesis <domain-you-own>
"""
from __future__ import annotations

import sys

from scrapers.enrichment.spiderfoot_scan import run_passive_scan, to_report_findings
from scrapers.tier5_ai.synthesis import render_markdown, synthesize_report


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.demo_spiderfoot_synthesis <domain-you-own>")
        sys.exit(1)
    target = sys.argv[1]

    print(f"Running a real passive SpiderFoot scan against {target} ...")
    print("(this takes a few minutes - it's checking many sources politely, not fast)")
    events = run_passive_scan(target)
    print(f"SpiderFoot reported {len(events)} raw events.")

    findings = to_report_findings(events)
    print(f"{len(findings)} of those map onto our 4 report categories.\n")
    if not findings:
        print("Nothing mapped to a reportable category - nothing to synthesize.")
        return

    business_name = f"{target} (real domain, scanned with the owner's own permission)"
    report = synthesize_report(business_name, findings)

    print(f"Risk rating: {report.risk_rating}")
    print(f"Executive summary: {report.executive_summary}\n")

    markdown = render_markdown(business_name, report)
    output_path = "data/spiderfoot_report.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"Full report written to {output_path}")
    print("\n" + "=" * 60 + "\n")
    print(markdown)


if __name__ == "__main__":
    main()
