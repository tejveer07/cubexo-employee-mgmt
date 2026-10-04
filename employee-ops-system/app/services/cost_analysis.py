"""
services/cost_analysis.py — Project & org-wide cost/profit calculations.

Salary, project income, and the org-wide GST rate are all **versioned history**
(SalaryHistory, ProjectIncomeHistory, GstRateHistory) — never overwritten, a new
row per change with an `effective_from` date. The "current" value as of a date is
the row with the latest `effective_from <= that date`. A rate change therefore
only affects periods from its effective date forward; past Lifetime figures are
never retroactively rewritten. TDS (per project) and overhead (org-wide) are
deliberately NOT historical — see the per-field notes below.

Two views, because salary/income/GST are all monthly-recurring concepts:
  - "Current snapshot": this month's run-rate using only currently active
    employees/projects/assignments, evaluated at a single point in time (today).
    No proration. Overhead is netted out here — this is the "overall profit or
    loss" figure.
  - "Lifetime": cumulative income/cost since each project/employee started,
    prorated by day over the actual historical duration, correctly blending
    old and new rates across whatever segments applied when. Shown as "gross
    margin to date" — overhead is NOT netted out here, because overhead has no
    historical record; backdating it would fabricate precision that doesn't exist.

An employee's `exit_date` is authoritative in both views (see `_employed_on`):
once it has passed, they add nothing to the current snapshot, and their lifetime
cost stops at the exit date — regardless of whether `status` was flipped or open
assignments were closed. A future `exit_date` still counts up to today only.

Proration formula: daily_rate = monthly_amount * 12 / 365. One formula covers
both a 3-day overlap and a 14-month overlap without splitting ranges into
per-calendar-month segments.

Tax deductions: Net Income = Gross Income − GST (if the project is GST-applicable)
− TDS. GST is a simple percentage of gross income (`gross * rate / 100`), computed
by crossing income segments against GST-rate segments (both can change
independently over time) so each sub-period is taxed at whatever rate actually
applied then. Gross income itself does NOT depend on GST-rate history coverage —
a period with income but no GST-rate row still contributes its full gross (just
0 GST). TDS is a single current per-project rate (not historical — a project's TDS
rate rarely changes, and if it does, the simpler retroactive behavior was
accepted as fine).

All figures returned by the public functions are quantized to 2 decimal places so
the numbers shown on screen add up exactly; the internal helpers keep full
precision.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app import models

DAYS_PER_YEAR = 365
FALLBACK_GST_RATE = Decimal("18")  # only used if gst_rate_history is somehow empty
_CENTS = Decimal("0.01")


def _money(value) -> Decimal:
    """Round a Decimal to 2 dp so displayed figures reconcile exactly."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _employed_on(employee, as_of: date) -> bool:
    """True if the employee is on payroll on ``as_of`` — active status AND no exit
    date yet (or one still in the future). Keeps ``exit_date`` authoritative even
    when ``status`` / open assignments were not kept in sync (e.g. an exit date
    set via the edit form instead of the Deactivate action)."""
    return (
        employee.status == models.EmployeeStatus.active
        and (employee.exit_date is None or employee.exit_date >= as_of)
    )


# ---------------------------------------------------------------------------
# Low-level date/segment math
# ---------------------------------------------------------------------------

def _daily_rate(monthly_amount) -> Decimal:
    if monthly_amount is None:
        return Decimal("0")
    return Decimal(monthly_amount) * 12 / DAYS_PER_YEAR


def _effective_window(range_start: date, range_end: date | None,
                       period_start: date, period_end: date | None):
    """Intersection of [range_start, range_end-or-open] and [period_start, period_end-or-open]
    as a (start, end) pair (end is None if BOTH inputs are open-ended), or None if they
    don't overlap. `period_end` may itself be None — this is reused to cross two
    segments that are each potentially open-ended (e.g. two "current, no end yet" rates)."""
    start = max(range_start, period_start)
    if range_end is None and period_end is None:
        end = None
    elif range_end is None:
        end = period_end
    elif period_end is None:
        end = range_end
    else:
        end = min(range_end, period_end)
    if end is not None and start > end:
        return None
    return start, end


