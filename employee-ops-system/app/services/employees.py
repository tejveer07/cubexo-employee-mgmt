"""services/employees.py — employee lifecycle helpers shared by the routes and
the startup / once-daily auto-deactivate sweep.

An employee's `exit_date` is the single source of truth for whether they are still
on the books. Once it is strictly in the past, they should be `inactive` and their
open team memberships / project assignments closed as of that date — the same
cleanup the Deactivate button performs. `cost_analysis._employed_on` already keeps
cost figures correct in the gap between the exit date passing and the sweep
running; this module makes the stored `status` catch up.
"""

from datetime import date

from sqlalchemy.orm import Session

from app import models


def apply_employee_exit(db: Session, emp: models.Employee, exit_date: date) -> None:
    """Mark `emp` as departed and close their open memberships / assignments as of
    `exit_date`. Does NOT commit — the caller owns the transaction. Mirrors
    `routers.employees.deactivate_employee`."""
    emp.status = models.EmployeeStatus.inactive
    emp.exit_date = exit_date
    db.query(models.TeamMembership).filter_by(
        employee_id=emp.id, to_date=None
    ).update({"to_date": exit_date})
    db.query(models.EmployeeProjectAssignment).filter_by(
        employee_id=emp.id, to_date=None
    ).update({"to_date": exit_date})


def sweep_exited_employees(db: Session, today: date | None = None) -> int:
    """Deactivate every still-active employee whose `exit_date` is strictly before
    `today`, closing their open memberships / assignments. Returns the number of
    employees changed.

    Idempotent — already-inactive rows are excluded by the status filter.
    One-directional: a future or cleared `exit_date` never re-activates anyone
    (that stays the manual Reactivate action). `exit_date == today` is left alone
    so it matches `cost_analysis._employed_on`; it is swept the next day.
    """
    today = today or date.today()
    stale = (
        db.query(models.Employee)
        .filter(
            models.Employee.status == models.EmployeeStatus.active,
            models.Employee.exit_date.isnot(None),
            models.Employee.exit_date < today,
        )
        .all()
    )
    for emp in stale:
        apply_employee_exit(db, emp, emp.exit_date)
    if stale:
        db.commit()
    return len(stale)
