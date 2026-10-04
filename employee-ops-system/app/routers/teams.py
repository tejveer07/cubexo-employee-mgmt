"""
routers/teams.py — Team CRUD: list, create, edit, view members.
"""

from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import require_login
from app.templates_config import templates

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def team_list(
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    teams = db.query(models.Team).order_by(models.Team.name).all()
    return templates.TemplateResponse("team_list.html", {"request": request, "teams": teams})


@router.get("/new", response_class=HTMLResponse)
async def new_team_form(
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
    return templates.TemplateResponse("team_form.html", {
        "request": request, "team": None, "employees": employees, "error": None,
    })


@router.post("/new")
async def create_team(
    request: Request,
    name: str = Form(...),
    team_lead_id: int | None = Form(None),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    if db.query(models.Team).filter_by(name=name).first():
        employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
        return templates.TemplateResponse("team_form.html", {
            "request": request, "team": None, "employees": employees,
            "error": f"Team '{name}' already exists.",
        }, status_code=400)

    team = models.Team(name=name, team_lead_id=team_lead_id or None)
    db.add(team)
    db.commit()
    return RedirectResponse(f"/teams/{team.id}", status_code=302)


@router.get("/{team_id}", response_class=HTMLResponse)
async def team_detail(
    team_id: int,
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    team = db.query(models.Team).filter_by(id=team_id).first()
    if not team:
        return RedirectResponse("/teams", status_code=302)

    current_members = (
        db.query(models.TeamMembership)
        .filter_by(team_id=team_id, to_date=None)
        .all()
    )
    past_members = (
        db.query(models.TeamMembership)
        .filter(models.TeamMembership.team_id == team_id, models.TeamMembership.to_date != None)
        .order_by(models.TeamMembership.to_date.desc())
        .all()
    )
    all_active_employees = (
        db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
    )

    return templates.TemplateResponse("team_detail.html", {
        "request": request, "team": team,
        "current_members": current_members, "past_members": past_members,
        "all_active_employees": all_active_employees,
        "today": date.today(),
    })


@router.get("/{team_id}/edit", response_class=HTMLResponse)
async def edit_team_form(
    team_id: int,
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    team = db.query(models.Team).filter_by(id=team_id).first()
    if not team:
        return RedirectResponse("/teams", status_code=302)
    employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
    return templates.TemplateResponse("team_form.html", {
        "request": request, "team": team, "employees": employees, "error": None,
    })


@router.post("/{team_id}/edit")
async def update_team(
    team_id: int,
    request: Request,
    name: str = Form(...),
    team_lead_id: int | None = Form(None),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    team = db.query(models.Team).filter_by(id=team_id).first()
    if not team:
        return RedirectResponse("/teams", status_code=302)

    conflict = db.query(models.Team).filter(
        models.Team.name == name, models.Team.id != team_id
    ).first()
    if conflict:
        employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
        return templates.TemplateResponse("team_form.html", {
            "request": request, "team": team, "employees": employees,
            "error": f"Team '{name}' already exists.",
        }, status_code=400)

    team.name = name
    team.team_lead_id = team_lead_id or None
    db.commit()
    return RedirectResponse(f"/teams/{team_id}", status_code=302)
