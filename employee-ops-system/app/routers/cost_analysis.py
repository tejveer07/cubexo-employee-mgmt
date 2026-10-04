"""
routers/cost_analysis.py — Org-wide and per-project cost/profit analysis, overhead setting.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import require_login
from app.templates_config import templates
from app.services import cost_analysis, analytics

router = APIRouter(prefix="/cost-analysis", tags=["cost_analysis"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def cost_analysis_page(
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    org_snapshot = cost_analysis.org_current_snapshot(db)
    org_lifetime = cost_analysis.org_lifetime(db)

    projects = db.query(models.Project).order_by(models.Project.name).all()
    rows = []
    unset_project_count = 0
    for p in projects:
        snap = cost_analysis.project_current_snapshot(db, p)
        life = cost_analysis.project_lifetime(db, p)
        if not p.income_history:
            unset_project_count += 1
        rows.append({"project": p, "snapshot": snap, "lifetime": life})

    active_employees = db.query(models.Employee).filter_by(status=models.EmployeeStatus.active).all()
    unset_employee_count = sum(1 for e in active_employees if not e.salary_history)

    return templates.TemplateResponse("cost_analysis.html", {
        "request": request,
        "org_snapshot": org_snapshot,
        "org_lifetime": org_lifetime,
        "rows": rows,
        "unset_employee_count": unset_employee_count,
        "unset_project_count": unset_project_count,
        "current_gst_rate": cost_analysis.get_current_gst_rate(db),
        "cost_charts": analytics.cost_charts_from_rows(db, rows),
    })


@router.post("/overhead")
async def update_overhead(
    monthly_overhead: Decimal = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    cost_analysis.set_overhead(db, monthly_overhead)
    return RedirectResponse("/cost-analysis", status_code=302)


@router.post("/gst-rate")
async def update_gst_rate(
    gst_rate: Decimal = Form(...),
    effective_from: date = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    cost_analysis.record_gst_rate_change(db, gst_rate, effective_from)
    return RedirectResponse("/cost-analysis", status_code=302)
