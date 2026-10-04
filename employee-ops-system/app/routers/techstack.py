"""
routers/techstack.py — Tech stack management: list all, add new, delete.

/techstacks/              — list all tech stacks
/techstacks/add-inline    — POST: add a new one and redirect back (used from employee form)
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import require_login
from app.templates_config import templates

router = APIRouter(prefix="/techstacks", tags=["techstacks"])


@router.get("/", response_class=HTMLResponse)
async def techstack_list(
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    stacks = db.query(models.TechStack).order_by(models.TechStack.name).all()
    return templates.TemplateResponse("techstack_list.html", {
        "request": request,
        "stacks": stacks,
    })


@router.post("/add-inline")
async def add_tech_inline(
    name: str = Form(...),
    return_to: str = Form(default="/employees/new"),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    """
    Adds a tech stack if it doesn't already exist (case-insensitive),
    then redirects back to whatever page invoked it.
    """
    normalized = name.strip().title()
    if not normalized:
        return RedirectResponse(return_to, status_code=302)

    existing = db.query(models.TechStack).filter(
        models.TechStack.name.ilike(normalized)
    ).first()

    if not existing:
        db.add(models.TechStack(name=normalized))
        db.commit()
        # Append a query param so the form can show a success notice
        sep = "&" if "?" in return_to else "?"
        return RedirectResponse(f"{return_to}{sep}tech_added={normalized}", status_code=302)

    sep = "&" if "?" in return_to else "?"
    return RedirectResponse(f"{return_to}{sep}tech_added={existing.name}", status_code=302)


@router.post("/delete/{tech_id}")
async def delete_tech(
    tech_id: int,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Only delete if no employees are currently using it
    usage = db.query(models.EmployeeTechStack).filter_by(tech_stack_id=tech_id).count()
    if usage == 0:
        db.query(models.TechStack).filter_by(id=tech_id).delete()
        db.commit()
    return RedirectResponse("/techstacks/", status_code=302)
