# Employee & Operations Management System — Build Spec

## 1. Overview

An internal, offline-first HR/operations tool to track employees, teams, projects, tech
stacks, and performance reviews (appreciation/escalation). Single-tenant, HR/admin-only
access, no per-employee login. Must run on a Windows machine with **no Python, Docker, or
database software pre-installed** — delivered as a standalone packaged executable.

This is a standalone system, fully separate from the existing SOD/EOD WhatsApp tracker
(different DB, different login, no shared code).

---

## 2. Tech Stack

- **Backend**: FastAPI (Python)
- **ORM**: SQLAlchemy
- **Database**: SQLite (single file, no server)
- **Migrations**: Alembic
- **Frontend**: Jinja2 templates + HTMX (server-rendered, no SPA build step)
- **Styling**: plain CSS (or Tailwind via CDN — no build pipeline, since target machine
  has no npm/node)
- **Packaging**: PyInstaller (`--onedir` mode), targeting Windows
- **Auth**: simple session-based login, single shared HR/admin account (hashed password,
  e.g. via `passlib`/`bcrypt`)
- **Server**: Uvicorn, bound to `127.0.0.1`, auto-launches default browser on startup

No internet access is assumed at runtime. No PDF export. No external services.

---

## 3. Data Model

### 3.1 Employee
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| name | str | |
| employee_code | str, unique | |
| email | str | |
| designation | str | |
| join_date | date | |
| exit_date | date, nullable | |
| team_lead_id | FK -> Employee.id, nullable | current lead, self-referential |
| status | enum(active, inactive) | |

Salary is **not** a column here — see 3.11 SalaryHistory.

### 3.2 Team
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| name | str | |
| team_lead_id | FK -> Employee.id | |

### 3.3 TeamMembership (historical team assignment)
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| employee_id | FK -> Employee.id | |
| team_id | FK -> Team.id | |
| from_date | date | |
| to_date | date, nullable | null = current |

### 3.4 Project
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| name | str | |
| client | str | |
| status | enum(active, completed, on_hold) | |
| start_date | date | |
| end_date | date, nullable | |
| tds_rate | numeric, nullable | current TDS %, single value (not historical) |
| gst_applicable | bool, default true | false = GST-exempt client (e.g. export/SEZ) |

Income is **not** a column here — see 3.12 ProjectIncomeHistory.

### 3.5 EmployeeProjectAssignment (historical project assignment)
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| employee_id | FK -> Employee.id | |
| project_id | FK -> Project.id | |
| role_on_project | str | |
| from_date | date | |
| to_date | date, nullable | null = ongoing |

### 3.6 TechStack
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| name | str, unique | seeded with common values; new ones addable via UI |

### 3.7 EmployeeTechStack (many-to-many)
| Field | Type | Notes |
|---|---|---|
| employee_id | FK -> Employee.id | |
| tech_stack_id | FK -> TechStack.id | |

### 3.8 Review
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| employee_id | FK -> Employee.id | |
| reviewer_id | FK -> Employee.id | |
| type | enum(appreciation, escalation) | |
| date | date | |
| notes | text | freeform, no rating field |

### 3.9 AdminUser
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| username | str, unique | |
| password_hash | str | |

### 3.10 OrgSettings (singleton, id=1)
| Field | Type | Notes |
|---|---|---|
| id | int, PK | always 1 |
| monthly_overhead | numeric | fixed monthly admin/management overhead, editable, **not historical** |
| updated_at | date, nullable | |

### 3.11 SalaryHistory (versioned employee salary)
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| employee_id | FK -> Employee.id | |
| monthly_salary | numeric | |
| effective_from | date | unique per (employee_id, effective_from); "current" = latest row with effective_from <= today |

### 3.12 ProjectIncomeHistory (versioned project income)
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| project_id | FK -> Project.id | |
| monthly_income | numeric | |
| effective_from | date | unique per (project_id, effective_from); same versioning pattern as SalaryHistory |

### 3.13 GstRateHistory (versioned org-wide GST rate)
| Field | Type | Notes |
|---|---|---|
| id | int, PK | |
| gst_rate | numeric | percent, e.g. 18.00 |
| effective_from | date | unique; seeded with one anchor row (18%, 2000-01-01) so nothing is ever "unset" |

