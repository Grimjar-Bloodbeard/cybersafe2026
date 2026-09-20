"""Full SQLAlchemy schema (see docs/architecture/PLAN.md, Section 4).

businesses/engagements extend the columns already populated by
scrapers/common/storage.py's Week 1 scraper output - Alembic's migration adds
the missing columns and new tables in place, it does not recreate these two.
"""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EngagementStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_SIGNATURE = "pending_signature"
    AUTHORIZED = "authorized"
    REVOKED = "revoked"
    EXPIRED = "expired"
    COMPLETED = "completed"


class ExtractionMethod(str, enum.Enum):
    CSS_SELECTOR = "css_selector"
    TIER5_LLAMA31 = "tier5_llama3.1"
    TIER5_QWEN25_CODER = "tier5_qwen2.5-coder"
    MANUAL_REVIEW_NEEDED = "manual_review_needed"


class CveMatchStatus(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED_RELEVANT = "confirmed_relevant"
    FALSE_POSITIVE = "false_positive"


class ScanRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String)
    contact_email: Mapped[str | None] = mapped_column(String)
    website_root_url: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, nullable=False)
    sourced_at: Mapped[str] = mapped_column(String, nullable=False)
    directory_category: Mapped[str | None] = mapped_column(String)
    directory_member_id: Mapped[str | None] = mapped_column(String, unique=True)
    phone: Mapped[str | None] = mapped_column(String)
    street_address: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)
    postal_code: Mapped[str | None] = mapped_column(String)
    profile_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    # Meeting action item, 2026-09-15: enforcing "no organization further than
    # a 30-minute drive from the event" needs real coordinates, not just a
    # city-name filter - see scripts/export_outreach_list.py's distance
    # calculation. Nullable: Chamber-of-Commerce-sourced rows don't have these
    # until geocoded (scrapers/common/geocode.py backfills them); OSM-sourced
    # rows (community scraper) get them directly at scrape time, for free.
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    engagements: Mapped[list["Engagement"]] = relationship(back_populates="business")


class Engagement(Base):
    """The literal legal/code gate. status must be 'authorized' - and every other
    check in assert_engagement_authorized() must pass - before any scraper runs
    against this business. See backend/app/auth/gate.py.
    """

    __tablename__ = "engagements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    scope_document_text: Mapped[str | None] = mapped_column(Text)
    in_scope_hosts: Mapped[str | None] = mapped_column(Text)  # JSON-encoded list of hostnames
    out_of_scope_notes: Mapped[str | None] = mapped_column(Text)
    authorized_by_signature_name: Mapped[str | None] = mapped_column(String)
    authorized_at: Mapped[str | None] = mapped_column(String)
    authorization_expires_at: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default=EngagementStatus.DRAFT.value)
    max_tier_allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rate_limit_override: Mapped[float | None] = mapped_column(Float)
    outreach_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    # Team dashboard, 2026-09-18: Jovan's 3-step outreach sequence from the
    # 2026-09-15 meeting, tracked per engagement so the whole team sees the
    # same state instead of everyone keeping their own copy of a spreadsheet.
    # Deliberately NOT extended to let the dashboard set status='authorized' -
    # that stays a real signed-paperwork event, never a dashboard click (see
    # backend/app/auth/gate.py's fail-closed design this would otherwise
    # undercut). The dashboard can only move status between draft and
    # pending_signature (not-yet-contacted vs. in-conversation); anything
    # more nuanced ("declined", "call back next week") goes in outreach_notes
    # rather than inventing new gate-relevant statuses.
    outreach_step1_sent_at: Mapped[str | None] = mapped_column(String)
    outreach_step2_sent_at: Mapped[str | None] = mapped_column(String)
    outreach_step3_sent_at: Mapped[str | None] = mapped_column(String)
    outreach_owner: Mapped[str | None] = mapped_column(String)  # which team member has this lead

    business: Mapped["Business"] = relationship(back_populates="engagements")
    scan_runs: Mapped[list["ScanRun"]] = relationship(back_populates="engagement")


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), nullable=False)
    tier_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    target_url: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String)
    completed_at: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default=ScanRunStatus.QUEUED.value)
    triggered_by: Mapped[str | None] = mapped_column(String)
    aborted_reason: Mapped[str | None] = mapped_column(Text)

    engagement: Mapped["Engagement"] = relationship(back_populates="scan_runs")
    raw_findings: Mapped[list["RawFinding"]] = relationship(back_populates="scan_run")


class RawFinding(Base):
    __tablename__ = "raw_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    page_url: Mapped[str] = mapped_column(String, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str | None] = mapped_column(String)
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    raw_html_ref: Mapped[str | None] = mapped_column(String)
    extracted_json: Mapped[str | None] = mapped_column(Text)

    scan_run: Mapped["ScanRun"] = relationship(back_populates="raw_findings")


class TechFingerprint(Base):
    __tablename__ = "tech_fingerprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    product_version: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    detection_method: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float)


