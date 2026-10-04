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
from sqlalchemy import inspect, text

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
    if not file.filename.endswith(".db"):
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

        # Schema sanity check — open the uploaded DB and verify tables
        from sqlalchemy import create_engine as _ce
        test_engine = _ce(f"sqlite:///{temp_path}", connect_args={"check_same_thread": False})
        try:
            inspector = inspect(test_engine)
            found_tables = set(inspector.get_table_names())
            missing = EXPECTED_TABLES - found_tables
        finally:
            test_engine.dispose()

        if missing:
            temp_path.unlink(missing_ok=True)
            return templates.TemplateResponse("db_import.html", {
                "request": request,
                "error": f"Schema check failed. Missing tables: {', '.join(sorted(missing))}",
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
