# CLAUDE.md — AI Build Notes & Conventions

> This file is maintained by Claude (AI assistant) to track architectural decisions,
> known gotchas, and conventions for this project. Update it whenever a non-obvious
> decision is made or a bug is fixed.

---

## Project Summary

**Employee & Operations Management System** for CubexO.  
Single-tenant, offline-first HR tool. FastAPI + SQLAlchemy + SQLite + Jinja2 + HTMX.  
Packaged as a standalone Windows exe via PyInstaller.

---

## Critical Bug Log

### Bug 001 — Nested `<form>` caused tech stack name to overwrite employee name
**Date**: 2026-08-25  
**Symptom**: Creating an employee with a tech stack selected — the tech stack name was being  
treated as the employee name. Adding team lead also appeared broken.  
**Root Cause**: `employee_form.html` had a `<form>` element *inside* the main `<form>`.  
HTML does not support nested forms. Browsers ignore the inner `<form>` tag entirely,  
so all its inputs (including `<input name="name">` for the tech stack) become part of  
the outer form. When the outer form submitted, there were two `name` fields — the  
employee name AND the tech stack name input — confusing FastAPI's form parser.  
**Fix**: Moved the "Add tech stack" form completely *outside* (below) the employee form.  
It now posts to `/techstacks/add-inline` with a `return_to` field to redirect back.  
**Rule**: **Never nest a `<form>` inside another `<form>` in any template.**

### Bug 002 — Employee list filter: 307 redirect → 422 Unprocessable Entity
**Date**: 2026-08-25  
**Symptom**: Searching by name or filtering caused a 307 redirect then 422 error.  
**Root Cause 1 (307)**: Router registered route as `"/"` under prefix `/employees`,  
making it only match `/employees/`. FastAPI auto-redirects `/employees` → `/employees/`.  
**Root Cause 2 (422)**: Unselected dropdown `<select>` fields submit as empty string `""`  
(`team_id=&project_id=&tech_id=`). FastAPI's `int | None` type annotation tries to  
parse `""` as int and fails with 422 Unprocessable Entity.  
**Fix**:  
1. Registered the list route under both `""` AND `"/"` so both paths work without redirect.  
2. Changed `team_id`, `project_id`, `tech_id` query params to `str = ""` and manually  
   convert: `int(x) if x.strip() else None`. This tolerates empty strings from dropdowns.  
**Rule**: **Query params that come from `<select>` elements should be typed as `str` in**  
**FastAPI and converted manually — empty string `""` is not `None`.**

### Bug 003 — Crash crossing two open-ended history segments (cost analysis)
**Date**: 2026-08-27  
**Symptom**: `TypeError` inside `_effective_window` when computing GST for a project whose
*current* income rate needed crossing against the *current* GST rate — i.e. two segments
that are each still open-ended (`effective_end = None`, no successor row yet).  
**Root Cause**: `_effective_window(range_start, range_end, period_start, period_end)` did
`end = min(effective_end, period_end)` assuming `period_end` is always a concrete date.
That's true for its original use (range vs. a bounded query window), but
`_income_and_gst_to_date` reuses it to intersect two *segments* directly — and when both
are the latest, open-ended entry, `period_end` is `None` too, so `min(None, None)` blows up.  
**Fix**: `_effective_window` now handles all four combinations explicitly — if both ends are
`None` the result stays open-ended (`end=None`); the caller's outer `_overlap_days` call
(against the real, always-concrete query period) resolves it to a final day count.  
**Rule**: **Any helper that intersects two ranges must handle both ends being open — don't**
**assume only one side of a range comparison can be unbounded.**

### Bug 004 — Cost analysis: wrong / irreconcilable figures
**Date**: 2026-09-02
**Symptoms & fixes** (all in `app/services/cost_analysis.py` unless noted):
1. **Salary double-counted across projects.** `assign_project` (`routers/employees.py`)
   never closed an employee's prior open assignment (unlike `assign_team`), so a
   shared employee's *whole* salary was added to every project they were on.
   **Fix**: `assign_project` now closes open assignments first — one active project
   per employee.
