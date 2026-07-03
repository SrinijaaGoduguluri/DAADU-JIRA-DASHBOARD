from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.jira_client import JiraClient, JiraError, resolve_date_range

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="Jira Work Dashboard",
    description="Track your Jira tickets and daily logged hours",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "auto_refresh_seconds": settings.auto_refresh_seconds,
            "jira_base_url": settings.jira_base_url_normalized,
            "credentials_configured": settings.credentials_configured,
        },
    )


@app.get("/api/health")
async def health() -> dict:
    settings = get_settings()
    if not settings.credentials_configured:
        return {
            "status": "missing_credentials",
            "message": "Add JIRA_EMAIL and JIRA_API_TOKEN to your .env file.",
            "jira_base_url": settings.jira_base_url_normalized,
        }

    client = JiraClient(settings)
    try:
        user = await client.verify_connection()
        return {
            "status": "ok",
            "user": user,
            "jira_base_url": settings.jira_base_url_normalized,
        }
    except JiraError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "status": "jira_error",
                "message": str(exc),
            },
        )


@app.get("/api/dashboard")
async def dashboard(
    preset: str = Query("7", description="7, 15, 30, or custom"),
    start: date | None = Query(None, description="Custom range start (YYYY-MM-DD)"),
    end: date | None = Query(None, description="Custom range end (YYYY-MM-DD)"),
) -> dict:
    settings = get_settings()
    if not settings.credentials_configured:
        raise HTTPException(
            status_code=400,
            detail="Missing credentials. Copy .env.example to .env and add your API token.",
        )

    try:
        start_date, end_date = resolve_date_range(preset, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client = JiraClient(settings)
    try:
        return await client.build_dashboard(start_date, end_date)
    except JiraError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/config")
async def public_config() -> dict:
    settings = get_settings()
    return {
        "auto_refresh_seconds": settings.auto_refresh_seconds,
        "jira_base_url": settings.jira_base_url_normalized,
        "credentials_configured": settings.credentials_configured,
        "presets": [
            {"id": "7", "label": "Last 7 days"},
            {"id": "15", "label": "Last 15 days"},
            {"id": "30", "label": "Last 30 days"},
            {"id": "custom", "label": "Custom range"},
        ],
    }