def _overlap_days(range_start: date, range_end: date | None,
                   period_start: date, period_end: date) -> int:
    window = _effective_window(range_start, range_end, period_start, period_end)
    if window is None:
        return 0
    start, end = window
    return (end - start).days + 1


def _prorated_amount(monthly_amount, range_start: date, range_end: date | None,
                      period_start: date, period_end: date) -> Decimal:
    days = _overlap_days(range_start, range_end, period_start, period_end)
    return _daily_rate(monthly_amount) * days


def _build_segments(history_rows, value_attr: str):
    """Turn a list of {value_attr, effective_from} rows into sorted, non-overlapping
    (value, start_date, end_date_or_None) segments — each segment's end is the day
    before the next entry's effective_from; the last segment is open-ended."""
    rows = sorted(history_rows, key=lambda r: r.effective_from)
    segments = []
    for i, r in enumerate(rows):
        start = r.effective_from
        end = rows[i + 1].effective_from - timedelta(days=1) if i + 1 < len(rows) else None
        segments.append((Decimal(getattr(r, value_attr)), start, end))
    return segments


def _current_value(history_rows, as_of: date, value_attr: str):
    """The value effective as of a given date (latest effective_from <= as_of), or None."""
    candidates = [r for r in history_rows if r.effective_from <= as_of]
    if not candidates:
        return None
    latest = max(candidates, key=lambda r: r.effective_from)
    return Decimal(getattr(latest, value_attr))


def _segment_total(segments, period_start: date, period_end: date) -> Decimal:
    return sum(
        (_prorated_amount(rate, s, e, period_start, period_end) for rate, s, e in segments),
        Decimal("0"),
    )


def _income_and_gst_to_date(income_segments, gst_segments, gst_applicable: bool,
                             period_start: date, period_end: date):
    """Gross income and GST amount over a period, correctly blending changes in
    BOTH income and GST rate over time (they vary independently).

    Gross is the plain prorated income total and does NOT depend on GST-rate
    history coverage. GST is ``amt * rate / 100`` for each income-segment ×
    GST-rate-segment overlap."""
    gross = _segment_total(income_segments, period_start, period_end)
    if not gst_applicable:
        return gross, Decimal("0")

    gst = Decimal("0")
    for inc_rate, inc_s, inc_e in income_segments:
        for gst_rate, gst_s, gst_e in gst_segments:
            window = _effective_window(inc_s, inc_e, gst_s, gst_e)
            if window is None:
                continue
            days = _overlap_days(window[0], window[1], period_start, period_end)
            if days <= 0:
                continue
            amt = _daily_rate(inc_rate) * days
            gst += amt * gst_rate / 100
    return gross, gst


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------

@dataclass
class ProjectSnapshot:
    project_id: int
    gross_income: Decimal
    gst_amount: Decimal
    tds_amount: Decimal
    net_income: Decimal
    cost: Decimal
    profit: Decimal
    unset_employee_count: int


@dataclass
class ProjectLifetime:
    project_id: int
    gross_income_to_date: Decimal
    gst_amount_to_date: Decimal
    tds_amount_to_date: Decimal
    net_income_to_date: Decimal
    cost_to_date: Decimal
    profit_to_date: Decimal
    days_elapsed: int


@dataclass
class OrgSnapshot:
    total_gross_income: Decimal
    total_gst: Decimal
    total_tds: Decimal
    total_net_income: Decimal
    total_salary_cost: Decimal
    overhead: Decimal
    profit: Decimal


@dataclass
class OrgLifetime:
    total_gross_income_to_date: Decimal
    total_gst_to_date: Decimal
    total_tds_to_date: Decimal
    total_net_income_to_date: Decimal
    total_salary_paid_to_date: Decimal
    gross_margin_to_date: Decimal


# ---------------------------------------------------------------------------
# Project-level
# ---------------------------------------------------------------------------