2. **GST basis.** Reviewed switching to GST-inclusive extraction
   (`gross * rate / (100 + rate)`); **decision: keep the original**
   `gross * rate / 100`, subtracted from gross, as the single formula. No change.
3. **Snapshot cost counted dangling/future assignments.** `project_current_snapshot`
   filtered only `to_date IS NULL`. **Fix**: also require `from_date <= as_of` and
   `_employed_on(employee, as_of)`.
4. **Gross income depended on GST-rate coverage.** `_income_and_gst_to_date` only
   accumulated gross inside the income×GST segment cross, so a period with no GST-rate
   row contributed 0 gross. **Fix**: gross is now always `_segment_total(income…)`;
   the cross loop only sums GST.
5. **Per-card rounding drift.** Full-precision Decimals were rounded independently per
   template cell, so `profit ≠ shown(net) − shown(cost) − shown(overhead)`. **Fix**:
   `_money()` helper quantizes every returned figure to 2 dp at the 4 dataclass
   return sites; derived values are computed from the quantized parts.
6. **`exit_date` ignored unless the Deactivate action was used.** The edit-employee
   form sets `exit_date` without flipping `status` or closing assignments, so a
   departed employee could still be billed (snapshots keyed on `status`;
   `project_lifetime` keyed on assignment `to_date`). A *future* `exit_date` also
   made `org_lifetime` project salary past today. **Fix**: new `_employed_on(emp,
   as_of)` helper (`status active` AND `exit_date` is None/future) gates both
   snapshot salary loops; `project_lifetime` intersects each assignment window with
   `[join_date, exit_date]`; `org_lifetime` caps `period_end` at
   `min(exit_date, today)`.
**Not changed** (deliberate): `_overlap_days` inclusive `+1` day count (documented
approximation); TDS treatment/label; org salary totals still count all
active/on-record employees incl. bench, so they do NOT foot to the per-project
breakdown — a note in `cost_analysis.html` explains this.
**Rule**: **Any new money figure returned from `cost_analysis.py` must pass**
**through `_money()`.**

---

## Architecture Decisions

### DB Path Resolution
Defined in `app/database.py`. Order of precedence:
1. `APP_DB_PATH` env var (absolute path)
2. Folder next to `sys.executable` when frozen (PyInstaller mode)
3. Folder next to `database.py` (dev mode)

**Rule**: DB must never live inside the PyInstaller temp extraction dir (`sys._MEIPASS`) —
it gets wiped between runs.

### Auth
- Single shared admin account. No per-employee logins.
- `passlib[bcrypt]` for hashing — **pin `bcrypt==4.0.1`** in requirements.txt.
  bcrypt 4.0+ broke passlib's version detection (it removed `__about__`). 
  bcrypt 4.0.1 is the last version that works with passlib 1.7.4 without patching.
- Session via Starlette `SessionMiddleware` (itsdangerous signed cookie).
- `require_login` FastAPI dependency — use on every protected route.
- **Forgot password** (`/forgot-password`, `main.py`): username + new password, **no
  verification by design** (local single-admin app). Anyone who can reach `/login` can
  reset the admin password — do not expose the port on an untrusted network.

### History Preservation
`TeamMembership` and `EmployeeProjectAssignment` rows are **never hard-deleted**.  
To end a membership/assignment: set `to_date`. `to_date = NULL` means "current".

### Employee exit / auto-deactivation
`Employee.exit_date` is the single source of truth for whether someone is still on
the books. Once it is **strictly before today**, the employee is auto-flagged
`status = inactive` and their open team memberships / project assignments are
closed as of the exit date (same cleanup as the Deactivate button).

- Logic lives in `app/services/employees.py`: `apply_employee_exit(db, emp, date)`
  (no commit; also used by `deactivate_employee`) and `sweep_exited_employees(db,
  today=None)` (idempotent, returns count).
- Runs **on app startup** (`lifespan` in `main.py`) and **once per calendar day**
  (a `@app.middleware("http")` with a module-level `_last_sweep` date guard — no
  scheduler, no schema column). It also runs **immediately** in `update_employee`
  when a past `exit_date` is saved via the edit form.
