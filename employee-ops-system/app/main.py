"""
main.py — FastAPI application entrypoint.

Usage (dev):
    python -m app.main --dev      # hot-reload
    python -m app.main            # normal

Usage (packaged):
    ./employee-ops-system.exe     # auto-opens browser
"""

import argparse
import logging
import os
import socket
import sys
import threading
import time
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
from app.auth import authenticate, hash_password, login_user, logout_user, require_login, LoginRequired
from app.templates_config import templates, BASE_DIR
from app.services.employees import sweep_exited_employees
from app.services.bootstrap import ensure_defaults

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


def _run_first_run_defaults() -> None:
    # Creates the admin account and starter tech stacks on an empty DB (no-op otherwise).
    db = SessionLocal()
    try:
        ensure_defaults(db)
    except Exception:
        db.rollback()
        logging.getLogger("ops.startup").exception("first-run defaults failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _last_sweep
    _run_first_run_defaults()
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

@app.exception_handler(LoginRequired)
async def _redirect_to_login(request: Request, exc: LoginRequired):
    return RedirectResponse("/login", status_code=302)


# Session middleware (uses itsdangerous signed cookies)
SECRET_KEY = os.environ.get("APP_SECRET_KEY", "change-me-in-production-please")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="ops_session")

# Static files. BASE_DIR comes from templates_config (inside the app package) because
# __file__ here is wrong when this module runs as the PyInstaller entry script.
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
    success = "Password updated. Please sign in." if request.query_params.get("reset") else None
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None, "success": success}
    )


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request, "error": None})


@app.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    username: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    # NOTE: intentionally unauthenticated (local single-admin app). See CLAUDE.md > Auth.
    from app import models
    from app.database import SessionLocal

    error = None
    if new_password != confirm_password:
        error = "Passwords do not match."
    elif len(new_password) < 6:
        error = "Password must be at least 6 characters."
    else:
        db = SessionLocal()
        try:
            admin = db.query(models.AdminUser).filter_by(username=username.strip()).first()
            if admin:
                admin.password_hash = hash_password(new_password)
                db.commit()
            else:
                error = "Unknown username."
        finally:
            db.close()

    if error:
        return templates.TemplateResponse(
            "forgot_password.html", {"request": request, "error": error}, status_code=400
        )
    return RedirectResponse("/login?reset=1", status_code=302)


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
PORT_TRIES = 10  # if 8767 is taken (e.g. a second copy is open), use the next free port


def _pick_port(start: int) -> int:
    for port in range(start, start + PORT_TRIES):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in {start}-{start + PORT_TRIES - 1}. Close other copies and try again.")


def _open_browser_when_ready(port: int, timeout: float = 20.0) -> None:
    """Open the browser only after the server accepts connections, so the first page
    load never hits 'connection refused' on a slow PC."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                webbrowser.open(f"http://{HOST}:{port}")
                return
        except OSError:
            time.sleep(0.2)
    logging.getLogger("ops.startup").error("Server did not start on port %s within %ss", port, timeout)


def _setup_windowed_logging() -> None:
    """A windowed (console=False) PyInstaller exe has sys.stdout/sys.stderr set to None,
    and uvicorn's default logging crashes on that. Send output to ops-system.log next
    to the database instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_file = open(DB_PATH.parent / "ops-system.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log_file
    logging.basicConfig(stream=log_file, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


if __name__ == "__main__":
    _setup_windowed_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run with hot-reload")
    args = parser.parse_args()

    if args.dev:
        uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
    else:
        port = _pick_port(PORT)
        threading.Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()
        # When frozen by PyInstaller, "app.main:app" can't be re-imported by name (this
        # file runs as __main__), so hand uvicorn the app object directly.
        target = app if getattr(sys, "frozen", False) else "app.main:app"
        uvicorn.run(target, host=HOST, port=port, reload=False)