def project_current_snapshot(db: Session, project: models.Project, as_of: date | None = None) -> ProjectSnapshot:
    as_of = as_of or date.today()
    zero = _money(0)
    if project.status != models.ProjectStatus.active:
        return ProjectSnapshot(project.id, zero, zero, zero, zero, zero, zero, 0)

    gross_income = _current_value(project.income_history, as_of, "monthly_income") or zero

    if project.gst_applicable:
        gst_rate = get_current_gst_rate(db, as_of)
        gst_amount = gross_income * gst_rate / 100
    else:
        gst_amount = zero

    tds_rate = Decimal(project.tds_rate) if project.tds_rate is not None else zero
    tds_amount = gross_income * tds_rate / 100
    net_income = gross_income - gst_amount - tds_amount

    active_assignments = [
        a for a in project.assignments
        if a.to_date is None
        and a.from_date <= as_of
        and _employed_on(a.employee, as_of)
    ]
    cost = zero
    unset_count = 0
    for a in active_assignments:
        salary = _current_value(a.employee.salary_history, as_of, "monthly_salary")
        if salary is None:
            unset_count += 1
            continue
        cost += salary

    net_income = _money(net_income)
    cost = _money(cost)
    return ProjectSnapshot(project.id, _money(gross_income), _money(gst_amount),
                            _money(tds_amount), net_income, cost,
                            _money(net_income - cost), unset_count)


def project_lifetime(db: Session, project: models.Project, as_of: date | None = None) -> ProjectLifetime:
    as_of = as_of or date.today()
    period_start = project.start_date
    period_end = project.end_date or as_of

    income_segments = _build_segments(project.income_history, "monthly_income")
    gst_segments = _build_segments(db.query(models.GstRateHistory).all(), "gst_rate")
    gross_income_to_date, gst_amount_to_date = _income_and_gst_to_date(
        income_segments, gst_segments, project.gst_applicable, period_start, period_end,
    )

    tds_rate = Decimal(project.tds_rate) if project.tds_rate is not None else Decimal("0")
    tds_amount_to_date = gross_income_to_date * tds_rate / 100
    net_income_to_date = gross_income_to_date - gst_amount_to_date - tds_amount_to_date

    cost_to_date = Decimal("0")
    for a in project.assignments:
        emp = a.employee
        # assignment window ∩ employment window ([join_date, exit_date]) — so a
        # departed employee's salary stops at their exit even if the assignment
        # was never closed.
        emp_window = _effective_window(a.from_date, a.to_date, emp.join_date, emp.exit_date)
        if emp_window is None:
            continue
        window = _effective_window(emp_window[0], emp_window[1], period_start, period_end)
        if window is None:
            continue
        salary_segments = _build_segments(emp.salary_history, "monthly_salary")
        cost_to_date += _segment_total(salary_segments, window[0], window[1])

    days_elapsed = (period_end - period_start).days + 1
    net_income_to_date = _money(net_income_to_date)
    cost_to_date = _money(cost_to_date)
    return ProjectLifetime(project.id, _money(gross_income_to_date), _money(gst_amount_to_date),
                            _money(tds_amount_to_date), net_income_to_date, cost_to_date,
                            _money(net_income_to_date - cost_to_date), days_elapsed)


# ---------------------------------------------------------------------------
# Org-wide
# ---------------------------------------------------------------------------

def org_current_snapshot(db: Session, as_of: date | None = None) -> OrgSnapshot:
    as_of = as_of or date.today()
    zero = Decimal("0")

    total_gross = total_gst = total_tds = total_net = zero
    for p in db.query(models.Project).filter_by(status=models.ProjectStatus.active).all():
        snap = project_current_snapshot(db, p, as_of)
        total_gross += snap.gross_income
        total_gst += snap.gst_amount
        total_tds += snap.tds_amount
        total_net += snap.net_income

    total_salary_cost = zero
    for e in db.query(models.Employee).filter_by(status=models.EmployeeStatus.active).all():
        if not _employed_on(e, as_of):  # past-dated exit but status still active
            continue
        salary = _current_value(e.salary_history, as_of, "monthly_salary")
        if salary is not None:
            total_salary_cost += salary

    overhead = _money(get_overhead(db))
    total_net = _money(total_net)
    total_salary_cost = _money(total_salary_cost)
    profit = _money(total_net - total_salary_cost - overhead)
    return OrgSnapshot(_money(total_gross), _money(total_gst), _money(total_tds),
                        total_net, total_salary_cost, overhead, profit)