None of these three history tables are ever hard-deleted or overwritten — a change is a new row (or, if the same `effective_from` is submitted again, an upsert of just that date's value). This mirrors the `TeamMembership`/`EmployeeProjectAssignment` history pattern already used elsewhere in this app, so a rate change only affects periods from its effective date forward.

---

## 4. Features

1. **Employee CRUD** — create/edit/deactivate employee, assign current team lead
2. **Employee profile page** (core screen) — shows:
   - Basic info (join date, designation, status, exit date if applicable)
   - Current team + team history timeline
   - Current + past project assignments with from/to dates and role
   - Tech stack tags
   - Team lead
   - Review history (appreciation/escalation) as a timeline
3. **Team CRUD** — create/edit team, assign lead, view current + past members
4. **Project CRUD** — create/edit project, view assigned employees over time
5. **Assignment management** — add/end an employee's project or team assignment
   (sets `to_date`, doesn't delete history)
6. **Tech stack management** — fixed list seeded on first run, "+ Add new" inline option
   from any employee edit form
7. **Reviews module** — log appreciation/escalation entries against an employee,
   freeform notes, dated, tied to a reviewer
8. **Search/filter** — filter employee list by team, project, tech stack, status
   (active/inactive)
9. **Dashboard home** — headcount summary, active project count, recent reviews feed
10. **Export DB** — button to download a timestamped copy of the current SQLite file
    (e.g. `employee_db_2026-08-25.db`)
11. **Import DB** — upload a `.db` file; auto-backs-up current DB first; runs a schema
    sanity check (verifies expected tables exist) before swapping; rejects on mismatch
12. **Auth** — single shared login, hashed password, session cookie
13. **Cost analysis** — per-project and org-wide profit/loss from recurring monthly salary
    vs. project income, net of GST (org-wide rate, optional per project) and TDS
    (per-project rate). A current-month snapshot (uses only currently active
    employees/projects/assignments, nets out admin/management overhead) and a
    lifetime-to-date view (prorated by day, correctly blending old and new rates
    across whatever salary/income/GST changes happened when — see 3.11–3.13 — shown
    as gross margin excluding overhead since overhead has no history)

---

## 5. Non-Functional Requirements

- Runs fully offline, no external network calls
- No admin rights required to run the packaged exe
- Startup should auto-open the default browser to `http://127.0.0.1:<port>`
- Database file (`app.db`) should live in a predictable location *outside* the PyInstaller
  bundle directory (e.g. next to the exe, or in `%APPDATA%`) so app updates don't wipe data
- On startup, run Alembic migrations automatically (or a lightweight schema-check) so
  imported DBs from older app versions don't crash the app
- Windows SmartScreen will likely flag the unsigned exe — not a bug, just expected

---

## 6. Suggested Folder Structure

```
employee-ops-system/
├── app/
│   ├── main.py                # FastAPI app entrypoint, uvicorn launch + browser open
│   ├── models.py               # SQLAlchemy models
│   ├── database.py             # engine/session setup, DB path resolution
│   ├── auth.py                 # login/session logic
│   ├── routers/
│   │   ├── employees.py
│   │   ├── teams.py
│   │   ├── projects.py
│   │   ├── reviews.py
│   │   ├── techstack.py
│   │   └── db_transfer.py      # import/export endpoints
│   ├── templates/               # Jinja2 templates
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── employee_profile.html
│   │   ├── employee_list.html
│   │   ├── team.html
│   │   ├── project.html
│   │   └── login.html
│   └── static/
│       └── style.css
├── alembic/
│   ├── versions/
│   └── env.py
├── alembic.ini
├── seed_data.py                 # seeds default tech stack list + first admin user
├── requirements.txt
├── build.spec                   # PyInstaller spec file
└── README.md
```

---

## 7. Build Order (Phases)

1. **Scaffolding** — FastAPI app skeleton, SQLAlchemy models, Alembic init + first
   migration, SQLite file creation, seed script (admin user + default tech stack list)
2. **Auth** — login page, session handling, protect all routes behind login
3. **Core CRUD** — Employee, Team, Project basic create/edit/list views
4. **Employee profile page** — the main aggregate view (team history, project history,
   tech stack, lead, reviews) — this is the centerpiece screen
5. **Assignment logic** — add/end team membership and project assignment with dates,
   validation to prevent overlapping "current" assignments where it doesn't make sense
6. **Reviews module** — add/list appreciation & escalation entries, timeline on profile
7. **Search/filter** — employee list filtering by team/project/tech stack/status
8. **Dashboard home** — headcount, active projects, recent reviews widgets
9. **Import/Export DB** — export endpoint (file download), import endpoint (upload +
   backup + sanity check + swap)
10. **Packaging** — PyInstaller `--onedir` build, test on a clean Windows machine (no
    Python installed) to confirm it runs standalone, verify browser auto-launch and
    correct DB file path resolution
11. **Polish** — basic styling pass, empty states, confirmation dialogs for destructive
    actions (deactivate employee, end assignment, import DB overwrite)

---

## 8. Notes for Claude Code

- Use SQLite with `check_same_thread=False` and a simple session-per-request pattern.
- Keep the DB path resolution logic in one place (`database.py`) so it's easy to point at
  `sys._MEIPASS`-adjacent locations correctly once bundled by PyInstaller (bundled temp
  dir vs. persistent app folder — the DB must NOT live inside the PyInstaller temp
  extraction directory, or it'll be wiped/inaccessible between runs).
- Historical tables (`TeamMembership`, `EmployeeProjectAssignment`) should never hard-delete
  rows when a membership "ends" — just set `to_date`. This preserves history.
- Validate on the "add tech stack" inline form to avoid duplicate near-identical entries
  (e.g. "React" vs "react" vs "ReactJS") — normalize casing at minimum.
- Add a `--dev` flag or environment variable to run with `reload=True` during development,
  but the packaged build should run without reload.
