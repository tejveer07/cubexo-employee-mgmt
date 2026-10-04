"""
routers/employees.py — Employee CRUD: list, create, edit, deactivate.
"""

from datetime import date
from decimal import Decimal
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import require_login
from app.templates_config import templates
from app.services import cost_analysis, analytics
from app.services.employees import apply_employee_exit
from app.services.notifications import load_smtp_config, notify_project_assignment

router = APIRouter(prefix="/employees", tags=["employees"])


def _optional_int(raw: str) -> int | None:
    """Parse a query-string id from a dropdown. Empty or non-numeric input means
    'no filter' instead of a 500 from int()."""
    raw = raw.strip()
    return int(raw) if raw.isdigit() else None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)  # matches /employees AND /employees/
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def employee_list(
    request: Request,
    status: str = "active",
    # Accept as strings so empty string ("") from unselected dropdowns
    # doesn't cause a 422 int-parse error — we convert manually below.
    team_id: str = "",
    project_id: str = "",
    tech_id: str = "",
    q: str = "",
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Convert empty strings to None
    team_id_int    = _optional_int(team_id)
    project_id_int = _optional_int(project_id)
    tech_id_int    = _optional_int(tech_id)

    query = db.query(models.Employee)

    if status in ("active", "inactive"):
        query = query.filter(models.Employee.status == status)

    if q.strip():
        query = query.filter(models.Employee.name.ilike(f"%{q.strip()}%"))

    if team_id_int:
        query = query.join(
            models.TeamMembership,
            (models.TeamMembership.employee_id == models.Employee.id) &
            (models.TeamMembership.to_date == None),
        ).filter(models.TeamMembership.team_id == team_id_int)

    if project_id_int:
        query = query.join(
            models.EmployeeProjectAssignment,
            (models.EmployeeProjectAssignment.employee_id == models.Employee.id) &
            (models.EmployeeProjectAssignment.to_date == None),
        ).filter(models.EmployeeProjectAssignment.project_id == project_id_int)

    if tech_id_int:
        query = query.join(
            models.EmployeeTechStack,
            models.EmployeeTechStack.employee_id == models.Employee.id,
        ).filter(models.EmployeeTechStack.tech_stack_id == tech_id_int)

    employees = query.order_by(models.Employee.name).all()

    teams = db.query(models.Team).order_by(models.Team.name).all()
    projects = db.query(models.Project).order_by(models.Project.name).all()
    tech_stacks = db.query(models.TechStack).order_by(models.TechStack.name).all()

    return templates.TemplateResponse("employee_list.html", {
        "request": request,
        "employees": employees,
        "teams": teams,
        "projects": projects,
        "tech_stacks": tech_stacks,
        "filters": {
            "status": status,
            "team_id": team_id_int,
            "project_id": project_id_int,
            "tech_id": tech_id_int,
            "q": q,
        },
    })


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_employee_form(
    request: Request,
    tech_added: str | None = None,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
    tech_stacks = db.query(models.TechStack).order_by(models.TechStack.name).all()
    return templates.TemplateResponse("employee_form.html", {
        "request": request,
        "employee": None,
        "all_employees": employees,
        "tech_stacks": tech_stacks,
        "employee_tech_ids": [],
        "error": None,
        "tech_added": tech_added,
    })


@router.post("/new", response_class=HTMLResponse)
async def create_employee(
    request: Request,
    name: str = Form(...),
    employee_code: str = Form(...),
    email: str = Form(...),
    designation: str = Form(...),
    join_date: date = Form(...),
    team_lead_id: int | None = Form(None),
    monthly_salary: Decimal | None = Form(None),
    tech_stack_ids: list[int] = Form(default=[]),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Check unique code
    if db.query(models.Employee).filter_by(employee_code=employee_code).first():
        employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
        tech_stacks = db.query(models.TechStack).order_by(models.TechStack.name).all()
        return templates.TemplateResponse("employee_form.html", {
            "request": request, "employee": None,
            "all_employees": employees, "tech_stacks": tech_stacks,
            "employee_tech_ids": tech_stack_ids,
            "error": f"Employee code '{employee_code}' already exists.",
        }, status_code=400)

    emp = models.Employee(
        name=name, employee_code=employee_code, email=email,
        designation=designation, join_date=join_date,
        team_lead_id=team_lead_id or None,
        status=models.EmployeeStatus.active,
    )
    db.add(emp)
    db.flush()  # get emp.id

    for tid in set(tech_stack_ids):
        db.add(models.EmployeeTechStack(employee_id=emp.id, tech_stack_id=tid))

    if monthly_salary is not None:
        db.add(models.SalaryHistory(employee_id=emp.id, monthly_salary=monthly_salary, effective_from=join_date))

    db.commit()
    return RedirectResponse(f"/employees/{emp.id}", status_code=302)


# ---------------------------------------------------------------------------
# Profile / Detail
# ---------------------------------------------------------------------------

@router.get("/{employee_id}", response_class=HTMLResponse)
async def employee_profile(
    employee_id: int,
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    emp = db.query(models.Employee).filter_by(id=employee_id).first()
    if not emp:
        return RedirectResponse("/employees", status_code=302)

    team_history = (
        db.query(models.TeamMembership)
        .filter_by(employee_id=employee_id)
        .order_by(models.TeamMembership.from_date.desc())
        .all()
    )
    project_history = (
        db.query(models.EmployeeProjectAssignment)
        .filter_by(employee_id=employee_id)
        .order_by(models.EmployeeProjectAssignment.from_date.desc())
        .all()
    )
    reviews = (
        db.query(models.Review)
        .filter_by(employee_id=employee_id)
        .order_by(models.Review.date.desc())
        .all()
    )
    all_teams = db.query(models.Team).order_by(models.Team.name).all()
    all_projects = db.query(models.Project).filter_by(status="active").order_by(models.Project.name).all()
    all_employees = db.query(models.Employee).filter(models.Employee.id != employee_id).order_by(models.Employee.name).all()

    salary_history = sorted(emp.salary_history, key=lambda r: r.effective_from, reverse=True)

    return templates.TemplateResponse("employee_profile.html", {
        "request": request,
        "emp": emp,
        "team_history": team_history,
        "project_history": project_history,
        "reviews": reviews,
        "all_teams": all_teams,
        "all_projects": all_projects,
        "all_employees": all_employees,
        "today": date.today(),
        "salary_history": salary_history,
        "salary_chart": analytics.employee_salary_series(emp),
        "reviews_chart": analytics.employee_reviews_series(emp),
    })


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

@router.get("/{employee_id}/edit", response_class=HTMLResponse)
async def edit_employee_form(
    employee_id: int,
    request: Request,
    tech_added: str | None = None,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    emp = db.query(models.Employee).filter_by(id=employee_id).first()
    if not emp:
        return RedirectResponse("/employees", status_code=302)
    all_employees = db.query(models.Employee).filter(models.Employee.id != employee_id).order_by(models.Employee.name).all()
    tech_stacks = db.query(models.TechStack).order_by(models.TechStack.name).all()
    employee_tech_ids = [et.tech_stack_id for et in emp.tech_stacks]
    return templates.TemplateResponse("employee_form.html", {
        "request": request, "employee": emp,
        "all_employees": all_employees, "tech_stacks": tech_stacks,
        "employee_tech_ids": employee_tech_ids, "error": None,
        "tech_added": tech_added,
    })


@router.post("/{employee_id}/edit", response_class=HTMLResponse)
async def update_employee(
    employee_id: int,
    request: Request,
    name: str = Form(...),
    employee_code: str = Form(...),
    email: str = Form(...),
    designation: str = Form(...),
    join_date: date = Form(...),
    exit_date: date | None = Form(None),
    team_lead_id: int | None = Form(None),
    tech_stack_ids: list[int] = Form(default=[]),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    emp = db.query(models.Employee).filter_by(id=employee_id).first()
    if not emp:
        return RedirectResponse("/employees", status_code=302)

    # Check code uniqueness (excluding self)
    conflict = db.query(models.Employee).filter(
        models.Employee.employee_code == employee_code,
        models.Employee.id != employee_id,
    ).first()
    if conflict:
        all_employees = db.query(models.Employee).filter(models.Employee.id != employee_id).order_by(models.Employee.name).all()
        tech_stacks = db.query(models.TechStack).order_by(models.TechStack.name).all()
        return templates.TemplateResponse("employee_form.html", {
            "request": request, "employee": emp,
            "all_employees": all_employees, "tech_stacks": tech_stacks,
            "employee_tech_ids": tech_stack_ids,
            "error": f"Employee code '{employee_code}' already in use.",
        }, status_code=400)

    emp.name = name
    emp.employee_code = employee_code
    emp.email = email
    emp.designation = designation
    emp.join_date = join_date
    emp.exit_date = exit_date
    emp.team_lead_id = team_lead_id or None

    # A past exit date means the employee has already left — deactivate now and
    # close their open memberships/assignments, rather than waiting for the sweep.
    if (
        exit_date is not None
        and exit_date < date.today()
        and emp.status == models.EmployeeStatus.active
    ):
        apply_employee_exit(db, emp, exit_date)

    # Update tech stacks
    db.query(models.EmployeeTechStack).filter_by(employee_id=employee_id).delete()
    for tid in set(tech_stack_ids):
        db.add(models.EmployeeTechStack(employee_id=employee_id, tech_stack_id=tid))

    db.commit()
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


# ---------------------------------------------------------------------------
# Deactivate / Reactivate
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/deactivate")
async def deactivate_employee(
    employee_id: int,
    exit_date: date = Form(default_factory=date.today),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    emp = db.query(models.Employee).filter_by(id=employee_id).first()
    if emp:
        apply_employee_exit(db, emp, exit_date)
        db.commit()
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


@router.post("/{employee_id}/reactivate")
async def reactivate_employee(
    employee_id: int,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    emp = db.query(models.Employee).filter_by(id=employee_id).first()
    if emp:
        emp.status = models.EmployeeStatus.active
        emp.exit_date = None
        db.commit()
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


# ---------------------------------------------------------------------------
# Assignment endpoints (Phase 5)
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/assign-team")
async def assign_team(
    employee_id: int,
    request: Request,
    team_id: int = Form(...),
    from_date: date = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not db.get(models.Team, team_id):
        request.session["_flash_error"] = "That team no longer exists."
        return RedirectResponse(f"/employees/{employee_id}", status_code=302)

    # Close any open memberships first
    db.query(models.TeamMembership).filter_by(employee_id=employee_id, to_date=None).update({"to_date": from_date})
    db.add(models.TeamMembership(employee_id=employee_id, team_id=team_id, from_date=from_date))
    db.commit()
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


@router.post("/{employee_id}/end-team/{membership_id}")
async def end_team_membership(
    employee_id: int,
    membership_id: int,
    to_date: date = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    m = db.query(models.TeamMembership).filter_by(id=membership_id, employee_id=employee_id).first()
    if m and not m.to_date:
        m.to_date = to_date
        db.commit()
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


@router.post("/{employee_id}/assign-project")
async def assign_project(
    employee_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    project_id: int = Form(...),
    role_on_project: str = Form(...),
    from_date: date = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not db.get(models.Project, project_id):
        request.session["_flash_error"] = "That project no longer exists."
        return RedirectResponse(f"/employees/{employee_id}", status_code=302)

    # Close any open project assignment first — an employee is on one project at a
    # time, so cost analysis attributes their whole salary to a single project.
    db.query(models.EmployeeProjectAssignment).filter_by(
        employee_id=employee_id, to_date=None
    ).update({"to_date": from_date})
    db.add(models.EmployeeProjectAssignment(
        employee_id=employee_id, project_id=project_id,
        role_on_project=role_on_project, from_date=from_date,
    ))
    db.commit()

    # Best-effort assignment email — dispatched after commit so a slow/unreachable
    # mail server can never block or fail the assignment itself.
    cfg = load_smtp_config(db)
    if cfg.enabled:
        emp = db.get(models.Employee, employee_id)
        proj = db.get(models.Project, project_id)
        if emp and proj and emp.email and "@" in emp.email:
            background_tasks.add_task(
                notify_project_assignment, cfg, emp.email, emp.name,
                proj.name, proj.client, role_on_project, from_date,
            )
            request.session["_flash_success"] = f"Assigned. Notification sent to {emp.email}."
        elif emp:
            request.session["_flash_error"] = (
                f"Assigned — {emp.name} has no valid email, so no notification was sent."
            )

    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


@router.post("/{employee_id}/end-project/{assignment_id}")
async def end_project_assignment(
    employee_id: int,
    assignment_id: int,
    to_date: date = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    a = db.query(models.EmployeeProjectAssignment).filter_by(id=assignment_id, employee_id=employee_id).first()
    if a and not a.to_date:
        a.to_date = to_date
        db.commit()
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


# ---------------------------------------------------------------------------
# Salary history
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/update-salary")
async def update_salary(
    employee_id: int,
    monthly_salary: Decimal = Form(...),
    effective_from: date = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    cost_analysis.record_salary_change(db, employee_id, monthly_salary, effective_from)
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)


# ---------------------------------------------------------------------------
# (Tech stack inline add is handled by routers/techstack.py)
# ---------------------------------------------------------------------------
