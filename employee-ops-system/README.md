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

The app opens at **http://127.0.0.1:8767**

Default admin credentials: `admin` / `changeme` — **change after first login.**

## Production / Packaged Build

```bash
pip install pyinstaller
pyinstaller build.spec
```

The result is a single file, `dist/employee-ops-system.exe`. Copy it to a user-writable folder (e.g. `Documents\OpsSystem\`, not `Program Files`) and double-click. No Python or command line is needed on the target machine.

- On first launch the exe creates `app.db` next to itself and seeds the admin account (`admin` / `changeme`) and the tech-stack list.
- It starts a local server and opens the browser. If port 8767 is busy (e.g. a second copy is running), it uses the next free port (8768–8776).
- `build.spec` has `CONSOLE = False` (no console window). Set it to `True` to see output while debugging. With no console, output goes to `ops-system.log` next to the exe.
- Each PC has its own `app.db`. Data is not shared between machines.

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
- Importing a database (`/db/import`) checks that the file has every column the current models need. Older exports are rejected with the list of missing columns; tables added in newer versions are created automatically after import.
- In dev mode, `app.db` is created in the `employee-ops-system/` directory.
- Override location with the `APP_DB_PATH` environment variable.