class HttpHeaderFinding(Base):
    __tablename__ = "http_headers_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    header_name: Mapped[str] = mapped_column(String, nullable=False)
    header_value: Mapped[str | None] = mapped_column(Text)
    is_security_header: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class TlsFinding(Base):
    __tablename__ = "tls_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    ssl_labs_grade: Mapped[str | None] = mapped_column(String)
    protocol_versions_supported: Mapped[str | None] = mapped_column(Text)  # JSON list
    cert_issuer: Mapped[str | None] = mapped_column(String)
    cert_expires_at: Mapped[str | None] = mapped_column(String)
    cert_transparency_subdomains: Mapped[str | None] = mapped_column(Text)  # JSON list
    notes: Mapped[str | None] = mapped_column(Text)


class CveMatch(Base):
    __tablename__ = "cve_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    tech_fingerprint_id: Mapped[int | None] = mapped_column(ForeignKey("tech_fingerprints.id"))
    cve_id: Mapped[str] = mapped_column(String, nullable=False)
    cvss_score: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String)
    nvd_url: Mapped[str | None] = mapped_column(String)
    match_confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, nullable=False, default=CveMatchStatus.UNREVIEWED.value)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    related_finding_type: Mapped[str | None] = mapped_column(String)
    related_finding_id: Mapped[int | None] = mapped_column(Integer)
    anomaly_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[str] = mapped_column(String, nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), nullable=False)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    generated_at: Mapped[str | None] = mapped_column(String)
    executive_summary_text: Mapped[str | None] = mapped_column(Text)
    full_report_markdown: Mapped[str | None] = mapped_column(Text)
    risk_rating: Mapped[str | None] = mapped_column(String)
    delivered_at: Mapped[str | None] = mapped_column(String)
    access_token: Mapped[str | None] = mapped_column(String, unique=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by_human: Mapped[bool] = mapped_column(Boolean, default=False)


class DemoShowcaseRun(Base):
    """The ONLY table frontend_public is ever allowed to read from."""

    __tablename__ = "demo_showcase_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anonymized_business_label: Mapped[str] = mapped_column(String, nullable=False)
    tier_demonstrated: Mapped[int] = mapped_column(Integer, nullable=False)
    synthetic_or_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)


class EventRegistration(Base):
    """Community event RSVPs (the Dec 4, 2026 event) - a separate concern from
    the assessment pipeline above, kept in its own table rather than entangled
    with businesses/engagements.
    """

    __tablename__ = "event_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_size: Mapped[int] = mapped_column(Integer, nullable=False)
    attendee_names: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list
    organization: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    submitted_at: Mapped[str] = mapped_column(String, nullable=False)
    # Meeting action item, 2026-09-15: an opt-in for a live assessment of the
    # business's own website during the presentation itself - separate from
    # the future real scan-admin tool (PLAN.md Section 7); this is just intent
    # captured at RSVP time, reviewed by a human before anything is scheduled.
    wants_live_assessment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TeamUser(Base):
    """One of the 4 team members allowed to log into the team outreach
    dashboard - entirely separate from Summit Gaming's own `users` table
    (different project, different database, on purpose). Passkey-only, same
    pattern as Summit's real, working webauthn.js/webauthn-routes.js -
    reimplemented in Python here since this project is FastAPI, not Express,
    not literally shared infrastructure. See backend/app/auth/passkeys.py.

    email is deliberately NOT unique, found live 2026-09-19: the team
    genuinely shares one inbox rather than each having their own working
    address, so identity here is really (email, display_name) together -
    a passkey doesn't actually need a unique email to be a distinct,
    per-device credential, only a unique account to attach to. See
    backend/app/team.py's enroll_request for the lookup that depends on this.
    """

    __tablename__ = "team_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    # Holds the challenge between "start registration" and "finish
    # registration" for one in-progress passkey enrollment - same shape as
    # Summit's users.webauthn_challenge column.
    webauthn_challenge: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    credentials: Mapped[list["TeamWebauthnCredential"]] = relationship(back_populates="user")


class TeamWebauthnCredential(Base):
    """One passkey (one device) belonging to one team member. A user can have
    more than one (phone + laptop), same as Summit's webauthn_credentials.
    """

    __tablename__ = "team_webauthn_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("team_users.id"), nullable=False)
    credential_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # base64url
    public_key: Mapped[str] = mapped_column(String, nullable=False)  # base64
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transports: Mapped[str | None] = mapped_column(String)  # JSON-encoded list
    device_label: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    last_used_at: Mapped[str | None] = mapped_column(String)

    user: Mapped["TeamUser"] = relationship(back_populates="credentials")


class TeamPasskeyEnrollToken(Base):
    """A short-lived, single-use, emailed link that lets someone register
    their very first passkey with no prior login to bootstrap from - same
    mechanism as Summit's passkey_enroll_tokens (and its own
    password_reset_tokens before that). Only the SHA-256 hash is stored,
    never the raw token - same reasoning as backend/app/rate_limit.py trusting
    only nginx-set headers: the raw token only ever exists in the email and
    the requester's browser.
    """

    __tablename__ = "team_passkey_enroll_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("team_users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)
    used_at: Mapped[str | None] = mapped_column(String)


class TeamSession(Base):
    """A logged-in team member's session. Only the SHA-256 hash of the
    session token is stored (same reasoning as the enroll token above) - the
    raw token lives only in the browser's cookie.
    """

    __tablename__ = "team_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("team_users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)