- **One-directional**: a future or cleared `exit_date` never re-activates anyone —
  `reactivate_employee` stays the only way back to `active` (it also clears
  `exit_date`). `exit_date == today` is deliberately left active (swept the next
  day) so it matches `cost_analysis._employed_on`, which keeps cost figures
  correct in the gap before a sweep runs.

### Cost Analysis
Employee salary, project income, and the org-wide GST rate are all **versioned
history** (`SalaryHistory`, `ProjectIncomeHistory`, `GstRateHistory`) — never
overwritten, a new row per change with an `effective_from` date. The "current"
value as of a date is the row with the latest `effective_from <= that date`. This
means **a rate change only affects periods from its effective date forward** —
past Lifetime figures are never retroactively rewritten. Submitting a change on a
date that already has a row **upserts** it (overwrites that date's value) rather
than erroring, for correcting typos.

`TDS` (`Project.tds_rate`) and `overhead` (`OrgSettings.monthly_overhead`) are
deliberately **NOT historical** — single current values. TDS rarely changes once
set for a client; overhead has no historical record at all, so tracking it would
fabricate precision that doesn't exist (this was the original decision before
history tracking existed for the other rates, and it still holds).

GST is a simple percentage of gross income (`gross * rate / 100`), subtracted from
gross along with TDS: `Net Income = gross − GST − TDS`. (A GST-inclusive
extraction, `rate / (100 + rate)`, was considered and rejected — the plain
percentage is the intended behavior.)

`app/services/cost_analysis.py` prorates everything with
`daily_rate = monthly_amount * 12 / 365` — one formula for both a 3-day and a
14-month overlap. A rate's full history is turned into non-overlapping
`(value, start, end)` segments (`_build_segments`) — the day before the next
entry's `effective_from` closes the previous segment; the latest entry stays
open-ended. Gross income is the plain prorated income total; **GST** is computed
separately by **crossing income segments against GST-rate segments**
(`_income_and_gst_to_date`, `amt * rate / 100`) since both can change
independently over time — see Bug 003 for a real gotcha this produced (two
open-ended segments). Gross does NOT depend on GST-rate history coverage.

Every figure returned by the public functions is passed through `_money()`
(quantize to 2 dp, `ROUND_HALF_UP`) so on-screen numbers add up exactly; internal
helpers keep full precision.

Two views exist, and they are **not** computed the same way:
- **Current snapshot** (dashboard stat, cost-analysis "This Month" section): no
  proration — a single point-in-time lookup (`_current_value`) for whatever is
  active *right now* (`status == active` projects; assignments that are
  `to_date IS NULL` **and** already started **and** whose employee passes
  `_employed_on`; employees that pass `_employed_on` — `status == active` and no
  past `exit_date`). Overhead is netted out here — this is the "overall profit or
  loss" number. Note the org-wide "Total Salary Cost" counts **all** such
  employees (incl. bench / unassigned), so it does not equal the sum of the
  per-project cost column.
- `exit_date` is authoritative everywhere salary is summed (`_employed_on` for the
  snapshot; assignment-window ∩ `[join_date, exit_date]` in `project_lifetime`;
  `period_end = min(exit_date, today)` in `org_lifetime`) — so it stays correct
  even if `exit_date` was set via the edit form rather than the Deactivate action.
- **Lifetime to date**: prorated by day since each project/employee actually
  started, correctly blending old and new rates across whatever segments
  applied when. Shown as **"gross margin to date" and deliberately excludes
  overhead** (see above). GST/TDS in this view DO correctly reflect historical
  rate changes (unlike overhead).

GST is **optional per project** — `Project.gst_applicable` (default true); when
false, GST is always 0 for that project regardless of the org-wide rate (for
GST-exempt clients, e.g. export/SEZ).

Missing salary/income (no history rows at all, no forced backfill) is treated as
0 everywhere in `cost_analysis.py`; the UI surfaces an "unset" notice instead of
silently hiding it.

Salary/income are **not** editable via the employee/project edit forms — only at
creation (first history row) and via dedicated `update-salary`/`update-income`
endpoints (mini-forms on the employee profile / project detail page, mirroring
the existing team/project assignment history UI pattern). This is intentional:
editing general info shouldn't silently rewrite financial history.

