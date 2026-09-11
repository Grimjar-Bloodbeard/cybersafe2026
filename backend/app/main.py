"""The actual front end - shows the AI-translated report. Deliberately plain:
server-rendered HTML shell (Jinja2) + a JSON API the page's own JS calls to
reveal the report live. No JavaScript framework, no build step. This is a
working page, not a mockup - `uvicorn backend.app.main:app --reload` runs it
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

from scrapers.tier5_ai.synthesis import CATEGORY_LABELS, synthesize_report
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
_page = _env.get_template("report.html").render()


@app.get("/", response_class=HTMLResponse)
def show_report():
    # The page is fully static HTML - it fetches and reveals the report itself
    # via /api/run-demo, so there's nothing server-side left to fill in here.
    return _page


@app.post("/api/run-demo")
def run_demo_json():
    """Returns the report as JSON so the front end can reveal it progressively
    (typewriter/staggered animation, optional voice) instead of a blocking
    full-page reload - see report.html's <script> for the reveal logic.

    Never lets a synthesis failure hang the browser: if both models fail
    (synthesize_report's fail-closed RuntimeError), that's reported as a real
    JSON error the frontend can actually show, not a bare 500 the page's
    `resp.json()` would choke on and abandon the loading state forever.
    """
    try:
        report = synthesize_report(SAMPLE_BUSINESS, SAMPLE_FINDINGS)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

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
