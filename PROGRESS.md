# Employee & Operations Management System — Progress Tracker

> **Project**: CubexO Internal HR/Operations Tool  
> **Stack**: FastAPI · SQLAlchemy · SQLite · Alembic · Jinja2 · HTMX · PyInstaller  
> **Target**: Standalone Windows `.exe`, offline-first, single HR/admin login  
> Last updated: 2026-08-26

---

## Phase Summary

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| 1 | Scaffolding | ✅ Done | Models, DB, Alembic migration, seed script |
| 2 | Auth | ✅ Done | Login/logout, session cookie, require_login dependency |
| 3 | Core CRUD | ✅ Done | Employee / Team / Project create-edit-list + templates |
| 4 | Employee Profile Page | ✅ Done | Integrated into Phase 3 — full aggregate view |
| 5 | Assignment Logic | ✅ Done | Add/end team & project assignments — history preserved |
| 6 | Reviews Module | ✅ Done | Appreciation/escalation log, timeline on profile |
| 7 | Search / Filter | ✅ Done | Employee list filtering by team/project/tech/status/name |
| 8 | Dashboard Home | ✅ Done | Headcount, active projects, recent reviews feed |
| 9 | Import / Export DB | ✅ Done | Export download, import with schema check + auto-backup |
| 10 | Packaging | ✅ Done | `build.spec` created; DB path PyInstaller-aware |
| 11 | Polish | ✅ Done | Inter font, full CSS, breadcrumbs, empty states, confirm dialogs, bug fixes |
| 12 | Cost Analysis | ✅ Done | Per-project & org-wide income/salary/overhead profit tracking |
| 13 | Visual Analytics | ✅ Done | Chart.js charts: /analytics hub + chart sections on dashboard, cost-analysis, employee & project pages |

---

## Phase 1 — Scaffolding ✅

**Goal**: Project skeleton, all SQLAlchemy models, Alembic setup, SQLite file creation, seed script.

### Deliverables
- [x] Folder structure created (`app/`, `app/routers/`, `app/templates/`, `app/static/`, `alembic/`)
- [x] `requirements.txt`
- [x] `app/database.py` — engine/session setup, DB path resolution (PyInstaller-aware)
- [x] `app/models.py` — all 9 models (Employee, Team, TeamMembership, Project, EmployeeProjectAssignment, TechStack, EmployeeTechStack, Review, AdminUser)
- [x] `app/main.py` — FastAPI app entrypoint, Uvicorn launch, browser auto-open
- [x] `alembic.ini` + `alembic/env.py` — configured for dynamic DB path
- [x] Initial Alembic migration generated and applied
- [x] `seed_data.py` — seeds default tech stack list + first admin user (admin / changeme)

---

## Phase 2 — Auth 🔲

**Goal**: Login page, session cookie, all routes protected behind login.

### Deliverables
- [ ] `app/auth.py` — password hashing/verification, session middleware
- [ ] `app/templates/login.html` — login form
- [ ] Login/logout routes in `app/main.py` or dedicated router
- [ ] Dependency: `get_current_user` used on all protected routes
- [ ] Redirect unauthenticated requests to `/login`

---

## Phase 3 — Core CRUD 🔲

**Goal**: Create / Edit / List views for Employee, Team, Project.

### Deliverables
- [ ] `app/routers/employees.py` — list, create, edit, deactivate
- [ ] `app/routers/teams.py` — list, create, edit
- [ ] `app/routers/projects.py` — list, create, edit, status change
- [ ] Templates: `employee_list.html`, `team.html`, `project.html`, shared forms
- [ ] HTMX-powered inline editing where applicable

---

## Phase 4 — Employee Profile Page 🔲

**Goal**: The centerpiece screen — all employee data in one aggregate view.

### Deliverables
- [ ] `app/templates/employee_profile.html`
- [ ] Profile route in `employees.py` — aggregates team history, project history, tech stack, reviews
- [ ] Team history timeline
- [ ] Project assignment history with from/to dates and role
- [ ] Tech stack tag display
- [ ] Review history timeline (appreciation/escalation)
- [ ] Current team lead display

