"""
routers/analytics.py — visual analytics hub (/analytics).

Read-only. Every chart is rendered client-side by Chart.js (see
app/static/charts.js); this route only serves the pre-bucketed aggregates, which
the template embeds via Jinja's ``| tojson`` filter.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import require_login
from app.templates_config import templates
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def analytics_page(
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "charts": analytics.analytics_bundle(db),
    })
