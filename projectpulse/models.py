"""SQLAlchemy ORM models.

These mirror ``sql/01_schema.sql`` exactly. The SQL file is the canonical DDL
for PostgreSQL; the ORM models let the loader build the same schema on the
SQLite fallback and give the codebase typed table definitions.

Columns beyond the original brief are marked ``# ext`` - they make the data
behave like a real Jira export (sprint membership, issue type, work start
dates, risk lifecycle dates) and are what make cycle time, burndown and risk
trends computable.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    employee_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(60), nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    weekly_capacity_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("weekly_capacity_hours BETWEEN 1 AND 60", name="ck_emp_capacity"),
    )


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(200))  # ext
    project_manager_id: Mapped[int] = mapped_column(
        ForeignKey("employees.employee_id"), nullable=False
    )
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    actual_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)

    __table_args__ = (
        CheckConstraint("planned_end_date > start_date", name="ck_proj_dates"),
        CheckConstraint("budget > 0", name="ck_proj_budget"),
        CheckConstraint(
            "status IN ('On Track','At Risk','Delayed','Completed','On Hold')",
            name="ck_proj_status",
        ),
        CheckConstraint(
            "priority IN ('Critical','High','Medium','Low')", name="ck_proj_priority"
        ),
    )


class Sprint(Base):
    __tablename__ = "sprints"

    sprint_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sprint_name: Mapped[str | None] = mapped_column(String(60))  # ext
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # ext: Closed / Active
    planned_story_points: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_story_points: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("end_date > start_date", name="ck_sprint_dates"),
        CheckConstraint("completed_story_points >= 0", name="ck_sprint_sp"),
        UniqueConstraint("project_id", "sprint_number", name="uq_sprint_number"),
    )


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_key: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)  # ext
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("sprints.sprint_id", ondelete="SET NULL"), index=True
    )  # ext
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.employee_id"), index=True
    )
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(10), nullable=False)  # ext
    story_points: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_hours: Mapped[float] = mapped_column(Numeric(7, 1), nullable=False)
    actual_hours: Mapped[float | None] = mapped_column(Numeric(7, 1))
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    created_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_date: Mapped[date | None] = mapped_column(Date)  # ext
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    completion_date: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint("story_points IN (1,2,3,5,8,13)", name="ck_task_sp"),
        CheckConstraint(
            "status IN ('To Do','In Progress','In Review','Blocked','Done')",
            name="ck_task_status",
        ),
        CheckConstraint(
            "completion_date IS NULL OR completion_date >= created_date",
            name="ck_task_completion",
        ),
    )


class Risk(Base):
    __tablename__ = "risks"

    risk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # ext
    risk_description: Mapped[str] = mapped_column(Text, nullable=False)
    probability: Mapped[int] = mapped_column(Integer, nullable=False)
    impact: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("employees.employee_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    identified_date: Mapped[date] = mapped_column(Date, nullable=False)  # ext
    resolved_date: Mapped[date | None] = mapped_column(Date)  # ext
    mitigation_progress: Mapped[int] = mapped_column(Integer, nullable=False)  # ext, 0-100

    __table_args__ = (
        CheckConstraint("probability BETWEEN 1 AND 5", name="ck_risk_prob"),
        CheckConstraint("impact BETWEEN 1 AND 5", name="ck_risk_impact"),
        CheckConstraint("risk_score = probability * impact", name="ck_risk_score"),
        CheckConstraint(
            "status IN ('Open','Mitigating','Closed','Accepted')", name="ck_risk_status"
        ),
        CheckConstraint("mitigation_progress BETWEEN 0 AND 100", name="ck_risk_mitigation"),
    )


class ScrumCeremony(Base):
    __tablename__ = "scrum_ceremonies"

    ceremony_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("sprints.sprint_id", ondelete="SET NULL")
    )  # ext
    ceremony_type: Mapped[str] = mapped_column(String(20), nullable=False)
    ceremony_date: Mapped[date] = mapped_column(Date, nullable=False)
    attendance_rate: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    action_items: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "ceremony_type IN ('Sprint Planning','Daily Standup','Sprint Review','Retrospective')",
            name="ck_cer_type",
        ),
        CheckConstraint("attendance_rate BETWEEN 0 AND 1", name="ck_cer_attendance"),
    )


class Performance(Base):
    __tablename__ = "performance"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.employee_id"), primary_key=True
    )
    sprint_id: Mapped[int] = mapped_column(
        ForeignKey("sprints.sprint_id", ondelete="CASCADE"), primary_key=True
    )
    stories_assigned: Mapped[int] = mapped_column(Integer, nullable=False)
    stories_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    story_points_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    bugs_reopened: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable: imported sheets may not have a peer review for every person-sprint.
    peer_review_score: Mapped[float | None] = mapped_column(Numeric(3, 1))

    __table_args__ = (
        CheckConstraint("stories_completed <= stories_assigned", name="ck_perf_stories"),
        CheckConstraint("peer_review_score BETWEEN 1 AND 5", name="ck_perf_peer"),
    )


class ProjectHistory(Base):
    """Archived PMO close-out records used to train the delay model (ext)."""

    __tablename__ = "project_history"

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_code: Mapped[str] = mapped_column(String(20), nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False)
    close_year: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_utilization: Mapped[float] = mapped_column(Float, nullable=False)
    open_risks: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_resource_utilization: Mapped[float] = mapped_column(Float, nullable=False)
    sprint_velocity: Mapped[float] = mapped_column(Float, nullable=False)
    tasks_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    delayed: Mapped[int] = mapped_column(Integer, nullable=False)


class DataImport(Base):
    """One row per data load (spreadsheet import or synthetic generator run). Kept across reloads."""

    __tablename__ = "data_imports"

    import_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    files: Mapped[str | None] = mapped_column(Text)
    row_counts: Mapped[str] = mapped_column(Text, nullable=False)  # JSON {table: rows}
    data_as_of: Mapped[date | None] = mapped_column(Date)


# Insert order that satisfies foreign keys.
TABLE_LOAD_ORDER = [
    "employees",
    "projects",
    "sprints",
    "tasks",
    "risks",
    "scrum_ceremonies",
    "performance",
    "project_history",
]