---

## Phase 5 — Assignment Logic 🔲

**Goal**: Add/end team & project assignments; preserve history, no hard deletes.

### Deliverables
- [ ] Add team membership form + endpoint (sets `from_date`, `to_date=null`)
- [ ] End team membership endpoint (sets `to_date`)
- [ ] Add project assignment form + endpoint
- [ ] End project assignment endpoint
- [ ] Validation: prevent duplicate open (null `to_date`) assignments for the same employee

---

## Phase 6 — Reviews Module 🔲

**Goal**: Log appreciation / escalation entries against an employee.

### Deliverables
- [ ] `app/routers/reviews.py`
- [ ] Add review form (employee, reviewer, type, date, notes)
- [ ] Reviews timeline on employee profile
- [ ] Filter reviews by type (appreciation / escalation)

---

## Phase 7 — Search / Filter 🔲

**Goal**: Filter the employee list by team, project, tech stack, and status.

### Deliverables
- [ ] Filter bar on `employee_list.html`
- [ ] Query params: `?team=`, `?project=`, `?tech=`, `?status=`
- [ ] HTMX-powered live filtering (no full page reload)

---

## Phase 8 — Dashboard Home 🔲

**Goal**: At-a-glance overview on login landing.

### Deliverables
- [ ] `app/templates/dashboard.html`
- [ ] Headcount widget (total active / inactive)
- [ ] Active projects count
- [ ] Recent reviews feed (last 10)
- [ ] Quick-links to employee list, teams, projects

---

## Phase 9 — Import / Export DB 🔲

**Goal**: Allow HR to backup and restore the SQLite database.

### Deliverables
- [ ] `app/routers/db_transfer.py`
- [ ] Export endpoint: streams timestamped `.db` file download
- [ ] Import endpoint: accepts `.db` upload, backs up current DB, schema sanity check, swap
- [ ] Rejects import if expected tables are missing
- [ ] UI buttons on settings/dashboard page

---

## Phase 10 — Packaging 🔲

**Goal**: Standalone Windows `.exe` via PyInstaller.

### Deliverables
- [ ] `build.spec` — PyInstaller spec (`--onedir`, includes templates/static)
- [ ] DB path resolves to folder *next to* exe (not inside PyInstaller temp dir)
- [ ] `--dev` flag / env var for `reload=True` during development
- [ ] Alembic migrations run automatically on startup
- [ ] Browser auto-launch to `http://127.0.0.1:<port>`
- [ ] Tested on a clean Windows environment (no Python installed)

---

## Phase 11 — Polish 🔲

**Goal**: Production-ready look and feel.

### Deliverables
- [ ] `app/static/style.css` — full styling pass
- [ ] Empty states for all list views
- [ ] Confirmation dialogs for destructive actions (deactivate employee, end assignment, import DB)
- [ ] Flash/toast messages for success/error feedback
- [ ] Responsive layout (usable on laptop screen)

---

## Phase 12 — Cost Analysis ✅

**Goal**: Per-project and org-wide profit/loss tracking from recurring monthly salary and project income, with GST/TDS tax deductions and full salary/income/GST-rate history (a rate change only affects periods from its effective date forward).

### Deliverables
- [x] `SalaryHistory`, `ProjectIncomeHistory`, `GstRateHistory` — versioned rate tables (never overwritten, upsert-by-effective_from), replacing the original flat `Employee.monthly_salary`/`Project.monthly_income` columns from the first pass at this feature
- [x] `Project.tds_rate` (single current value, not historical) and `Project.gst_applicable` (per-project GST exemption flag); `OrgSettings.monthly_overhead` (single current value, not historical)
- [x] `app/services/cost_analysis.py` — daily-rate proration (`monthly * 12 / 365`) over piecewise-constant history segments; current-month snapshot and lifetime-to-date views; GST computed by crossing income segments against GST-rate segments since both vary independently over time
- [x] `app/routers/cost_analysis.py` — `/cost-analysis` page + overhead edit + GST rate change endpoints
- [x] Salary History / Income History cards (timeline + "record a change" mini-form) on employee profile / project detail, mirroring the existing team/project assignment history pattern
- [x] `db_transfer.py` `EXPECTED_TABLES` updated for `org_settings`, `salary_history`, `project_income_history`, `gst_rate_history`

