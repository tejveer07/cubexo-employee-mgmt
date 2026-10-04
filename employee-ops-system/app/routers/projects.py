"""
routers/projects.py — Project CRUD: list, create, edit, status change, view assignments.
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

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def project_list(
    request: Request,
    status: str = "active",
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    query = db.query(models.Project)
    if status in ("active", "completed", "on_hold"):
        query = query.filter(models.Project.status == status)
    projects = query.order_by(models.Project.name).all()
    return templates.TemplateResponse("project_list.html", {
        "request": request, "projects": projects, "current_status": status,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_project_form(
    request: Request,
    user: str = Depends(require_login),
):
    return templates.TemplateResponse("project_form.html", {
        "request": request, "project": None, "error": None,
    })


@router.post("/new")
async def create_project(
    request: Request,
    name: str = Form(...),
    client: str = Form(...),
    status: str = Form("active"),
    start_date: date = Form(...),
    end_date: date | None = Form(None),
    monthly_income: Decimal | None = Form(None),
    tds_rate: Decimal | None = Form(None),
    gst_applicable: str | None = Form(None),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    project = models.Project(
        name=name, client=client,
        status=models.ProjectStatus(status),
        start_date=start_date, end_date=end_date,
        tds_rate=tds_rate,
        gst_applicable=gst_applicable is not None,
    )
    db.add(project)
    db.flush()  # get project.id

    if monthly_income is not None:
        db.add(models.ProjectIncomeHistory(project_id=project.id, monthly_income=monthly_income, effective_from=start_date))

    db.commit()
    return RedirectResponse(f"/projects/{project.id}", status_code=302)


@router.get("/{project_id}", response_class=HTMLResponse)
async def project_detail(
    project_id: int,
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        return RedirectResponse("/projects", status_code=302)

    assignments = (
        db.query(models.EmployeeProjectAssignment)
        .filter_by(project_id=project_id)
        .order_by(models.EmployeeProjectAssignment.from_date.desc())
        .all()
    )
    active_employees = (
        db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
    )

    income_history = sorted(project.income_history, key=lambda r: r.effective_from, reverse=True)

    return templates.TemplateResponse("project_detail.html", {
        "request": request, "project": project,
        "assignments": assignments,
        "active_employees": active_employees,
        "today": date.today(),
        "ProjectStatus": models.ProjectStatus,
        "cost_snapshot": cost_analysis.project_current_snapshot(db, project),
        "cost_lifetime": cost_analysis.project_lifetime(db, project),
        "income_history": income_history,
        "current_gst_rate": cost_analysis.get_current_gst_rate(db),
        "project_charts": analytics.project_charts(db, project),
    })


@router.get("/{project_id}/edit", response_class=HTMLResponse)
async def edit_project_form(
    project_id: int,
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        return RedirectResponse("/projects", status_code=302)
    return templates.TemplateResponse("project_form.html", {
        "request": request, "project": project, "error": None,
    })


@router.post("/{project_id}/edit")
async def update_project(
    project_id: int,
    name: str = Form(...),
    client: str = Form(...),
    status: str = Form(...),
    start_date: date = Form(...),
    end_date: date | None = Form(None),
    tds_rate: Decimal | None = Form(None),
    gst_applicable: str | None = Form(None),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        return RedirectResponse("/projects", status_code=302)
    project.name = name
    project.client = client
    project.status = models.ProjectStatus(status)
    project.start_date = start_date
    project.end_date = end_date
    project.tds_rate = tds_rate
    project.gst_applicable = gst_applicable is not None
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


# ---------------------------------------------------------------------------
# Income history
# ---------------------------------------------------------------------------

@router.post("/{project_id}/update-income")
async def update_income(
    project_id: int,
    monthly_income: Decimal = Form(...),
    effective_from: date = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    cost_analysis.record_income_change(db, project_id, monthly_income, effective_from)
    return RedirectResponse(f"/projects/{project_id}", status_code=302)
