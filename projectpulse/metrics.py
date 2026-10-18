"""Portfolio, agile, resource and people metrics.

Every function is pure pandas: it takes DataFrames plus an ``as_of`` date (the
end of the dashboard's date filter) and returns a DataFrame or scalar. Because
metrics are computed *as of* a date, moving the date filter replays the
portfolio as it looked at that point in time.

Metric definitions (also in README)
-----------------------------------
Progress (% complete)  = story points done / total story points in scope
Planned progress       = linear from first sprint start to planned end date
PV / EV / AC           = budget x planned %, budget x actual %, cost to date
SPI                    = EV / PV  (completed projects: planned / actual duration)
CPI                    = EV / AC
Schedule variance (SV) = EV - PV          Cost variance (CV) = EV - AC
Budget variance %      = (AC - EV) / EV   (positive = over budget)
EAC                    = budget / CPI
Risk exposure          = sum of probability x impact for unresolved risks,
                         mitigating risks discounted by half their mitigation %
Health score           = 40 % schedule + 30 % budget + 30 % risk health
Velocity               = story points completed in a sprint
Commitment reliability = completed / planned story points
Lead time              = completion - created (days)
Cycle time             = completion - work started (days)
Utilisation            = planned sprint hours / capacity hours
Defect rate            = bugs reopened / stories completed
Performance score      = 30 % completion + 30 % on-time + 20 % sprint
                         contribution + 20 % collaboration (peer review)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

INITIATION_SHARE = 0.12  # fallback when a project has no sprints yet
DELAY_TOLERANCE = 0.10  # forecast slip (share of planned duration) before "delayed"
OPEN_RISK_STATUSES = ("Open", "Mitigating")


# --------------------------------------------------------------------------- helpers
def _ts(x) -> pd.Timestamp:
    return pd.Timestamp(x).normalize()


def rag(score: float) -> str:
    """Traffic-light band for a 0-100 health score."""
    if pd.isna(score):
        return "Grey"
    if score >= config.HEALTH_GREEN:
        return "Green"
    if score >= config.HEALTH_YELLOW:
        return "Yellow"
    return "Red"


def schedule_health(spi: float) -> float:
    """100 at SPI >= 1, falling 2.5 points per 1 % schedule slippage."""
    if pd.isna(spi):
        return np.nan
    return float(np.clip(100 - max(0.0, 1 - spi) * 250, 0, 100))


def budget_health(cpi: float) -> float:
    """100 at CPI >= 1, falling 3 points per 1 % cost overrun (1/CPI - 1)."""
    if pd.isna(cpi) or cpi <= 0:
        return np.nan
    return float(np.clip(100 - max(0.0, 1 / cpi - 1) * 300, 0, 100))


def risk_health(exposure: float) -> float:
    """Exponential decay: exposure 50 -> ~78, 100 -> ~61, 200 -> ~37."""
    return float(100 * np.exp(-max(exposure, 0) / 200))


def health_score(sched: float, budget: float, risk: float) -> float:
    w = config.HEALTH_WEIGHTS
    return float(w["schedule"] * sched + w["budget"] * budget + w["risk"] * risk)


def classify_delay(prob: float) -> str:
    bands = config.DELAY_CLASS_BANDS
    if prob < bands["Low Risk"]:
        return "Low Risk"
    if prob < bands["Medium Risk"]:
        return "Medium Risk"
    return "High Risk"


def open_risks_as_of(risks: pd.DataFrame, as_of) -> pd.DataFrame:
    """Risks identified on/before ``as_of`` and not yet resolved at that date."""
    as_of = _ts(as_of)
    r = risks[risks.identified_date <= as_of]
    unresolved = r.resolved_date.isna() | (r.resolved_date > as_of)
    return r[unresolved]


def risk_exposure(open_risks: pd.DataFrame) -> pd.Series:
    """Per-project exposure; mitigating risks are discounted by progress."""
    discount = np.where(open_risks.status == "Mitigating",
                        1 - open_risks.mitigation_progress / 200, 1.0)
    return (open_risks.risk_score * discount).groupby(open_risks.project_id).sum()


# --------------------------------------------------------------------------- utilisation
def daily_assignment(tasks: pd.DataFrame, sprints: pd.DataFrame) -> pd.DataFrame:
    """Spread each employee's planned sprint hours evenly over the sprint's working days."""
    t = tasks[tasks.sprint_id.notna() & tasks.employee_id.notna()]
    cell = (t.groupby(["employee_id", "sprint_id", "project_id"], as_index=False)
             .planned_hours.sum()
             .merge(sprints[["sprint_id", "start_date", "end_date"]], on="sprint_id"))
    start = cell.start_date.values.astype("datetime64[D]")
    end = cell.end_date.values.astype("datetime64[D]") + np.timedelta64(1, "D")
    n = np.busday_count(start, end)
    idx = np.repeat(np.arange(len(cell)), n)
    offsets = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    days = np.busday_offset(start[idx], offsets, roll="forward")
    return pd.DataFrame({
        "employee_id": cell.employee_id.values[idx].astype(int),
        "project_id": cell.project_id.values[idx].astype(int),
        "date": pd.to_datetime(days),
        "hours": (cell.planned_hours.values / n)[idx],
    })


def utilisation_by_employee(daily: pd.DataFrame, employees: pd.DataFrame,
                            start, end) -> pd.DataFrame:
    """Assigned hours vs capacity per employee over [start, end]."""
    start, end = _ts(start), _ts(end)
    window = daily[(daily.date >= start) & (daily.date <= end)]
    bdays = max(np.busday_count(start.date(), (end + pd.Timedelta(days=1)).date()), 1)
    hours = window.groupby("employee_id").hours.sum()
    out = employees.set_index("employee_id")[["employee_name", "department", "role",
                                               "weekly_capacity_hours"]].copy()
    out["assigned_hours"] = hours.reindex(out.index).fillna(0.0)
    out["capacity_hours"] = out.weekly_capacity_hours / 5 * bdays
    out["utilization"] = out.assigned_hours / out.capacity_hours
    out["projects"] = window.groupby("employee_id").project_id.nunique().reindex(out.index).fillna(0).astype(int)
    return out.reset_index()


def utilisation_by_month(daily: pd.DataFrame, employees: pd.DataFrame,
                         start, end) -> pd.DataFrame:
    """Employee x month utilisation matrix (long form)."""
    start, end = _ts(start), _ts(end)
    d = daily[(daily.date >= start) & (daily.date <= end)].copy()
    d["month"] = d.date.dt.to_period("M").dt.to_timestamp()
    hours = d.groupby(["employee_id", "month"]).hours.sum().reset_index()
    months = pd.period_range(start, end, freq="M").to_timestamp()
    bdays = pd.Series({m: np.busday_count(m.date(), (m + pd.offsets.MonthBegin(1)).date())
                       for m in months})
    cap = employees.set_index("employee_id").weekly_capacity_hours / 5
    hours["utilization"] = hours.hours / (hours.employee_id.map(cap) * hours.month.map(bdays))
    return hours


# --------------------------------------------------------------------------- projects
def project_metrics(data: dict[str, pd.DataFrame], as_of, daily: pd.DataFrame | None = None
                    ) -> pd.DataFrame:
    """One row per project that had started by ``as_of`` with EVM, risk and health."""
    as_of = _ts(as_of)
    projects, tasks, sprints = data["projects"], data["tasks"], data["sprints"]
    employees, risks = data["employees"], data["risks"]
    data_end = data_as_of(data)

    p = projects[projects.start_date <= as_of].copy()
    p = p.merge(employees[["employee_id", "employee_name"]]
                .rename(columns={"employee_id": "project_manager_id",
                                 "employee_name": "project_manager"}),
                on="project_manager_id", how="left")

    done_mask = tasks.completion_date.notna() & (tasks.completion_date <= as_of)
    total_sp = tasks.groupby("project_id").story_points.sum()
    done_sp = tasks[done_mask].groupby("project_id").story_points.sum()
    remaining = tasks[tasks.created_date <= as_of].assign(open=~done_mask).groupby("project_id").open.sum()

    # Cost to date: actual cost is attributed to completed work in proportion to effort.
    done_all = tasks[tasks.status == "Done"]
    rate = (projects.set_index("project_id").actual_cost
            / done_all.groupby("project_id").actual_hours.sum())
    hours_to_date = tasks[done_mask].groupby("project_id").actual_hours.sum()

    p["completed_as_of"] = p.actual_end_date.notna() & (p.actual_end_date <= as_of)
    p["status_as_of"] = np.where(p.completed_as_of, "Completed",
                                 np.where(as_of >= data_end, p.status, "Active"))
    p["progress"] = (p.project_id.map(done_sp).fillna(0) / p.project_id.map(total_sp)).fillna(0)
    planned_days = (p.planned_end_date - p.start_date).dt.days
    elapsed = (as_of - p.start_date).dt.days
    # Delivery baseline: linear from the first sprint (end of initiation) to planned end.
    first_sprint = p.project_id.map(sprints.groupby("project_id").start_date.min())
    default_init = planned_days * INITIATION_SHARE
    init = ((first_sprint - p.start_date).dt.days).fillna(default_init).clip(upper=planned_days - 1)
    p["planned_progress"] = np.clip((elapsed - init) / (planned_days - init), 0, 1)
    p.loc[p.completed_as_of, "planned_progress"] = 1.0

    p["pv"] = p.budget * p.planned_progress
    p["ev"] = p.budget * p.progress
    p["ac"] = np.where(p.completed_as_of, p.actual_cost,
                       p.project_id.map(rate) * p.project_id.map(hours_to_date).fillna(0))
    p["ac"] = p.ac.fillna(0)
    p["spi"] = np.where(p.pv > 0, p.ev / p.pv.replace(0, np.nan), np.nan)
    actual_days = (p.actual_end_date - p.start_date).dt.days
    p.loc[p.completed_as_of, "spi"] = planned_days / actual_days
    p["cpi"] = np.where(p.ac > 0, p.ev / p.ac.replace(0, np.nan), np.nan)
    p["schedule_variance"] = p.ev - p.pv
    p["cost_variance"] = p.ev - p.ac
    p["budget_variance_pct"] = np.where(p.ev > 0, (p.ac - p.ev) / p.ev, np.nan)
    p["budget_utilization"] = p.ac / p.budget
    p["eac"] = np.where(p.cpi > 0, p.budget / p.cpi, p.budget)
    p["vac"] = p.budget - p.eac
    p["tasks_remaining"] = p.project_id.map(remaining).fillna(0).astype(int)

    # Forecast finish: extrapolate the delivery rate achieved since initiation ended.
    delivery_days = (elapsed - init).clip(lower=1)
    rate_per_day = p.progress / delivery_days
    days_left = np.where(rate_per_day > 0, (1 - p.progress) / rate_per_day.replace(0, np.nan),
                         (planned_days - elapsed).clip(lower=0))
    days_left = pd.Series(days_left, index=p.index).fillna(0).clip(upper=3 * 365)
    p["forecast_end"] = as_of + pd.to_timedelta(days_left.round(), unit="D")
    early_phase = elapsed <= init  # too early to extrapolate - assume plan
    p.loc[early_phase, "forecast_end"] = p.planned_end_date
    p.loc[p.completed_as_of, "forecast_end"] = p.actual_end_date
    p["delay_days"] = (p.forecast_end - p.planned_end_date).dt.days
    tolerance = (planned_days * DELAY_TOLERANCE).clip(lower=7)
    p["is_delayed"] = np.where(p.completed_as_of, p.delay_days > 0, p.delay_days > tolerance)

    # Risks
    o = open_risks_as_of(risks, as_of)
    p["open_risks"] = p.project_id.map(o.groupby("project_id").size()).fillna(0).astype(int)
    high = o[o.risk_score >= config.HIGH_RISK_SCORE]
    p["high_risks"] = p.project_id.map(high.groupby("project_id").size()).fillna(0).astype(int)
    p["risk_exposure"] = p.project_id.map(risk_exposure(o)).fillna(0.0)

    # Agile signals
    sp = sprint_metrics(sprints[sprints.start_date <= as_of], as_of)
    closed = sp[sp.is_closed].sort_values(["project_id", "sprint_number"])
    # Position of each closed sprint counted back from the latest (0 = most recent).
    back = closed.groupby("project_id").cumcount(ascending=False)
    recent3, prior3 = closed[back < 3], closed[(back >= 3) & (back < 6)]
    vel_recent = recent3.groupby("project_id").velocity.mean()
    vel_prior = prior3.groupby("project_id").velocity.mean()
    vel_prior = vel_prior[prior3.groupby("project_id").size() == 3]
    p["velocity_recent"] = p.project_id.map(vel_recent)
    p["velocity_change_pct"] = p.project_id.map((vel_recent - vel_prior) / vel_prior)
    sums = recent3.groupby("project_id")[["velocity", "planned_story_points"]].sum()
    rel = sums.velocity / sums.planned_story_points.clip(lower=1)
    p["commitment_reliability"] = p.project_id.map(rel)

    cer = data["scrum_ceremonies"]
    cer = cer[(cer.ceremony_date <= as_of) & (cer.ceremony_date > as_of - pd.Timedelta(days=90))]
    p["attendance_rate"] = p.project_id.map(cer.groupby("project_id").attendance_rate.mean())

    # Team utilisation (everyone on the project, all their work) over the last 8 weeks.
    if daily is None:
        daily = daily_assignment(tasks, sprints)
    window_start = as_of - pd.Timedelta(weeks=8)
    recent = daily[(daily.date > window_start) & (daily.date <= as_of)]
    util = utilisation_by_employee(daily, employees, window_start + pd.Timedelta(days=1), as_of)
    util = util.set_index("employee_id")
    team_util = {}
    for pid, members in recent.groupby("project_id").employee_id.unique().items():
        u = util.loc[members]
        team_util[pid] = u.assigned_hours.sum() / u.capacity_hours.sum()
    p["team_utilization"] = p.project_id.map(team_util)
    p["team_size"] = p.project_id.map(recent.groupby("project_id").employee_id.nunique()).fillna(0).astype(int)

    # Health
    p["schedule_health"] = p.spi.map(schedule_health)
    p["budget_health"] = p.cpi.map(budget_health).fillna(100.0)
    p["risk_health"] = p.risk_exposure.map(risk_health)
    p["schedule_health"] = p.schedule_health.fillna(100.0)
    p["health_score"] = [health_score(s, b, r) for s, b, r in
                         zip(p.schedule_health, p.budget_health, p.risk_health)]
    p["rag"] = p.health_score.map(rag)
    # Status derived from the numbers (works for any as-of date, unlike the reported status).
    p["computed_status"] = np.select(
        [p.completed_as_of, p.is_delayed, p.rag != "Green"],
        ["Completed", "Delayed", "At Risk"], default="On Track")
    return p.reset_index(drop=True)


def data_as_of(data: dict[str, pd.DataFrame]) -> pd.Timestamp:
    """Latest date with recorded activity - the snapshot date of the data set."""
    t = data["tasks"]
    return _ts(max(t.completion_date.max(), t.created_date.max(),
                   data["scrum_ceremonies"].ceremony_date.max()))


def portfolio_kpis(pm: pd.DataFrame) -> dict[str, float]:
    """Headline KPIs over the projects in ``pm`` (output of project_metrics)."""
    active = pm[pm.status_as_of != "Completed"]
    scope = active if len(active) else pm
    weights = scope.budget
    return {
        "active_projects": int(len(active)),
        "total_projects": int(len(pm)),
        "portfolio_health": float(np.average(scope.health_score, weights=weights)) if len(scope) else np.nan,
        "budget_utilization": float(scope.ac.sum() / scope.budget.sum()) if len(scope) else np.nan,
        "portfolio_cpi": float(scope.ev.sum() / scope.ac.sum()) if scope.ac.sum() else np.nan,
        "portfolio_spi": float(scope.ev.sum() / scope.pv.sum()) if scope.pv.sum() else np.nan,
        "delayed_projects": int(pm.is_delayed.sum()),
        "open_risks": int(pm.open_risks.sum()),
        "high_risks": int(pm.high_risks.sum()),
        "total_budget": float(pm.budget.sum()),
        "total_cost": float(pm.ac.sum()),
    }


def budget_trend(projects: pd.DataFrame, tasks: pd.DataFrame, start, end) -> pd.DataFrame:
    """Monthly planned vs actual spend (and cumulative) for the given projects."""
    start, end = _ts(start), _ts(end)
    months = pd.period_range(start, end, freq="M").to_timestamp()
    planned = pd.Series(0.0, index=months)
    for p in projects.itertuples():
        days = pd.date_range(p.start_date, p.planned_end_date - pd.Timedelta(days=1))
        per_day = p.budget / len(days)
        m = pd.Series(per_day, index=days).resample("MS").sum()
        planned = planned.add(m.reindex(months).fillna(0), fill_value=0)

    done = tasks[(tasks.status == "Done") & tasks.project_id.isin(projects.project_id)]
    rate = projects.set_index("project_id").actual_cost / done.groupby("project_id").actual_hours.sum()
    cost = done.actual_hours * done.project_id.map(rate)
    actual = cost.groupby(done.completion_date.dt.to_period("M").dt.to_timestamp()).sum()
    actual = actual.reindex(months).fillna(0)
    actual[months > end] = np.nan

    out = pd.DataFrame({"month": months, "planned": planned.values, "actual": actual.values})
    # Cumulative from the start of each project's life, not just the visible window.
    before_planned = 0.0
    for p in projects.itertuples():
        if p.start_date < start:
            days = pd.date_range(p.start_date, min(start, p.planned_end_date) - pd.Timedelta(days=1))
            before_planned += p.budget / max((p.planned_end_date - p.start_date).days, 1) * len(days)
    before_actual = cost[done.completion_date < start].sum()
    out["planned_cum"] = out.planned.cumsum() + before_planned
    out["actual_cum"] = out.actual.cumsum() + before_actual
    return out


# --------------------------------------------------------------------------- agile
def sprint_metrics(sprints: pd.DataFrame, as_of=None) -> pd.DataFrame:
    s = sprints.copy()
    as_of = _ts(as_of) if as_of is not None else s.end_date.max()
    s["is_closed"] = (s.end_date <= as_of) & (s.status == "Closed")
    s["velocity"] = s.completed_story_points
    s["commitment_reliability"] = s.completed_story_points / s.planned_story_points.replace(0, np.nan)
    s["successful"] = s.commitment_reliability >= config.SPRINT_SUCCESS_THRESHOLD
    return s


def task_flow_times(tasks: pd.DataFrame) -> pd.DataFrame:
    """Lead and cycle time (days) for completed tasks."""
    d = tasks[tasks.status == "Done"].copy()
    d["lead_time_days"] = (d.completion_date - d.created_date).dt.days
    d["cycle_time_days"] = (d.completion_date - d.started_date).dt.days.clip(lower=0)
    return d


def burndown(tasks: pd.DataFrame, sprint: pd.Series, as_of=None) -> pd.DataFrame:
    """Daily remaining story points for one sprint, with the ideal line."""
    t = tasks[tasks.sprint_id == sprint.sprint_id]
    days = pd.date_range(sprint.start_date, sprint.end_date, freq="D")
    total = t.story_points.sum()
    actual = [total - t[t.completion_date <= d].story_points.sum() for d in days]
    ideal = np.linspace(total, 0, len(days))
    out = pd.DataFrame({"date": days, "ideal": ideal, "remaining": actual})
    if as_of is not None:
        out.loc[out.date > _ts(as_of), "remaining"] = np.nan
    return out


# --------------------------------------------------------------------------- people
def employee_performance(tasks: pd.DataFrame, performance: pd.DataFrame,
                         sprints: pd.DataFrame, employees: pd.DataFrame) -> pd.DataFrame:
    """Employee KPI table + weighted performance score (inputs already date-filtered)."""
    t = tasks[tasks.sprint_id.isin(sprints.sprint_id) & tasks.employee_id.notna()]
    g = t.groupby("employee_id")
    done = t[t.status == "Done"]
    out = pd.DataFrame({
        "tasks_assigned": g.size(),
        "tasks_completed": done.groupby("employee_id").size(),
        "on_time": done[done.completion_date <= done.due_date].groupby("employee_id").size(),
    }).fillna(0)

    pf = performance[performance.sprint_id.isin(sprints.sprint_id)]
    # Sprint contribution: each person's SP relative to the average team member in the same sprint.
    team_avg = pf.groupby("sprint_id").story_points_completed.transform("mean")
    pf = pf.assign(rel=pf.story_points_completed / team_avg.replace(0, np.nan))
    agg = pf.groupby("employee_id").agg(
        story_points_delivered=("story_points_completed", "sum"),
        stories_completed=("stories_completed", "sum"),
        bugs_reopened=("bugs_reopened", "sum"),
        peer_review_score=("peer_review_score", "mean"),
        contribution_ratio=("rel", "mean"),
        sprints=("sprint_id", "nunique"),
    )
    out = out.join(agg, how="inner")
    out["task_completion_rate"] = out.tasks_completed / out.tasks_assigned
    out["on_time_rate"] = (out.on_time / out.tasks_completed.replace(0, np.nan)).fillna(0)
    out["defect_rate"] = (out.bugs_reopened / out.stories_completed.replace(0, np.nan)).fillna(0)
    out["sprint_contribution"] = (out.contribution_ratio.clip(upper=1.5) / 1.5 * 100).fillna(0)
    out["collaboration"] = out.peer_review_score / 5 * 100
    w = config.PERFORMANCE_WEIGHTS
    delivery = (w["task_completion"] * out.task_completion_rate * 100
                + w["on_time"] * out.on_time_rate * 100
                + w["sprint_contribution"] * out.sprint_contribution)
    # Without a peer review (imported data may lack one) the other three weights are rescaled.
    out["performance_score"] = np.where(
        out.collaboration.notna(), delivery + w["collaboration"] * out.collaboration.fillna(0),
        delivery / (1 - w["collaboration"]))
    out = out.join(employees.set_index("employee_id")[["employee_name", "department", "role"]])
    out = out.reset_index().sort_values("performance_score", ascending=False)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def performance_band(score: float) -> str:
    if score >= 85:
        return "Exceeds"
    if score >= 72:
        return "Meets"
    return "Developing"


def risk_severity(score: float) -> str:
    if score >= config.HIGH_RISK_SCORE:
        return "High"
    if score >= 8:
        return "Medium"
    return "Low"