def org_lifetime(db: Session, as_of: date | None = None) -> OrgLifetime:
    as_of = as_of or date.today()
    zero = Decimal("0")

    total_gross = total_gst = total_tds = total_net = zero
    for p in db.query(models.Project).all():
        life = project_lifetime(db, p, as_of)
        total_gross += life.gross_income_to_date
        total_gst += life.gst_amount_to_date
        total_tds += life.tds_amount_to_date
        total_net += life.net_income_to_date

    total_salary_paid = zero
    for e in db.query(models.Employee).all():
        # cap at today — a future exit_date must not project salary past "to date"
        period_end = min(e.exit_date, as_of) if e.exit_date else as_of
        salary_segments = _build_segments(e.salary_history, "monthly_salary")
        total_salary_paid += _segment_total(salary_segments, e.join_date, period_end)

    total_net = _money(total_net)
    total_salary_paid = _money(total_salary_paid)
    return OrgLifetime(_money(total_gross), _money(total_gst), _money(total_tds), total_net,
                        total_salary_paid, _money(total_net - total_salary_paid))


# ---------------------------------------------------------------------------
# Overhead (org-wide, single current value — no history, see module docstring)
# ---------------------------------------------------------------------------

def get_overhead(db: Session) -> Decimal:
    settings = db.query(models.OrgSettings).filter_by(id=1).first()
    return Decimal(settings.monthly_overhead) if settings else Decimal("0")


def set_overhead(db: Session, value: Decimal) -> models.OrgSettings:
    settings = db.query(models.OrgSettings).filter_by(id=1).first()
    if settings is None:
        settings = models.OrgSettings(id=1, monthly_overhead=value)
        db.add(settings)
    else:
        settings.monthly_overhead = value
    settings.updated_at = date.today()
    db.commit()
    return settings


# ---------------------------------------------------------------------------
# GST rate history (org-wide)
# ---------------------------------------------------------------------------

def get_current_gst_rate(db: Session, as_of: date | None = None) -> Decimal:
    as_of = as_of or date.today()
    rate = _current_value(db.query(models.GstRateHistory).all(), as_of, "gst_rate")
    return rate if rate is not None else FALLBACK_GST_RATE


def record_gst_rate_change(db: Session, gst_rate: Decimal, effective_from: date) -> models.GstRateHistory:
    existing = db.query(models.GstRateHistory).filter_by(effective_from=effective_from).first()
    if existing:
        existing.gst_rate = gst_rate
    else:
        existing = models.GstRateHistory(gst_rate=gst_rate, effective_from=effective_from)
        db.add(existing)
    db.commit()
    return existing


# ---------------------------------------------------------------------------
# Salary / project income history (upsert-by-effective_from)
# ---------------------------------------------------------------------------

def record_salary_change(db: Session, employee_id: int, monthly_salary: Decimal, effective_from: date) -> models.SalaryHistory:
    existing = db.query(models.SalaryHistory).filter_by(employee_id=employee_id, effective_from=effective_from).first()
    if existing:
        existing.monthly_salary = monthly_salary
    else:
        existing = models.SalaryHistory(employee_id=employee_id, monthly_salary=monthly_salary, effective_from=effective_from)
        db.add(existing)
    db.commit()
    return existing


def record_income_change(db: Session, project_id: int, monthly_income: Decimal, effective_from: date) -> models.ProjectIncomeHistory:
    existing = db.query(models.ProjectIncomeHistory).filter_by(project_id=project_id, effective_from=effective_from).first()
    if existing:
        existing.monthly_income = monthly_income
    else:
        existing = models.ProjectIncomeHistory(project_id=project_id, monthly_income=monthly_income, effective_from=effective_from)
        db.add(existing)
    db.commit()
    return existing
