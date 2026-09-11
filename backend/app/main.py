"""The actual front end - shows the AI-translated report. Deliberately plain:
server-rendered HTML (Jinja2), no JavaScript framework, no build step. This is
a working page, not a mockup - `uvicorn backend.app.main:app --reload` runs it
for real, right now, on your own machine.

Later (per docs/architecture/PLAN.md Section 7) this gets hosted on Cody's own
infrastructure behind Tailscale so the whole team can reach it from anywhere -
that's a separate, deliberate deployment step, not done here.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from scrapers.tier5_ai.synthesis import synthesize_report
from scripts.demo_tier5_synthesis import SAMPLE_BUSINESS, SAMPLE_FINDINGS

app = FastAPI(title="CyberSafe 2026")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# Rendering Jinja2 directly, not through Starlette's Jinja2Templates wrapper -
# that wrapper hit a real version-compatibility bug (a cache-key TypeError)
# with this FastAPI/Starlette/Jinja2 combination. This is simpler anyway:
# fewer moving parts, and it's plain to see exactly what's happening.
_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)

_last_report = None  # in-memory only - a real "last run" store comes with the DB wiring


def _render(report) -> str:
    template = _env.get_template("report.html")
    return template.render(business_name=SAMPLE_BUSINESS, report=report)


@app.get("/", response_class=HTMLResponse)
def show_report():
    return _render(_last_report)


@app.post("/api/run-demo")
def run_demo_json():
    """Returns the report as JSON so the front end can reveal it progressively
    (typewriter/staggered animation, optional voice) instead of a blocking
    full-page reload - see report.html's <script> for the reveal logic.
    """
    global _last_report
    _last_report = synthesize_report(SAMPLE_BUSINESS, SAMPLE_FINDINGS)
    return JSONResponse(
        {
            "business_name": SAMPLE_BUSINESS,
            "risk_rating": _last_report.risk_rating,
            "executive_summary": _last_report.executive_summary,
            "findings": [f.model_dump() for f in _last_report.findings],
            "what_we_did_not_test": _last_report.what_we_did_not_test,
        }
    )
