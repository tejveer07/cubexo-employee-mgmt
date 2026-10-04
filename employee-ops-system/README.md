# Employee & Operations Management System

Internal HR/operations tool for CubexO. Tracks employees, teams, projects, tech stacks, and performance reviews.

## Quick Start (Development)

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run DB migrations
alembic upgrade head

# 4. Seed initial data (tech stacks + admin user)
python seed_data.py

# 5. Run the development server (with hot-reload)
python -m app.main --dev
```

The app opens at **http://127.0.0.1:8765**

Default admin credentials: `admin` / `changeme` — **change after first login.**

## Production / Packaged Build

```bash
pip install pyinstaller
pyinstaller build.spec
```

The built exe will be in `dist/employee-ops-system/`. Run it directly — no Python installation required on the target machine.

## Project Structure

```
employee-ops-system/
├── app/
│   ├── main.py          # FastAPI entrypoint + Uvicorn launch
│   ├── database.py      # Engine/session, DB path resolution
│   ├── models.py        # SQLAlchemy ORM models
│   ├── auth.py          # Auth/session logic
│   ├── routers/         # Feature routers
│   ├── templates/       # Jinja2 HTML templates
│   └── static/          # CSS, JS assets
├── alembic/             # DB migrations
├── alembic.ini
├── seed_data.py
├── requirements.txt
├── build.spec           # PyInstaller config
└── PROGRESS.md          # Build phase tracker
```

## Database

- SQLite file (`app.db`) lives **next to the exe** in production — not inside the PyInstaller bundle.
- In dev mode, `app.db` is created in the `employee-ops-system/` directory.
- Override location with the `APP_DB_PATH` environment variable.
