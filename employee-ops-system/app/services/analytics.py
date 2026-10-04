"""
services/analytics.py — chart-ready aggregates for the /analytics page and the
chart sections on the dashboard, cost-analysis, employee-profile and
project-detail pages.

Every function returns plain JSON-serialisable primitives (float / int / str /
list / dict) so a template can embed the result with Jinja's ``| tojson`` filter
and hand it straight to Chart.js. No ``Decimal`` and no ``date`` object ever
leaves this module.

All money math is delegated to ``app.services.cost_analysis`` — this module only
*buckets* those figures by calendar month or by category. Monthly figures reuse
the same day-proration engine as the cost-analysis "Lifetime" view
(``daily_rate = monthly_amount * 12 / 365``) windowed to a single month, so a
point on a monthly trend line reconciles with the Lifetime totals on the
cost-analysis page. Overhead is excluded from every monthly / lifetime profit
figure here for the same reason it is excluded from "gross margin to date" — it
has no history.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.services import cost_analysis as ca
from app.services.cost_analysis import (
    _build_segments,
    _effective_window,
    _income_and_gst_to_date,
    _segment_total,
)

MONTHS_DEFAULT = 24


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def _f(value) -> float:
    """Quantise to 2 dp (via cost_analysis._money) then cast to float for JSON."""
    if value is None:
        return 0.0
    return float(ca._money(value))


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, nxt - timedelta(days=1)


def _month_labels(months: int) -> list[tuple[str, date, date]]:
    """The last ``months`` calendar months as (``"YYYY-MM"``, start, end),
    oldest first, ending with the current month."""
    today = date.today()
    y, m = today.year, today.month
    out: list[tuple[str, date, date]] = []
    for _ in range(max(months, 1)):
        s, e = _month_bounds(y, m)
        out.append((f"{y:04d}-{m:02d}", s, e))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    out.reverse()
    return out


def _earliest_data_date(db: Session) -> date | None:
    candidates: list[date] = []
    for col in (
        models.SalaryHistory.effective_from,
        models.ProjectIncomeHistory.effective_from,
        models.Employee.join_date,
        models.Project.start_date,
    ):
        row = db.query(col).order_by(col.asc()).first()
        if row and row[0] is not None:
            candidates.append(row[0])
    return min(candidates) if candidates else None


def _month_range(db: Session, months: int) -> list[tuple[str, date, date]]:
    """`_month_labels` trimmed to months that actually contain or follow the
    earliest piece of data — so an empty DB yields [] and a young org isn't
    padded with a year of flat-zero months."""
    labels = _month_labels(months)
    earliest = _earliest_data_date(db)
    if earliest is None:
        return []
    trimmed = [t for t in labels if t[2] >= earliest]
    return trimmed or labels[-1:]


# ---------------------------------------------------------------------------
# Cost / finance time series
# ---------------------------------------------------------------------------

def monthly_cost_trend(db: Session, months: int = MONTHS_DEFAULT) -> list[dict]:
    """Per calendar month: prorated gross income, GST, TDS, net income, salary
    cost (every on-record employee, bench included — matches org_lifetime), and
    gross-margin profit (net − salary, overhead excluded)."""
    period = _month_range(db, months)
    if not period:
        return []

    projects = db.query(models.Project).all()
    employees = db.query(models.Employee).all()
    gst_segments = _build_segments(db.query(models.GstRateHistory).all(), "gst_rate")
    proj_income = {p.id: _build_segments(p.income_history, "monthly_income") for p in projects}
    emp_salary = {e.id: _build_segments(e.salary_history, "monthly_salary") for e in employees}

    out: list[dict] = []
    for label, m_start, m_end in period:
        gross = gst = tds = Decimal("0")
        for p in projects:
            win = _effective_window(p.start_date, p.end_date, m_start, m_end)
            if win is None:
                continue
            g, x = _income_and_gst_to_date(
                proj_income[p.id], gst_segments, p.gst_applicable, win[0], win[1] or m_end,
            )
            gross += g
            gst += x
            if p.tds_rate is not None:
                tds += g * Decimal(p.tds_rate) / 100
        net = gross - gst - tds

        salary = Decimal("0")
        for e in employees:
            ew = _effective_window(e.join_date, e.exit_date, m_start, m_end)
            if ew is None:
                continue
            salary += _segment_total(emp_salary[e.id], ew[0], ew[1] or m_end)

        out.append({
            "month": label,
            "gross_income": _f(gross),
            "gst": _f(gst),
            "tds": _f(tds),
            "net_income": _f(net),
            "salary_cost": _f(salary),
            "profit": _f(net - salary),
        })

    # Drop leading months with no financial activity at all — the org may have
    # employees/projects on record before any salary/income was ever entered,
    # and a run of flat-zero points just adds noise to the line.
    first_active = next(
        (i for i, r in enumerate(out) if r["gross_income"] or r["salary_cost"]),
        len(out) - 1,
    )
    return out[first_active:]


def org_composition(db: Session) -> dict:
    """This-month and lifetime money composition, for the doughnut/stacked-bar
    breakdowns. Straight passthrough of org_current_snapshot / org_lifetime."""
    snap = ca.org_current_snapshot(db)
    life = ca.org_lifetime(db)
    return {
        "this_month": {
            "gross": _f(snap.total_gross_income),
            "gst": _f(snap.total_gst),
            "tds": _f(snap.total_tds),
            "salary": _f(snap.total_salary_cost),
            "overhead": _f(snap.overhead),
            "profit": _f(snap.profit),
        },
        "lifetime": {
            "gross": _f(life.total_gross_income_to_date),
            "gst": _f(life.total_gst_to_date),
            "tds": _f(life.total_tds_to_date),
            "salary": _f(life.total_salary_paid_to_date),
            "margin": _f(life.gross_margin_to_date),
        },
    }


def per_project_pl(db: Session, rows: list[dict] | None = None) -> list[dict]:
    """Per-project net income / cost / profit, this-month and lifetime.

    ``rows`` may be the list the cost-analysis router already assembled
    (``{"project", "snapshot", "lifetime"}``) to avoid recomputing
    project_lifetime; otherwise it is built here."""
    if rows is None:
        projects = db.query(models.Project).order_by(models.Project.name).all()
        rows = [
            {
                "project": p,
                "snapshot": ca.project_current_snapshot(db, p),
                "lifetime": ca.project_lifetime(db, p),
            }
            for p in projects
        ]
    out: list[dict] = []
    for r in rows:
        p, s, l = r["project"], r["snapshot"], r["lifetime"]
        out.append({
            "name": p.name,
            "status": p.status.value,
            "this_month_net": _f(s.net_income),
            "this_month_cost": _f(s.cost),
            "this_month_profit": _f(s.profit),
            "lifetime_net": _f(l.net_income_to_date),
            "lifetime_cost": _f(l.cost_to_date),
            "lifetime_margin": _f(l.profit_to_date),
        })
    return out


def margin_ranking(db: Session, rows: list[dict] | None = None) -> list[dict]:
    """per_project_pl sorted by lifetime gross margin, best first."""
    return sorted(per_project_pl(db, rows), key=lambda d: d["lifetime_margin"], reverse=True)


# ---------------------------------------------------------------------------
# People time series & breakdowns
# ---------------------------------------------------------------------------

def monthly_headcount_trend(db: Session, months: int = MONTHS_DEFAULT) -> list[dict]:
    """Per month: active headcount at month end, plus joiners and leavers in
    the month (from join_date / exit_date)."""
    period = _month_range(db, months)
    if not period:
        return []
    emps = db.query(models.Employee).all()
    out: list[dict] = []
    for label, m_start, m_end in period:
        headcount = sum(
            1 for e in emps
            if e.join_date <= m_end and (e.exit_date is None or e.exit_date > m_end)
        )
        joiners = sum(1 for e in emps if m_start <= e.join_date <= m_end)
        leavers = sum(1 for e in emps if e.exit_date and m_start <= e.exit_date <= m_end)
        out.append({"month": label, "headcount": headcount, "joiners": joiners, "leavers": leavers})
    return out


def _as_count_list(counter: dict[str, int]) -> list[dict]:
    return [
        {"label": k, "count": v}
        for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def headcount_by_dimension(db: Session) -> dict:
    """Current active workforce split by team (current membership), designation,
    and tech stack (an employee counts once per tech they hold)."""
    emps = db.query(models.Employee).filter_by(status=models.EmployeeStatus.active).all()

    by_team: dict[str, int] = {}
    by_designation: dict[str, int] = {}
    by_tech: dict[str, int] = {}
    for e in emps:
        current = [m for m in e.team_memberships if m.to_date is None]
        if current:
            for m in current:
                name = m.team.name if m.team else "Unknown"
                by_team[name] = by_team.get(name, 0) + 1
        else:
            by_team["No team"] = by_team.get("No team", 0) + 1

        by_designation[e.designation] = by_designation.get(e.designation, 0) + 1

        for et in e.tech_stacks:
            name = et.tech_stack.name if et.tech_stack else "Unknown"
            by_tech[name] = by_tech.get(name, 0) + 1

    return {
        "by_team": _as_count_list(by_team),
        "by_designation": _as_count_list(by_designation),
        "by_tech_stack": _as_count_list(by_tech),
    }


def project_allocation(db: Session) -> dict:
    """Active employees on >=1 open assignment vs on the bench, plus open
    headcount per active project."""
    emps = db.query(models.Employee).filter_by(status=models.EmployeeStatus.active).all()
    assigned = sum(1 for e in emps if any(a.to_date is None for a in e.project_assignments))
    bench = len(emps) - assigned

    per_project: list[dict] = []
    projects = (
        db.query(models.Project)
        .filter_by(status=models.ProjectStatus.active)
        .order_by(models.Project.name)
        .all()
    )
    for p in projects:
        cnt = sum(
            1 for a in p.assignments
            if a.to_date is None and a.employee is not None
            and a.employee.status == models.EmployeeStatus.active
        )
        per_project.append({"label": p.name, "count": cnt})
    per_project.sort(key=lambda x: (-x["count"], x["label"]))
    return {"assigned": assigned, "bench": bench, "per_project": per_project}


def reviews_trend(db: Session, months: int = MONTHS_DEFAULT) -> list[dict]:
    """Appreciation vs escalation counts per month."""
    period = _month_range(db, months)
    if not period:
        return []
    reviews = db.query(models.Review).all()
    out: list[dict] = []
    for label, m_start, m_end in period:
        appr = sum(
            1 for r in reviews
            if r.type == models.ReviewType.appreciation and m_start <= r.date <= m_end
        )
        esc = sum(
            1 for r in reviews
            if r.type == models.ReviewType.escalation and m_start <= r.date <= m_end
        )
        out.append({"month": label, "appreciation": appr, "escalation": esc})
    return out


# ---------------------------------------------------------------------------
# Per-entity series (employee profile / project detail)
# ---------------------------------------------------------------------------

def employee_salary_series(emp: models.Employee) -> list[dict]:
    """Step line of monthly salary vs effective_from."""
    rows = sorted(emp.salary_history, key=lambda r: r.effective_from)
    return [
        {"date": r.effective_from.isoformat(), "salary": _f(r.monthly_salary)}
        for r in rows
    ]


def employee_reviews_series(emp: models.Employee, months: int = MONTHS_DEFAULT) -> list[dict]:
    """Appreciation vs escalation per month for one employee."""
    received = list(emp.reviews_received)
    if not received:
        return []
    earliest = min(r.date for r in received)
    period = [t for t in _month_labels(months) if t[2] >= earliest] or _month_labels(1)
    out: list[dict] = []
    for label, m_start, m_end in period:
        appr = sum(
            1 for r in received
            if r.type == models.ReviewType.appreciation and m_start <= r.date <= m_end
        )
        esc = sum(
            1 for r in received
            if r.type == models.ReviewType.escalation and m_start <= r.date <= m_end
        )
        out.append({"month": label, "appreciation": appr, "escalation": esc})
    return out


def project_charts(db: Session, project: models.Project, months: int = MONTHS_DEFAULT) -> dict:
    """Income step line + monthly P/L line + assigned-headcount line for one
    project. Monthly P/L uses the same windowed proration as
    monthly_cost_trend, so its latest point tracks the this-month snapshot."""
    income_series = [
        {"date": r.effective_from.isoformat(), "income": _f(r.monthly_income)}
        for r in sorted(project.income_history, key=lambda r: r.effective_from)
    ]

    period = [t for t in _month_labels(months) if t[2] >= project.start_date] or _month_labels(1)
    gst_segments = _build_segments(db.query(models.GstRateHistory).all(), "gst_rate")
    inc_segments = _build_segments(project.income_history, "monthly_income")
    salary_cache: dict[int, list] = {}

    monthly_pl: list[dict] = []
    headcount_series: list[dict] = []
    for label, m_start, m_end in period:
        win = _effective_window(project.start_date, project.end_date, m_start, m_end)
        if win is None:
            monthly_pl.append({"month": label, "net_income": 0.0, "cost": 0.0, "profit": 0.0})
            headcount_series.append({"month": label, "headcount": 0})
            continue

        g, x = _income_and_gst_to_date(
            inc_segments, gst_segments, project.gst_applicable, win[0], win[1] or m_end,
        )
        tds = g * Decimal(project.tds_rate) / 100 if project.tds_rate is not None else Decimal("0")
        net = g - x - tds

        cost = Decimal("0")
        hc = 0
        for a in project.assignments:
            emp = a.employee
            if emp is None:
                continue
            aw = _effective_window(a.from_date, a.to_date, emp.join_date, emp.exit_date)
            if aw is None:
                continue
            aw = _effective_window(aw[0], aw[1], m_start, m_end)
            if aw is None:
                continue
            hc += 1
            if emp.id not in salary_cache:
                salary_cache[emp.id] = _build_segments(emp.salary_history, "monthly_salary")
            cost += _segment_total(salary_cache[emp.id], aw[0], aw[1] or m_end)

        monthly_pl.append({
            "month": label,
            "net_income": _f(net),
            "cost": _f(cost),
            "profit": _f(net - cost),
        })
        headcount_series.append({"month": label, "headcount": hc})

    return {
        "income_series": income_series,
        "monthly_pl": monthly_pl,
        "headcount_series": headcount_series,
    }


# ---------------------------------------------------------------------------
# Bundles consumed by the routes
# ---------------------------------------------------------------------------

def analytics_bundle(db: Session) -> dict:
    """Everything the /analytics page needs, in one call."""
    return {
        "cost_trend": monthly_cost_trend(db),
        "headcount_trend": monthly_headcount_trend(db),
        "headcount_by": headcount_by_dimension(db),
        "allocation": project_allocation(db),
        "reviews_trend": reviews_trend(db),
        "per_project_pl": per_project_pl(db),
        "margin_ranking": margin_ranking(db),
        "composition": org_composition(db),
    }


def cost_charts_from_rows(db: Session, rows: list[dict]) -> dict:
    """Chart data for the cost-analysis page, reusing its already-built rows."""
    return {
        "cost_trend": monthly_cost_trend(db),
        "per_project_pl": per_project_pl(db, rows),
        "margin_ranking": margin_ranking(db, rows),
        "composition": org_composition(db),
    }


def dashboard_charts(db: Session) -> dict:
    """Two compact charts for the dashboard home."""
    return {
        "headcount_trend": monthly_headcount_trend(db, months=12),
        "composition": org_composition(db),
    }
