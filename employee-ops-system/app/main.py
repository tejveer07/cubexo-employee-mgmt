"""
main.py — FastAPI application entrypoint.

Usage (dev):
    python -m app.main --dev      # hot-reload
    python -m app.main            # normal

Usage (packaged):
    ./employee-ops-system.exe     # auto-opens browser
"""

import argparse
import os
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from datetime import date

import uvicorn
from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, DB_PATH, get_db, SessionLocal
from app import models
from app.auth import authenticate, login_user, logout_user, require_login
from app.templates_config import templates
from app.services.employees import sweep_exited_employees

# ---------------------------------------------------------------------------
# Create tables on first run (Alembic migrations are the authoritative path;
# this is a safety net when the packaged exe runs for the very first time)
# ---------------------------------------------------------------------------
models.Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Auto-deactivate employees whose exit_date has passed — once on startup, then
# once per calendar day (guarded below in middleware). See services/employees.py.
# ---------------------------------------------------------------------------
_last_sweep: date | None = None


def _run_exit_sweep(today: date | None = None) -> None:
    db = SessionLocal()
    try:
        sweep_exited_employees(db, today)
    except Exception:
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _last_sweep
    _last_sweep = date.today()
    _run_exit_sweep(_last_sweep)
    yield


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Employee & Operations Management System", docs_url=None, redoc_url=None,
              lifespan=lifespan)


@app.middleware("http")
async def _daily_exit_sweep(request: Request, call_next):
    global _last_sweep
    today = date.today()
    if _last_sweep != today:
        _last_sweep = today  # set first so a failing sweep doesn't retry every request
        _run_exit_sweep(today)
    return await call_next(request)

# Session middleware (uses itsdangerous signed cookies)
SECRET_KEY = os.environ.get("APP_SECRET_KEY", "change-me-in-production-please")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="ops_session")

# Static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---------------------------------------------------------------------------
# Routers (uncommented incrementally as each phase is built)
# ---------------------------------------------------------------------------
from app.routers import employees, teams, projects, reviews, db_transfer, techstack, cost_analysis, analytics, settings
app.include_router(employees.router)
app.include_router(teams.router)
app.include_router(projects.router)
app.include_router(reviews.router)
app.include_router(db_transfer.router)
app.include_router(techstack.router)
app.include_router(cost_analysis.router)
app.include_router(analytics.router)
app.include_router(settings.router)

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        admin = authenticate(username, password, db)
    finally:
        db.close()

    if admin:
        login_user(request, admin.username)
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid username or password."},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------------------------
# Dashboard / home
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: str = Depends(require_login),
    db=Depends(get_db),          # session stays open until AFTER template is rendered
):
    from sqlalchemy.orm import joinedload

    from app.services import cost_analysis, analytics

    total_active   = db.query(models.Employee).filter_by(status=models.EmployeeStatus.active).count()
    total_inactive = db.query(models.Employee).filter_by(status=models.EmployeeStatus.inactive).count()
    active_projects = db.query(models.Project).filter_by(status=models.ProjectStatus.active).count()
    org_snapshot = cost_analysis.org_current_snapshot(db)

    # Eagerly load employee + reviewer so Jinja2 never triggers a lazy load
    # on a closed session.
    recent_reviews = (
        db.query(models.Review)
        .options(
            joinedload(models.Review.employee),
            joinedload(models.Review.reviewer),
        )
        .order_by(models.Review.date.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_active": total_active,
        "total_inactive": total_inactive,
        "active_projects": active_projects,
        "recent_reviews": recent_reviews,
        "org_snapshot": org_snapshot,
        "dash_charts": analytics.dashboard_charts(db),
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 8767


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run with hot-reload")
    args = parser.parse_args()

    if not args.dev:
        threading.Timer(1.0, _open_browser).start()

    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=args.dev,
    )
