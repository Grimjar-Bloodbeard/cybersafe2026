"""The shape of a synthesized report. Passed to Ollama as a JSON schema via the
`format` parameter, which constrains the model's output to valid JSON matching
this structure - it can't wander off and reply with a paragraph of prose
instead of the fields we actually need to store in the `reports` table.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["mfa", "phishing_exposure", "backups_ransomware", "general_hygiene"]
Severity = Literal["low", "medium", "high"]


class ReportFinding(BaseModel):
    category: Category
    title: str = Field(description="A short, plain-English name for this finding")
    plain_english_explanation: str = Field(
        description="What this means for the business owner, no jargon - why it matters"
    )
    severity: Severity


class SynthesizedReport(BaseModel):
    executive_summary: str = Field(
        description="2-4 sentences, plain English, for a non-technical business owner"
    )
    risk_rating: Literal["Low", "Medium", "High"]
    findings: list[ReportFinding]
    what_we_did_not_test: str = Field(
        description="Explicit statement of scope boundaries - reinforces what this "
        "assessment does NOT cover, per the scope-of-engagement"
    )
