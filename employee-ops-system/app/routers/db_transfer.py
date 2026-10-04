"""
routers/db_transfer.py — Import and export the SQLite database.

Export: streams the current app.db as a timestamped download.
Import: uploads a .db file, backs up current DB, runs a schema sanity
        check (verifies expected tables exist), then swaps if OK.
"""

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, inspect

from app import models
from app.database import DB_PATH, engine
from app.auth import require_login
from app.templates_config import templates

router = APIRouter(prefix="/db", tags=["db"])

EXPECTED_TABLES = {
    "admin_users", "employees", "teams", "team_memberships",
    "projects", "employee_project_assignments",
    "tech_stacks", "employee_tech_stacks", "reviews",
    "org_settings", "salary_history", "project_income_history", "gst_rate_history",
}


def _schema_problems(db_file: Path) -> list[str]:
    """Compare an uploaded SQLite file against the current models. Returns human-readable
    problems. A table that is missing entirely is only a problem for the core tables
    (new model tables get created after import); a column the models need but the file
    lacks is always a problem, because queries would fail later."""
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    try:
        inspector = inspect(test_engine)
        found_tables = set(inspector.get_table_names())
        problems = []

        missing_core = EXPECTED_TABLES - found_tables
        if missing_core:
            problems.append(f"Missing tables: {', '.join(sorted(missing_core))}")

        for table in models.Base.metadata.sorted_tables:
            if table.name not in found_tables:
                continue
            file_cols = {c["name"] for c in inspector.get_columns(table.name)}
            missing_cols = {c.name for c in table.columns} - file_cols
            if missing_cols:
                problems.append(f"{table.name} is missing columns: {', '.join(sorted(missing_cols))}")
        return problems
    finally:
        test_engine.dispose()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_db(user: str = Depends(require_login)):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"employee_db_{timestamp}.db"
    return FileResponse(
        path=str(DB_PATH),
        media_type="application/octet-stream",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: str = Depends(require_login)):
    return templates.TemplateResponse("db_import.html", {"request": request, "error": None, "success": None})


@router.post("/import", response_class=HTMLResponse)
async def import_db(
    request: Request,
    file: UploadFile = File(...),
    user: str = Depends(require_login),
):
    if not (file.filename or "").endswith(".db"):
        return templates.TemplateResponse("db_import.html", {
            "request": request,
            "error": "Please upload a .db file.",
            "success": None,
        }, status_code=400)

    # Save uploaded file to a temp location
    temp_path = DB_PATH.parent / f"_import_temp_{datetime.now().strftime('%Y%m%d%H%M%S')}.db"
    try:
        contents = await file.read()
        temp_path.write_bytes(contents)

        problems = _schema_problems(temp_path)
        if problems:
            temp_path.unlink(missing_ok=True)
            return templates.TemplateResponse("db_import.html", {
                "request": request,
                "error": "Schema check failed. " + " ".join(problems),
                "success": None,
            }, status_code=400)

        # Backup current DB
        if DB_PATH.exists():
            backup_path = DB_PATH.parent / f"app_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(DB_PATH, backup_path)

        # Close all SQLAlchemy connections before swap
        engine.dispose()

        # Swap
        shutil.move(str(temp_path), str(DB_PATH))

        # Tables added in newer versions may not exist in an older export yet
        models.Base.metadata.create_all(bind=engine)

        return templates.TemplateResponse("db_import.html", {
            "request": request,
            "error": None,
            "success": "Database imported successfully. A backup of the previous database was saved automatically.",
        })

    except Exception as e:
        temp_path.unlink(missing_ok=True)
        return templates.TemplateResponse("db_import.html", {
            "request": request,
            "error": f"Import failed: {e}",
            "success": None,
        }, status_code=500)
