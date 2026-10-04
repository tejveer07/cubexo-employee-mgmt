"""
services/notifications.py — Outbound email for assignment notifications.

Config lives in the OrgSettings singleton (id=1), edited by the admin on the
/settings page. Sending is **best-effort**: send_email never raises and returns a
bool, and assignment routes dispatch it via FastAPI BackgroundTasks so a slow or
unreachable mail server can never block or fail the assignment itself.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app import models
from app.templates_config import templates

log = logging.getLogger("ops.notifications")

DEFAULT_PORT = 587
DEFAULT_FROM_NAME = "CubexO Operations"


# ---------------------------------------------------------------------------
# Config (read from / written to OrgSettings id=1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SmtpConfig:
    """Plain primitives only — safe to hand to a BackgroundTask after the DB
    session that produced it has been closed."""
    enabled: bool
    host: str
    port: int
    username: str
    password: str
    use_tls: bool  # STARTTLS
    use_ssl: bool  # implicit TLS (port 465)
    from_addr: str
    from_name: str


def load_smtp_config(db: Session) -> SmtpConfig:
    s = db.query(models.OrgSettings).filter_by(id=1).first()
    if s is None:
        return SmtpConfig(False, "", "", "", "", True, False, "", DEFAULT_FROM_NAME)
    username = (s.smtp_username or "").strip()
    return SmtpConfig(
        enabled=bool(s.email_enabled),
        host=(s.smtp_host or "").strip(),
        port=int(s.smtp_port) if s.smtp_port else DEFAULT_PORT,
        username=username,
        password=s.smtp_password or "",
        use_tls=bool(s.smtp_use_tls),
        use_ssl=bool(s.smtp_use_ssl),
        from_addr=(s.email_from or "").strip() or username,
        from_name=(s.email_from_name or "").strip() or DEFAULT_FROM_NAME,
    )


def save_smtp_config(
    db: Session,
    *,
    host: str,
    port: int | None,
    username: str,
    password: str | None,
    use_tls: bool,
    use_ssl: bool,
    from_addr: str,
    from_name: str,
    enabled: bool,
) -> models.OrgSettings:
    """Upsert the OrgSettings singleton. A blank `password` keeps the stored one."""
    s = db.query(models.OrgSettings).filter_by(id=1).first()
    if s is None:
        s = models.OrgSettings(id=1, monthly_overhead=0)
        db.add(s)
    s.smtp_host = host.strip() or None
    s.smtp_port = port or None
    s.smtp_username = username.strip() or None
    if password:  # blank => leave existing password untouched
        s.smtp_password = password
    s.smtp_use_tls = use_tls
    s.smtp_use_ssl = use_ssl
    s.email_from = from_addr.strip() or None
    s.email_from_name = from_name.strip() or None
    s.email_enabled = enabled
    s.updated_at = date.today()
    db.commit()
    return s


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_email(cfg: SmtpConfig, to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Best-effort send. Returns True on success, False on any problem. Never raises."""
    if not cfg.enabled:
        log.info("email disabled — not sending %r to %s", subject, to)
        return False
    if not to or "@" not in to:
        log.warning("email skipped — invalid recipient %r", to)
        return False
    if not cfg.host:
        log.warning("email skipped — SMTP host not configured")
        return False

    msg = EmailMessage()
    msg["From"] = f"{cfg.from_name} <{cfg.from_addr}>" if cfg.from_addr else cfg.from_name
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        if cfg.use_ssl:
            with smtplib.SMTP_SSL(cfg.host, cfg.port, context=ssl.create_default_context(), timeout=15) as smtp:
                _login_and_send(smtp, cfg, msg)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as smtp:
                if cfg.use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                _login_and_send(smtp, cfg, msg)
    except Exception:
        log.exception("email send failed — %r to %s", subject, to)
        return False

    log.info("email sent — %r to %s", subject, to)
    return True


def _login_and_send(smtp: smtplib.SMTP, cfg: SmtpConfig, msg: EmailMessage) -> None:
    if cfg.username:
        smtp.login(cfg.username, cfg.password)
    smtp.send_message(msg)


def _render(name: str, ctx: dict) -> str:
    return templates.env.get_template(f"emails/{name}").render(**ctx)


# ---------------------------------------------------------------------------
# Event-specific
# ---------------------------------------------------------------------------

def notify_project_assignment(
    cfg: SmtpConfig,
    to_email: str,
    employee_name: str,
    project_name: str,
    client: str,
    role: str,
    from_date: date,
) -> bool:
    ctx = {
        "employee_name": employee_name,
        "project_name": project_name,
        "client": client,
        "role": role,
        "from_date": from_date.strftime("%d %b %Y"),
        "from_name": cfg.from_name,
    }
    subject = f"You've been assigned to {project_name}"
    return send_email(
        cfg,
        to_email,
        subject,
        _render("project_assigned.html", ctx),
        _render("project_assigned.txt", ctx),
    )
