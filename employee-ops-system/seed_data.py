"""
seed_data.py — Seeds the database with:
  1. Default tech stack list
  2. First admin user (username: admin, password: changeme)

Run from the employee-ops-system/ directory:
    python seed_data.py

Safe to run multiple times — skips entries that already exist.
"""

import sys
import os

# Make sure app is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine
from app import models
from passlib.context import CryptContext

# Create tables if not already present
models.Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_TECH_STACKS = [
    "Python", "JavaScript", "TypeScript", "Java", "C#", "C++", "Go", "Rust", "PHP", "Ruby",
    "React", "Angular", "Vue.js", "Next.js", "Node.js", "FastAPI", "Django", "Flask",
    "Spring Boot", "ASP.NET", "Laravel",
    "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis", "Elasticsearch",
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Terraform", "Ansible",
    "Git", "GitHub Actions", "Jenkins", "Linux", "Nginx",
    "React Native", "Flutter", "Swift", "Kotlin",
    "TensorFlow", "PyTorch", "Pandas", "NumPy", "scikit-learn",
]

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "changeme"


def seed():
    db = SessionLocal()
    try:
        # --- Tech stacks ---
        existing_names = {ts.name.lower() for ts in db.query(models.TechStack).all()}
        new_stacks = []
        for name in DEFAULT_TECH_STACKS:
            if name.lower() not in existing_names:
                new_stacks.append(models.TechStack(name=name))

        if new_stacks:
            db.add_all(new_stacks)
            db.commit()
            print(f"[seed] Added {len(new_stacks)} tech stack(s).")
        else:
            print("[seed] Tech stacks already seeded — skipped.")

        # --- Admin user ---
        existing_admin = db.query(models.AdminUser).filter_by(username=ADMIN_USERNAME).first()
        if not existing_admin:
            admin = models.AdminUser(
                username=ADMIN_USERNAME,
                password_hash=pwd_context.hash(ADMIN_PASSWORD),
            )
            db.add(admin)
            db.commit()
            print(f"[seed] Admin user '{ADMIN_USERNAME}' created (password: {ADMIN_PASSWORD}).")
            print("[seed] ** Change the admin password after first login! **")
        else:
            print(f"[seed] Admin user '{ADMIN_USERNAME}' already exists — skipped.")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
