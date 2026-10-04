"""
auth.py — Session-based authentication for the single HR/admin account.

Uses Starlette's SessionMiddleware (itsdangerous-backed cookie) so that
any request carrying a valid session cookie is considered authenticated.

FastAPI dependency:
    def my_route(request: Request, user=Depends(require_login)):
        ...
"""

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SESSION_KEY = "user"


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def login_user(request: Request, username: str) -> None:
    """Store the authenticated username in the session."""
    request.session[SESSION_KEY] = username


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def current_user(request: Request) -> str | None:
    """Return the logged-in username, or None."""
    return request.session.get(SESSION_KEY)


# ---------------------------------------------------------------------------
# FastAPI dependency — redirects to /login if not authenticated
# ---------------------------------------------------------------------------

def require_login(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


# ---------------------------------------------------------------------------
# Authenticate against the DB
# ---------------------------------------------------------------------------

def authenticate(username: str, password: str, db: Session) -> models.AdminUser | None:
    admin = db.query(models.AdminUser).filter_by(username=username).first()
    if admin and verify_password(password, admin.password_hash):
        return admin
    return None
