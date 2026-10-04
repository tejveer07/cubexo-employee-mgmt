"""
seed_data.py — Seeds the database with:
  1. Default tech stack list
  2. First admin user (username: admin, password: changeme)

Run from the employee-ops-system/ directory:
    python seed_data.py

Safe to run multiple times — skips entries that already exist. The same logic runs
automatically at app startup (app/services/bootstrap.py), so this script is only
needed for manual setup.
"""

import sys
import os

# Make sure app is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine
from app import models
from app.services.bootstrap import ADMIN_PASSWORD, ADMIN_USERNAME, ensure_defaults

# Create tables if not already present
models.Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()
    try:
        added, admin_created = ensure_defaults(db)
        if added:
            print(f"[seed] Added {added} tech stack(s).")
        else:
            print("[seed] Tech stacks already seeded — skipped.")

        if admin_created:
            print(f"[seed] Admin user '{ADMIN_USERNAME}' created (password: {ADMIN_PASSWORD}).")
            print("[seed] ** Change the admin password after first login! **")
        else:
            print(f"[seed] Admin user '{ADMIN_USERNAME}' already exists — skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