### Email Notifications
When an employee is assigned to a project (`assign_project` in `routers/employees.py`),
they get an email — **project assignment only**, recipient is the assigned employee
only, no CC.

- **Config** lives in the `OrgSettings` singleton (`smtp_*` / `email_*` columns,
  added by migration `e4a7c1b90d21`), edited by the admin on the **`/settings`** page
  (`routers/settings.py` + `templates/settings.html`). Nothing in env vars. The SMTP
  **password is stored plaintext** — single-user local-admin app, and `/db/export`
  copies the whole file, so a backup contains it. On `/settings/email`, a **blank
  password field keeps the stored password** (`save_smtp_config`).
- **Transport** is stdlib `smtplib` (no new dependency). `smtplib.SMTP_SSL` when
  `smtp_use_ssl`, else `smtplib.SMTP` + `starttls()` when `smtp_use_tls`.
- **Best-effort / fire-and-forget.** `notifications.send_email()` never raises and
  returns a bool; `assign_project` dispatches it via FastAPI `BackgroundTasks` *after*
  `db.commit()`. A broken/offline mail server only produces a logged
  `ops.notifications` exception — the assignment still succeeds. The success flash is
  optimistic; real delivery failures are log-only.
- **Master toggle**: `OrgSettings.email_enabled` (default false) — nothing is sent,
  and no connection attempted, unless it's on. Keeps bulk/historical data entry quiet.
- `SmtpConfig` (frozen dataclass of primitives) is read from the DB *before* the
  background task is queued, so the task never touches the closed session.
- `/settings` also has a **"send test email"** button (`POST /settings/email/test`) —
  sends synchronously and flashes the result, for SMTP setup.
- Email bodies: `templates/emails/project_assigned.{html,txt}` — standalone (they do
  **not** extend `base.html`), rendered via the shared Jinja env
  (`templates.env.get_template(...)`).

### Visual Analytics
`app/services/analytics.py` produces **chart-ready** data — it only *buckets*
`cost_analysis` figures by calendar month or by category and returns plain
JSON-safe primitives (`float`/`int`/`str`/`list`/`dict`). No `Decimal` or `date`
object ever leaves it (`_f()` runs every money value through
`cost_analysis._money` then `float()`).

- **Monthly series** reuse the cost-analysis proration engine
  (`_build_segments` + `_segment_total` + `_income_and_gst_to_date`) windowed to
  one calendar month, so a trend point reconciles with the **Lifetime** view —
  **not** the This-Month snapshot, which is an un-prorated run-rate (a 30/31-day
  month reads ~1–2% under the snapshot because of `*12/365`). Overhead is
  excluded from every trend/lifetime profit figure, same rule as
  "gross margin to date". `monthly_cost_trend` trims leading months that have no
  income and no salary at all.
- **No JSON API.** Every route hands its bundle to the template and the template
  embeds it with `{{ x | tojson }}` inside a `{% block scripts %}` — fully
  offline, no fetch, no Decimal-encoder plumbing. Routes touched:
  `/analytics` (new hub), `/` (`dash_charts`), `/cost-analysis` (`cost_charts`,
  reuses the page's already-built `rows`), employee profile (`salary_chart`,
  `reviews_chart`), project detail (`project_charts`).
- **Rendering**: Chart.js 4.4.4 UMD from jsDelivr CDN + `app/static/charts.js`
  (`window.Charts` — Chart.js defaults, palette mirrored from `style.css`
  `:root`, and `bar`/`line`/`doughnut` builders that safely no-op when their
  target `<canvas>` is absent, which is how the "no data yet" empty states
  work). `base.html` gained a `{% block scripts %}` before `</body>`.
- Doughnut "where gross income goes" cards clamp a negative profit slice to 0
  and print the real signed figure in a caption below.

### Tech Stack Normalization
Tech stack names are `.strip().title()` normalized on insert.  
Uniqueness check is case-insensitive (`.ilike(normalized)`).

### Shared Templates Instance
`app/templates_config.py` exports a single `Jinja2Templates` instance.  
All routers import from there. **Do not create a new `Jinja2Templates()` instance**  
in individual routers or main.py — it causes path resolution issues.

---

## Routing Conventions

