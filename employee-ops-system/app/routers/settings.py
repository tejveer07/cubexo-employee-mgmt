"""
routers/settings.py — App settings. Currently: outbound-email (SMTP) config for
the project-assignment notification feature.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import require_login
from app.templates_config import templates
from app.services.notifications import load_smtp_config, save_smtp_config, send_email

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    s = db.query(models.OrgSettings).filter_by(id=1).first()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "s": s,
        "has_password": bool(s and s.smtp_password),
    })


@router.post("/email")
async def update_email_settings(
    request: Request,
    smtp_host: str = Form(""),
    smtp_port: str = Form(""),          # number input can POST "" — convert manually (see Bug 002)
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),      # blank => keep stored password
    email_from: str = Form(""),
    email_from_name: str = Form(""),
    smtp_use_tls: str | None = Form(None),
    smtp_use_ssl: str | None = Form(None),
    email_enabled: str | None = Form(None),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    port = int(smtp_port) if smtp_port.strip().isdigit() else None
    save_smtp_config(
        db,
        host=smtp_host,
        port=port,
        username=smtp_username,
        password=smtp_password,
        use_tls=smtp_use_tls is not None,
        use_ssl=smtp_use_ssl is not None,
        from_addr=email_from,
        from_name=email_from_name,
        enabled=email_enabled is not None,
    )
    request.session["_flash_success"] = "Email settings saved."
    return RedirectResponse("/settings", status_code=302)


@router.post("/email/test")
async def send_test_email(
    request: Request,
    test_to: str = Form(...),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
):
    cfg = load_smtp_config(db)
    ok = send_email(
        cfg,
        test_to.strip(),
        "CubexO Operations — test email",
        "<p>This is a test email from CubexO Operations. "
        "If you received it, SMTP is configured correctly.</p>",
        "This is a test email from CubexO Operations. "
        "If you received it, SMTP is configured correctly.\n",
    )
    if ok:
        request.session["_flash_success"] = f"Test email sent to {test_to.strip()}."
    else:
        request.session["_flash_error"] = (
            "Test email failed. Check that email is enabled and the SMTP settings "
            "are correct — see the server log for details."
        )
    return RedirectResponse("/settings", status_code=302)
