"""
models.py — All SQLAlchemy ORM models.

Tables:
  employees, teams, team_memberships, projects,
  employee_project_assignments, tech_stacks, employee_tech_stacks,
  reviews, admin_users, org_settings, salary_history,
  project_income_history, gst_rate_history
"""

import enum
from datetime import date

from sqlalchemy import (
    Column, Integer, String, Date, Enum, Text, ForeignKey, UniqueConstraint, Numeric, Boolean,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EmployeeStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class ProjectStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    on_hold = "on_hold"


class ReviewType(str, enum.Enum):
    appreciation = "appreciation"
    escalation = "escalation"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    employee_code = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False)
    designation = Column(String, nullable=False)
    join_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=True)
    team_lead_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    status = Column(Enum(EmployeeStatus), nullable=False, default=EmployeeStatus.active)

    # Relationships
    team_lead = relationship("Employee", remote_side="Employee.id", foreign_keys=[team_lead_id])
    subordinates = relationship("Employee", foreign_keys=[team_lead_id], back_populates="team_lead")

    team_memberships = relationship("TeamMembership", back_populates="employee", foreign_keys="TeamMembership.employee_id")
    project_assignments = relationship("EmployeeProjectAssignment", back_populates="employee", foreign_keys="EmployeeProjectAssignment.employee_id")
    tech_stacks = relationship("EmployeeTechStack", back_populates="employee")
    salary_history = relationship("SalaryHistory", back_populates="employee")

    reviews_received = relationship("Review", back_populates="employee", foreign_keys="Review.employee_id")
    reviews_given = relationship("Review", back_populates="reviewer", foreign_keys="Review.reviewer_id")

    # Teams where this employee is the lead
    led_teams = relationship("Team", back_populates="team_lead", foreign_keys="Team.team_lead_id")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    team_lead_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    team_lead = relationship("Employee", back_populates="led_teams", foreign_keys=[team_lead_id])
    memberships = relationship("TeamMembership", back_populates="team")


class TeamMembership(Base):
    """Historical record of which employee belonged to which team and when."""
    __tablename__ = "team_memberships"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=True)  # NULL = current membership

    employee = relationship("Employee", back_populates="team_memberships", foreign_keys=[employee_id])
    team = relationship("Team", back_populates="memberships")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    client = Column(String, nullable=False)
    status = Column(Enum(ProjectStatus), nullable=False, default=ProjectStatus.active)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    tds_rate = Column(Numeric(5, 2), nullable=True)  # percent, e.g. 10.00 — single current value, no history
    gst_applicable = Column(Boolean, nullable=False, default=True)

    assignments = relationship("EmployeeProjectAssignment", back_populates="project")
    income_history = relationship("ProjectIncomeHistory", back_populates="project")


class EmployeeProjectAssignment(Base):
    """Historical record of which employee worked on which project and when."""
    __tablename__ = "employee_project_assignments"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role_on_project = Column(String, nullable=False)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=True)  # NULL = ongoing

    employee = relationship("Employee", back_populates="project_assignments", foreign_keys=[employee_id])
    project = relationship("Project", back_populates="assignments")


class TechStack(Base):
    __tablename__ = "tech_stacks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    employees = relationship("EmployeeTechStack", back_populates="tech_stack")


class EmployeeTechStack(Base):
    """Many-to-many: Employee <-> TechStack."""
    __tablename__ = "employee_tech_stacks"

    employee_id = Column(Integer, ForeignKey("employees.id"), primary_key=True)
    tech_stack_id = Column(Integer, ForeignKey("tech_stacks.id"), primary_key=True)

    employee = relationship("Employee", back_populates="tech_stacks")
    tech_stack = relationship("TechStack", back_populates="employees")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    type = Column(Enum(ReviewType), nullable=False)
    date = Column(Date, nullable=False)
    notes = Column(Text, nullable=False)

    employee = relationship("Employee", back_populates="reviews_received", foreign_keys=[employee_id])
    reviewer = relationship("Employee", back_populates="reviews_given", foreign_keys=[reviewer_id])


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)


class OrgSettings(Base):
    """Singleton row (id=1) holding org-wide settings.

    Two unrelated groups of settings live here:
      - `monthly_overhead` — admin/management overhead. Deliberately has no history:
        a single current figure, netted out only in the "This Month" cost-analysis
        view, never the Lifetime view. See app/services/cost_analysis.py.
      - `smtp_*` / `email_*` — outbound email (SMTP) config for the assignment
        notification feature, edited by the admin on the /settings page. The SMTP
        password is stored as plaintext (single-user, local-admin app; note that
        /db/export copies the whole DB file). See app/services/notifications.py.
    """
    __tablename__ = "org_settings"

    id = Column(Integer, primary_key=True)
    monthly_overhead = Column(Numeric(12, 2), nullable=False, default=0)
    updated_at = Column(Date, nullable=True)

    # Outbound email (SMTP) — see app/services/notifications.py
    smtp_host = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True)  # treated as 587 when NULL
    smtp_username = Column(String, nullable=True)
    smtp_password = Column(String, nullable=True)  # plaintext
    smtp_use_tls = Column(Boolean, nullable=False, default=True, server_default="1")   # STARTTLS
    smtp_use_ssl = Column(Boolean, nullable=False, default=False, server_default="0")  # implicit TLS (port 465)
    email_from = Column(String, nullable=True)       # falls back to smtp_username
    email_from_name = Column(String, nullable=True)  # falls back to "CubexO Operations"
    email_enabled = Column(Boolean, nullable=False, default=False, server_default="0")


class SalaryHistory(Base):
    """Versioned employee salary — never overwritten, a new row per rate change.
    The "current" rate is the row with the latest effective_from <= today.
    See app/services/cost_analysis.py for how segments are derived and prorated.
    """
    __tablename__ = "salary_history"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    monthly_salary = Column(Numeric(12, 2), nullable=False)
    effective_from = Column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("employee_id", "effective_from"),)

    employee = relationship("Employee", back_populates="salary_history")


class ProjectIncomeHistory(Base):
    """Versioned project income — same pattern as SalaryHistory."""
    __tablename__ = "project_income_history"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    monthly_income = Column(Numeric(12, 2), nullable=False)
    effective_from = Column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "effective_from"),)

    project = relationship("Project", back_populates="income_history")


class GstRateHistory(Base):
    """Versioned org-wide GST rate — same pattern as SalaryHistory, so a rate
    change only affects months from its effective date forward.
    """
    __tablename__ = "gst_rate_history"

    id = Column(Integer, primary_key=True, index=True)
    gst_rate = Column(Numeric(5, 2), nullable=False)  # percent, e.g. 18.00
    effective_from = Column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("effective_from"),)
