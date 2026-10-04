"""
routers/reviews.py — Log appreciation / escalation reviews.
"""

from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import require_login
from app.templates_config import templates

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/new", response_class=HTMLResponse)
async def new_review_form(
    request: Request,
    employee_id: int | None = None,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
    return templates.TemplateResponse("review_form.html", {
        "request": request,
        "employees": employees,
        "preselected_id": employee_id,
        "today": date.today(),
        "error": None,
    })


@router.post("/new")
async def create_review(
    request: Request,
    employee_id: int = Form(...),
    reviewer_id: int = Form(...),
    review_type: str = Form(...),
    review_date: date = Form(...),
    notes: str = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    if employee_id == reviewer_id:
        employees = db.query(models.Employee).filter_by(status="active").order_by(models.Employee.name).all()
        return templates.TemplateResponse("review_form.html", {
            "request": request, "employees": employees,
            "preselected_id": employee_id, "today": review_date,
            "error": "Reviewer and reviewee cannot be the same person.",
        }, status_code=400)

    review = models.Review(
        employee_id=employee_id,
        reviewer_id=reviewer_id,
        type=models.ReviewType(review_type),
        date=review_date,
        notes=notes.strip(),
    )
    db.add(review)
    db.commit()
    return RedirectResponse(f"/employees/{employee_id}", status_code=302)
