"""The actual front end - shows the AI-translated report and the real event
registration form. Deliberately plain: server-rendered HTML shells (Jinja2) +
a JSON API the pages' own JS calls. No JavaScript framework, no build step.

Deployed publicly at cybersafe.codynoah.net (see docs/architecture/DEPLOYMENT.md
for the full runbook and why) - safe to be public because nothing here can
trigger a real scan against a real business; Tiers 2-5 and the actual
scan-triggering admin tool don't exist yet. THAT tool, when built, is what
needs to stay Tailscale-gated per docs/architecture/PLAN.md Section 7 - not
this one. The two public POST endpoints (run-demo, register) are rate-limited
(backend/app/rate_limit.py) since they're reachable by anyone with the link.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.app.db.models import EventRegistration
from backend.app.db.session import get_session
from backend.app.rate_limit import PerIPRateLimiter, client_ip
from scrapers.tier5_ai.synthesis import CATEGORY_LABELS, synthesize_report
from scripts.demo_tier5_synthesis import SAMPLE_BUSINESS, SAMPLE_FINDINGS

app = FastAPI(title="CyberSafe 2026")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# Tunable while the team is actively testing - loosen these temporarily if
# needed, but tighten back before the public event. See rate_limit.py for why
# these are per-process (--workers 1 in ecosystem.config.js is load-bearing).
DEMO_RATE_LIMIT = PerIPRateLimiter(max_requests=1, per_seconds=60)
REGISTER_RATE_LIMIT = PerIPRateLimiter(max_requests=5, per_seconds=600)
_demo_slot = threading.Semaphore(1)  # at most one Ollama synthesis in flight, globally -
# protects against the *legitimate* case of many people scanning the same QR
# code at once, which per-IP limiting alone wouldn't catch.

# Rendering Jinja2 directly, not through Starlette's Jinja2Templates wrapper -
# that wrapper hit a real version-compatibility bug (a cache-key TypeError)
# with this FastAPI/Starlette/Jinja2 combination. This is simpler anyway:
# fewer moving parts, and it's plain to see exactly what's happening.
_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)
_page = _env.get_template("report.html").render()
_register_page = _env.get_template("register.html").render()


@app.get("/", response_class=HTMLResponse)
def show_report():
    # The page is fully static HTML - it fetches and reveals the report itself
    # via /api/run-demo, so there's nothing server-side left to fill in here.
    return _page


@app.get("/register", response_class=HTMLResponse)
def show_register():
    return _register_page


class RegistrationRequest(BaseModel):
    group_size: int = Field(gt=0, le=50)
    attendee_names: list[str] = Field(min_length=1)
    organization: str = Field(min_length=1, max_length=200)
    email: EmailStr
    hp_website: str = Field(default="", max_length=200)  # honeypot - real users never fill this


@app.post("/api/register")
def submit_registration(
    registration: RegistrationRequest,
    request: Request,
    db: Session = Depends(get_session),
):
    REGISTER_RATE_LIMIT.check(client_ip(request))

    if registration.hp_website:
        # A bot filled in the hidden field - fake success so it doesn't learn
        # to look for a different tell. Never write a row.
        return JSONResponse({"status": "registered"})

    db.add(
        EventRegistration(
            group_size=registration.group_size,
            attendee_names=json.dumps(registration.attendee_names),
            organization=registration.organization,
            email=registration.email,
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    db.commit()
    return JSONResponse({"status": "registered"})


@app.post("/api/run-demo")
def run_demo_json(request: Request):
    """Returns the report as JSON so the front end can reveal it progressively
    (typewriter/staggered animation, optional voice) instead of a blocking
    full-page reload - see report.html's <script> for the reveal logic.

    Never lets a synthesis failure hang the browser: if both models fail
    (synthesize_report's fail-closed RuntimeError), that's reported as a real
    JSON error the frontend can actually show, not a bare 500 the page's
    `resp.json()` would choke on and abandon the loading state forever.

    Two layers of protection since this calls a slow, CPU-bound local LLM:
    a per-IP throttle (stops one abusive client), and a global concurrency
    slot (stops a legitimate crowd - everyone scanning the same QR code at
    once - from piling onto Ollama simultaneously).
    """
    DEMO_RATE_LIMIT.check(client_ip(request))

    if not _demo_slot.acquire(blocking=False):
        return JSONResponse(
            {"error": "The live demo is busy right now - try again in a minute."},
            status_code=503,
        )
    try:
        report = synthesize_report(SAMPLE_BUSINESS, SAMPLE_FINDINGS)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    finally:
        _demo_slot.release()

    return JSONResponse(
        {
            "business_name": SAMPLE_BUSINESS,
            "risk_rating": report.risk_rating,
            "executive_summary": report.executive_summary,
            "findings": [f.model_dump() for f in report.findings],
            "what_we_did_not_test": report.what_we_did_not_test,
            "category_labels": CATEGORY_LABELS,
        }
    )