| Prefix | Router file | Purpose |
|--------|-------------|---------|
| `/employees` | `routers/employees.py` | Employee CRUD, profile, assignments |
| `/teams` | `routers/teams.py` | Team CRUD, member list |
| `/projects` | `routers/projects.py` | Project CRUD, assignment list |
| `/reviews` | `routers/reviews.py` | Appreciation / escalation log |
| `/techstacks` | `routers/techstack.py` | Tech stack management |
| `/db` | `routers/db_transfer.py` | Import / Export SQLite file |
| `/cost-analysis` | `routers/cost_analysis.py` | Cost/profit analysis, overhead + GST rate settings |
| `/analytics` | `routers/analytics.py` | Visual analytics hub (Chart.js) |
| `/settings` | `routers/settings.py` | App settings — SMTP / email-notification config + test email |
| `/login`, `/logout`, `/` | `app/main.py` | Auth + dashboard |

### Route ordering gotcha (FastAPI/Starlette)
Parameterized routes like `/{employee_id}` will **not** shadow literal routes like `/new`
as long as `/new` is registered **before** `/{employee_id}` in the same router.  
FastAPI matches routes in registration order. Always define literal routes first.

---

## Template Conventions

- All templates extend `base.html`.
- Flash messages use `flash_success` / `flash_error` context keys (shown in `base.html`).
- `tech_added` query param is used to show a success notice after adding a tech stack
  from within the employee form (redirects back with `?tech_added=Name`).
- No nested `<form>` elements — ever. (See Bug 001.)

---

## Known Limitations / Future Work

- No pagination on employee list (low priority for small orgs).
- PyInstaller build not yet tested on a clean Windows machine (Phase 10 — pending real test).
- HTMX CDN loaded from internet — for fully offline deploy, bundle htmx.min.js in `static/`.
- Chart.js CDN (jsDelivr, pinned `4.4.4`) loaded on the chart pages — same offline
  gap. To close it: save `chart.umd.min.js` into `app/static/vendor/` and change
  the `<script src>` in the four `{% block scripts %}` to
  `{{ url_for('static', path='vendor/chart.umd.min.js') }}` (`build.spec` already
  bundles `app/static` wholesale).

---

## File Structure (Key Files)

```
employee-ops-system/
├── app/
│   ├── main.py              # FastAPI app, session middleware, dashboard, auth routes
│   ├── database.py          # Engine, SessionLocal, DB path resolution
│   ├── models.py            # All SQLAlchemy models (incl. OrgSettings)
│   ├── auth.py              # bcrypt hashing, session helpers, require_login
│   ├── templates_config.py  # Shared Jinja2Templates instance
│   ├── services/
│   │   ├── cost_analysis.py # Salary/income proration, snapshot & lifetime calcs
│   │   ├── analytics.py     # Chart-ready monthly/category aggregates (JSON-safe)
│   │   ├── employees.py     # Employee exit sweep
│   │   └── notifications.py # SMTP config (OrgSettings) + best-effort assignment email
│   ├── routers/
│   │   ├── employees.py     # Employee CRUD + profile + assignments
│   │   ├── teams.py         # Team CRUD
│   │   ├── projects.py      # Project CRUD
│   │   ├── reviews.py       # Review log
│   │   ├── techstack.py     # Tech stack management
│   │   ├── db_transfer.py   # Import/Export DB
│   │   ├── cost_analysis.py # Cost/profit analysis, overhead setting
│   │   ├── analytics.py     # /analytics chart hub
│   │   └── settings.py      # /settings — SMTP / email config + test email
│   ├── templates/           # Jinja2 HTML templates (analytics.html = chart hub)
│   │   └── emails/          # Standalone email bodies (project_assigned.html/.txt)
│   └── static/
│       ├── style.css        # Global stylesheet (+ .chart-grid/.chart-card)
│       └── charts.js        # Shared Chart.js helper (window.Charts)
├── alembic/                 # DB migrations
├── alembic.ini
├── seed_data.py             # Seed tech stacks + admin user (admin/changeme)
├── requirements.txt         # Pin bcrypt==4.0.1!
├── build.spec               # PyInstaller config
├── PROGRESS.md              # Phase-by-phase build tracker
└── CLAUDE.md                # This file
```