---

## Phase 13 — Visual Analytics ✅

**Goal**: Turn the number cards / tables into charts — cost & profit trends, money composition, per-project P/L, headcount and review breakdowns.

### Deliverables
- [x] `app/services/analytics.py` — chart-ready aggregates, all JSON-safe primitives (no `Decimal`/`date`). Reuses `cost_analysis` helpers (`_build_segments`, `_segment_total`, `_income_and_gst_to_date`, …); monthly series windowed to one calendar month with the same `monthly*12/365` proration. Overhead excluded from every trend/lifetime profit (no history). Leading no-activity months trimmed from the cost trend.
- [x] `app/routers/analytics.py` — `/analytics` hub page (read-only; data embedded via `{{ ...|tojson }}`, no JSON API)
- [x] Chart sections added to `dashboard.html`, `cost_analysis.html`, `employee_profile.html`, `project_detail.html`; context vars added in `main.py` / `routers/cost_analysis.py` / `routers/employees.py` / `routers/projects.py`
- [x] `app/static/charts.js` — shared `window.Charts` helper (Chart.js defaults, palette from `style.css`, `bar`/`line`/`doughnut` builders that no-op on missing `<canvas>`)
- [x] `base.html` — new `{% block scripts %}` before `</body>`, "Analytics" nav link
- [x] `.chart-grid` / `.chart-card` / `.chart-section-title` styles appended to `style.css`
- [x] Chart.js 4.4.4 from jsDelivr CDN (offline gap noted in CLAUDE.md alongside the HTMX one — vendor into `app/static/vendor/` to close it)

---

## Decisions & Notes

| Date | Decision |
|------|----------|
| 2026-08-25 | Tech stack confirmed: FastAPI + SQLite + Jinja2 + HTMX + PyInstaller |
| 2026-08-25 | Auth: single shared admin account, bcrypt hashed, session cookie |
| 2026-08-25 | History preserved via `to_date` nullability — no hard deletes on assignments |
| 2026-08-25 | DB path: next to exe or in `%APPDATA%`, NOT inside PyInstaller temp dir |
| 2026-08-25 | Seed admin credentials: `admin` / `changeme` (user should change on first login) |
| 2026-08-26 | Cost analysis: salary/income modeled as monthly recurring; per-project cost prorated daily by assignment overlap (`monthly*12/365`); overhead is a single editable figure netted only in the current-month view, not the lifetime view |
| 2026-08-27 | Cost analysis v2: salary/income/GST rate are versioned history (never overwritten, effective-dated) so a rate change never retroactively rewrites past Lifetime figures — same pattern as `to_date`-based assignment history. TDS (per project) and overhead (org-wide) stay single current values by design — TDS rarely changes and overhead has no historical record. GST is optional per project (`gst_applicable` flag) for exempt clients. |
| 2026-09-02 | Visual analytics: `app/services/analytics.py` buckets the existing `cost_analysis` figures by calendar month (same `monthly*12/365` proration engine, windowed to one month) and by category — returns JSON-safe primitives only. Charts are client-side Chart.js 4.4.4 (CDN via jsDelivr; drop the file into `app/static/vendor/` and swap the `src` for fully-offline packaging). New `/analytics` hub page + chart sections embedded on dashboard / cost-analysis / employee-profile / project-detail via `{{ ...|tojson }}` (no JSON API). Monthly trend points reconcile with the **Lifetime** view, not the This-Month run-rate snapshot (the snapshot isn't day-prorated). Shared JS helper: `app/static/charts.js` (`window.Charts`). |
