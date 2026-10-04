"""
services/bootstrap.py — Idempotent first-run defaults: the starter tech-stack list and
the first admin account. Called on every startup (main.py lifespan) so a freshly
packaged exe with an empty app.db is usable immediately, and by seed_data.py.

Only inserts what is missing, so it never overwrites an existing admin password or
tech stack.
"""

from sqlalchemy.orm import Session

from app import models
from app.auth import hash_password

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


def ensure_defaults(db: Session) -> tuple[int, bool]:
    """Add missing default tech stacks and the admin user. Returns
    (number of tech stacks added, whether the admin user was created)."""
    existing_names = {ts.name.lower() for ts in db.query(models.TechStack).all()}
    new_stacks = [
        models.TechStack(name=name)
        for name in DEFAULT_TECH_STACKS
        if name.lower() not in existing_names
    ]
    db.add_all(new_stacks)

    admin_created = False
    if not db.query(models.AdminUser).filter_by(username=ADMIN_USERNAME).first():
        db.add(models.AdminUser(username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD)))
        admin_created = True

    db.commit()
    return len(new_stacks), admin_created
