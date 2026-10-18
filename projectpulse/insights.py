"""Rule-based "AI Insights" engine.

Turns project metrics into an analyst-style narrative: a headline, the main
drivers ranked by severity, what is going well, and concrete recommendations.
No LLM is required - every sentence is generated from the numbers, so the
output is deterministic, auditable and always consistent with the dashboards.

The ``answer`` function is a small intent router so the page can behave like a
chat assistant ("Why is Project Phoenix unhealthy?", "Compare Titan and Orion").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .metrics import classify_delay

NUMBER_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
                "Ten", "Eleven", "Twelve"]


def _n(n: int) -> str:
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)


def _money(x: float) -> str:
    sign, x = ("-" if x < 0 else ""), abs(x)
    if x >= 1e6:
        return f"{sign}${x / 1e6:,.2f}M"
    if x >= 1e3:
        return f"{sign}${x / 1e3:,.0f}K"
    return f"{sign}${x:,.0f}"


@dataclass
class Driver:
    key: str
    text: str
    severity: float  # 0-1, used for ranking
    recommendation: str


@dataclass
class Diagnosis:
    project_name: str
    health_score: float
    rag: str
    headline: str
    drivers: list[Driver] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)

    def to_markdown(self, max_drivers: int = 6) -> str:
        lines = [self.headline, ""]
        if self.drivers:
            lines.append("**Main drivers:**")
            lines += [f"- {d.text}" for d in self.drivers[:max_drivers]]
            lines.append("")
        if self.positives:
            lines.append("**What is working:**")
            lines += [f"- {p}" for p in self.positives]
            lines.append("")
        recs = self.recommendations(max_drivers)
        if recs:
            lines.append("**Recommendations:**")
            lines += [f"{i}. {r}" for i, r in enumerate(recs, start=1)]
        return "\n".join(lines)

    def recommendations(self, limit: int = 6) -> list[str]:
        seen, out = set(), []
        for d in self.drivers[:limit]:
            if d.recommendation not in seen:
                seen.add(d.recommendation)
                out.append(d.recommendation)
        if not out:
            out.append("Maintain current cadence; keep monitoring SPI/CPI and the risk register "
                       "in the weekly status review.")
        return out


@dataclass
class InsightContext:
    """Everything the engine needs, prepared once by the page."""

    pm: pd.DataFrame  # metrics.project_metrics (+ delay_probability / risk_class)
    open_risks: pd.DataFrame  # open risks with project_name
    utilization: pd.DataFrame  # metrics.utilisation_by_employee for the recent window
    tasks: pd.DataFrame
    team: dict[int, list[int]]  # project_id -> employee ids active recently

    def project(self, name_or_id) -> pd.Series | None:
        pm = self.pm
        if isinstance(name_or_id, (int, np.integer)):
            hit = pm[pm.project_id == name_or_id]
        else:
            hit = pm[pm.project_name.str.lower() == str(name_or_id).lower()]
        return None if hit.empty else hit.iloc[0]


# --------------------------------------------------------------------------- diagnosis
def diagnose(row: pd.Series, ctx: InsightContext) -> Diagnosis:
    name = row.project_name
    drivers: list[Driver] = []
    positives: list[str] = []
    completed = row.status_as_of == "Completed"

    # Schedule
    if pd.notna(row.spi) and row.spi < 0.95:
        behind = (1 - row.spi) * 100
        if completed:
            text = (f"Delivered {row.delay_days:.0f} days after the planned end date "
                    f"(schedule performance {row.spi:.2f}).")
        else:
            text = (f"Schedule performance index is {row.spi:.2f} - {behind:.0f}% behind plan "
                    f"({row.progress:.0%} complete vs {row.planned_progress:.0%} planned); "
                    f"forecast finish {row.forecast_end:%d %b %Y}"
                    + (f", {row.delay_days:.0f} days late." if row.delay_days > 0 else "."))
        drivers.append(Driver("schedule", text, min(1, (1 - row.spi) * 3),
                              "Re-baseline with the steering committee and agree a MoSCoW scope-cut "
                              "list to protect the critical path; track SPI weekly."))
    elif pd.notna(row.spi):
        positives.append(f"Schedule on plan (SPI {row.spi:.2f}).")

    # Velocity trend
    if pd.notna(row.velocity_change_pct) and row.velocity_change_pct <= -0.08:
        prior = row.velocity_recent / (1 + row.velocity_change_pct)
        drivers.append(Driver(
            "velocity",
            f"Sprint velocity declined {abs(row.velocity_change_pct):.0%} over the last three "
            f"sprints ({prior:.0f} → {row.velocity_recent:.0f} story points per sprint).",
            min(1, abs(row.velocity_change_pct) * 2.5),
            "Run a focused retrospective on the velocity drop - check unplanned work, WIP limits "
            "and carry-over - and plan the next sprint on recent velocity, not historical."))

    # Commitment reliability
    if pd.notna(row.commitment_reliability) and row.commitment_reliability < config.SPRINT_SUCCESS_THRESHOLD:
        drivers.append(Driver(
            "reliability",
            f"Team is completing only {row.commitment_reliability:.0%} of committed story points "
            f"(target {config.SPRINT_SUCCESS_THRESHOLD:.0%}).",
            min(1, (config.SPRINT_SUCCESS_THRESHOLD - row.commitment_reliability) * 4),
            f"Commit to ~{row.velocity_recent:.0f} SP per sprint (yesterday's weather) and enforce "
            "a Definition of Ready before items enter a sprint."))
    elif pd.notna(row.commitment_reliability):
        positives.append(f"Sprint commitments are reliable ({row.commitment_reliability:.0%} delivered).")

    # Budget
    if pd.notna(row.budget_variance_pct) and row.budget_variance_pct > 0.03:
        overrun = row.eac - row.budget
        drivers.append(Driver(
            "budget",
            f"Budget exceeded by {row.budget_variance_pct:.0%} relative to work delivered "
            f"(CPI {row.cpi:.2f}); estimate at completion {_money(row.eac)} vs budget "
            f"{_money(row.budget)} ({_money(overrun)} over).",
            min(1, row.budget_variance_pct * 4),
            "Freeze discretionary spend, review contractor burn and EAC weekly with Finance, and "
            "raise a change request if the overrun is structural."))
    elif pd.notna(row.cpi):
        positives.append(f"Cost performance healthy (CPI {row.cpi:.2f}).")

    # Risks
    pr = ctx.open_risks[ctx.open_risks.project_id == row.project_id]
    high = pr[pr.risk_score >= config.HIGH_RISK_SCORE].sort_values("risk_score", ascending=False)
    if len(high):
        top = high.iloc[0]
        drivers.append(Driver(
            "risks",
            f"{_n(len(high))} unresolved high-risk issue{'s' if len(high) != 1 else ''} "
            f"(score ≥ {config.HIGH_RISK_SCORE}) out of {len(pr)} open; most severe: "
            f"“{top.risk_description}” (score {top.risk_score}, {top.status.lower()}).",
            min(1, 0.25 + len(high) * 0.1),
            f"Escalate the top {min(len(high), 3)} high risks to the steering committee, confirm "
            "mitigation owners and due dates, and review the register weekly."))
    elif len(pr) == 0 and not completed:
        positives.append("No open risks on the register.")

    # Resourcing
    if pd.notna(row.team_utilization) and row.team_utilization > config.OVERLOAD_THRESHOLD:
        team = ctx.team.get(row.project_id, [])
        u = ctx.utilization[ctx.utilization.employee_id.isin(team)]
        overloaded = u[u.utilization > config.OVERLOAD_THRESHOLD]
        drivers.append(Driver(
            "utilization",
            f"Resource utilization reached {row.team_utilization:.0%} of capacity across the "
            f"{row.team_size}-person team; {len(overloaded)} member"
            f"{'s are' if len(overloaded) != 1 else ' is'} above 100%.",
            min(1, (row.team_utilization - 1) * 4 + 0.2),
            _rebalance_recommendation(overloaded, ctx)))

    # Ceremonies
    if pd.notna(row.attendance_rate) and row.attendance_rate < 0.85:
        drivers.append(Driver(
            "attendance",
            f"Scrum ceremony attendance averaging {row.attendance_rate:.0%} over the last 90 days.",
            min(1, (0.85 - row.attendance_rate) * 5),
            "Reset team working agreements: protect ceremony time in calendars, keep stand-ups to "
            "15 minutes, and make retrospective actions visible on the board."))

    # Blocked work
    blocked = ctx.tasks[(ctx.tasks.project_id == row.project_id) & (ctx.tasks.status == "Blocked")]
    if len(blocked) >= 10:
        drivers.append(Driver(
            "blocked",
            f"{len(blocked)} tasks are currently blocked.",
            min(1, len(blocked) / 60),
            "Introduce a daily blocker triage with the PM and dependency owners; escalate blockers "
            "older than 3 days."))

    # Predictive
    if "delay_probability" in row and pd.notna(row.get("delay_probability")) and not completed:
        p = row.delay_probability
        if p >= config.DELAY_CLASS_BANDS["Low Risk"]:
            drivers.append(Driver(
                "prediction",
                f"Delay model estimates a {p:.0%} probability of late delivery ({classify_delay(p)}).",
                p * 0.8,
                "Use the Predictive Analytics what-if panel to test which lever (risks, velocity, "
                "scope) brings delay probability below 35%."))

    drivers.sort(key=lambda d: d.severity, reverse=True)
    verdict = {"Green": "healthy", "Yellow": "under watch", "Red": "unhealthy"}.get(row.rag, "")
    headline = (f"**{name}** has a health score of **{row.health_score:.0f}** "
                f"({row.rag} - {verdict}). Schedule {row.schedule_health:.0f} · Budget "
                f"{row.budget_health:.0f} · Risk {row.risk_health:.0f}.")
    return Diagnosis(name, float(row.health_score), row.rag, headline, drivers, positives)


def _rebalance_recommendation(overloaded: pd.DataFrame, ctx: InsightContext) -> str:
    names = ", ".join(overloaded.sort_values("utilization", ascending=False)
                      .employee_name.head(3).tolist())
    spare = ctx.utilization[(ctx.utilization.utilization < config.UNDERUTILISED_THRESHOLD)
                            & (ctx.utilization.role != "Project Manager")]
    spare_names = ", ".join(spare.sort_values("utilization").employee_name.head(2).tolist())
    rec = "Rebalance workload"
    if names:
        rec += f" - start with {names}"
    if spare_names:
        rec += f"; under-utilised capacity is available ({spare_names})"
    return rec + ", or defer lower-priority backlog items."


# --------------------------------------------------------------------------- portfolio
def portfolio_briefing(ctx: InsightContext) -> str:
    pm = ctx.pm
    active = pm[pm.status_as_of != "Completed"]
    scope = active if len(active) else pm
    health = np.average(scope.health_score, weights=scope.budget) if len(scope) else float("nan")
    red = scope[scope.rag == "Red"].sort_values("health_score")
    yellow = scope[scope.rag == "Yellow"].sort_values("health_score")
    cpi = scope.ev.sum() / scope.ac.sum() if scope.ac.sum() else float("nan")
    eac_over = (scope.eac - scope.budget).clip(lower=0).sum()
    over = ctx.utilization[(ctx.utilization.utilization > config.OVERLOAD_THRESHOLD)]
    high = ctx.open_risks[ctx.open_risks.risk_score >= config.HIGH_RISK_SCORE]

    lines = [f"**Portfolio health is {health:.0f}** across {len(active)} active projects "
             f"(budget-weighted). Portfolio CPI is {cpi:.2f} with a forecast overrun of "
             f"{_money(eac_over)} at completion.", ""]
    if len(red):
        lines.append("**Needs executive attention (Red):**")
        for r in red.itertuples():
            lines.append(f"- **{r.project_name}** - health {r.health_score:.0f}, SPI {r.spi:.2f}, "
                         f"CPI {r.cpi:.2f}, {r.high_risks} high risks"
                         + (f", {r.delay_probability:.0%} delay probability"
                            if hasattr(r, "delay_probability") and pd.notna(r.delay_probability) else ""))
        lines.append("")
    if len(yellow):
        lines.append("**On watch (Yellow):** " + ", ".join(
            f"{r.project_name} ({r.health_score:.0f})" for r in yellow.itertuples()))
        lines.append("")
    lines.append(f"**Risk:** {len(ctx.open_risks)} open risks, {len(high)} high-severity, "
                 f"concentrated in {_top_list(high.project_name.value_counts())}.")
    lines.append(f"**People:** {len(over)} people are over 100% allocated; average utilisation "
                 f"is {ctx.utilization[ctx.utilization.assigned_hours > 0].utilization.mean():.0%} "
                 "for allocated staff.")
    if len(red):
        worst = red.iloc[0]
        lines += ["", f"**Recommended focus:** run a recovery review for **{worst.project_name}** "
                      "this week and decide on scope, staffing or timeline trade-offs."]
    return "\n".join(lines)


def _top_list(counts: pd.Series, k: int = 3) -> str:
    if counts.empty:
        return "no single project"
    return ", ".join(f"{name} ({n})" for name, n in counts.head(k).items())


# --------------------------------------------------------------------------- chat router
INTENTS = [
    ("compare", r"\bcompare\b|\bvs\.?\b|\bversus\b"),
    ("budget", r"budget|cost|spend|cpi|overrun|money|finance"),
    ("risk", r"\brisk"),
    ("resource", r"team|resource|utili[sz]|capacity|overload|people|staff|workload"),
    ("agile", r"velocity|sprint|scrum|burndown|commitment|ceremon"),
    ("delay", r"delay|late|predict|forecast|on time|deadline"),
    ("portfolio", r"portfolio|overall|summary|executive|briefing|which projects|worst|best|all projects"),
    ("health", r"unhealthy|why|health|status|doing|wrong|problem|issue"),
]


def find_projects(question: str, ctx: InsightContext) -> list[pd.Series]:
    q = question.lower()
    hits = []
    for _, row in ctx.pm.iterrows():
        short = row.project_name.lower().replace("project ", "")
        if re.search(rf"\b{re.escape(short)}\b", q):
            hits.append(row)
    return hits


def detect_intent(question: str) -> str:
    q = question.lower()
    for intent, pattern in INTENTS:
        if re.search(pattern, q):
            return intent
    return "unknown"


def answer(question: str, ctx: InsightContext) -> str:
    projects = find_projects(question, ctx)
    intent = detect_intent(question)

    if intent == "compare" and len(projects) >= 2:
        return _compare(projects[:4])
    if not projects:
        if intent in ("portfolio", "health", "compare"):
            return portfolio_briefing(ctx)
        if intent == "risk":
            return _portfolio_risks(ctx)
        if intent == "resource":
            return _portfolio_resources(ctx)
        if intent == "budget":
            return _portfolio_budget(ctx)
        if intent in ("delay", "agile"):
            return _portfolio_delay(ctx)
        return HELP_TEXT

    row = projects[0]
    diag = diagnose(row, ctx)
    focus = {"budget": "budget", "risk": "risks", "resource": "utilization",
             "agile": ("velocity", "reliability", "attendance"), "delay": ("prediction", "schedule")}
    if intent in focus:
        keys = focus[intent] if isinstance(focus[intent], tuple) else (focus[intent],)
        focused = [d for d in diag.drivers if d.key in keys]
        if focused:
            diag.drivers = focused + [d for d in diag.drivers if d not in focused]
        else:
            return (diag.headline + "\n\n" + _no_issue_text(intent, row) + "\n\n"
                    + "\n".join(f"- {p}" for p in diag.positives))
    return diag.to_markdown()


def _no_issue_text(intent: str, row: pd.Series) -> str:
    return {
        "budget": f"No budget concern: CPI is {row.cpi:.2f} and EAC is {_money(row.eac)} against a "
                  f"{_money(row.budget)} budget.",
        "risk": f"No high-severity risks; {row.open_risks} open risk(s) with exposure "
                f"{row.risk_exposure:.0f}.",
        "resource": f"Team utilisation is {row.team_utilization:.0%} - within capacity."
        if pd.notna(row.team_utilization) else "No current team allocation (project closed).",
        "agile": f"Agile delivery is stable: recent velocity {row.velocity_recent:.0f} SP, "
                 f"commitment reliability {row.commitment_reliability:.0%}.",
        "delay": "No material delay signal from the schedule or the prediction model.",
    }.get(intent, "")


def _compare(rows: list[pd.Series]) -> str:
    header = "| Metric | " + " | ".join(r.project_name for r in rows) + " |"
    sep = "|---|" + "---|" * len(rows)
    def line(label, fn):
        return f"| {label} | " + " | ".join(fn(r) for r in rows) + " |"
    table = [header, sep,
             line("Health score", lambda r: f"{r.health_score:.0f} ({r.rag})"),
             line("Progress", lambda r: f"{r.progress:.0%}"),
             line("SPI", lambda r: f"{r.spi:.2f}"),
             line("CPI", lambda r: f"{r.cpi:.2f}"),
             line("Open / high risks", lambda r: f"{r.open_risks} / {r.high_risks}"),
             line("Recent velocity", lambda r: f"{r.velocity_recent:.0f}" if pd.notna(r.velocity_recent) else "–"),
             line("Team utilisation", lambda r: f"{r.team_utilization:.0%}" if pd.notna(r.team_utilization) else "–")]
    best = max(rows, key=lambda r: r.health_score)
    worst = min(rows, key=lambda r: r.health_score)
    gap = best.health_score - worst.health_score
    summary = (f"\n\n**{best.project_name}** leads by {gap:.0f} health points. The gap is driven "
               f"mostly by {_biggest_gap(best, worst)}.")
    return "\n".join(table) + summary


def _biggest_gap(a: pd.Series, b: pd.Series) -> str:
    w = config.HEALTH_WEIGHTS
    gaps = {"schedule": w["schedule"] * (a.schedule_health - b.schedule_health),
            "budget": w["budget"] * (a.budget_health - b.budget_health),
            "risk": w["risk"] * (a.risk_health - b.risk_health)}
    k = max(gaps, key=gaps.get)
    return f"{k} health ({gaps[k]:.0f} weighted points)"


def _portfolio_risks(ctx: InsightContext) -> str:
    r = ctx.open_risks.sort_values("risk_score", ascending=False)
    high = r[r.risk_score >= config.HIGH_RISK_SCORE]
    lines = [f"**{len(r)} open risks**, {len(high)} high-severity. By category: "
             + _top_list(r.category.value_counts(), 4) + ".", "", "**Top 5 risks:**"]
    for x in r.head(5).itertuples():
        lines.append(f"- {x.project_name}: {x.risk_description} (score {x.risk_score}, {x.status})")
    return "\n".join(lines)


def _portfolio_resources(ctx: InsightContext) -> str:
    u = ctx.utilization[ctx.utilization.role != "Project Manager"]
    over = u[u.utilization > config.OVERLOAD_THRESHOLD].sort_values("utilization", ascending=False)
    under = u[u.utilization < config.UNDERUTILISED_THRESHOLD]
    dept = u.groupby("department").apply(
        lambda g: g.assigned_hours.sum() / g.capacity_hours.sum(), include_groups=False)
    lines = [f"**{len(over)} overloaded** and **{len(under)} under-utilised** people "
             f"(of {len(u)} delivery staff).",
             "Department utilisation: " + ", ".join(f"{d} {v:.0%}" for d, v in dept.sort_values(ascending=False).items()) + "."]
    if len(over):
        lines += ["", "**Most stretched:** " + ", ".join(
            f"{x.employee_name} ({x.utilization:.0%})" for x in over.head(5).itertuples())]
    return "\n".join(lines)


def _portfolio_budget(ctx: InsightContext) -> str:
    pm = ctx.pm
    over = pm[pm.budget_variance_pct > 0.03].sort_values("budget_variance_pct", ascending=False)
    lines = [f"Portfolio spend to date is {_money(pm.ac.sum())} against {_money(pm.budget.sum())} "
             f"total budget (CPI {pm.ev.sum() / pm.ac.sum():.2f})."]
    if len(over):
        lines += ["", "**Projects over budget (vs earned value):**"]
        lines += [f"- {r.project_name}: +{r.budget_variance_pct:.0%}, EAC {_money(r.eac)} vs "
                  f"{_money(r.budget)}" for r in over.itertuples()]
    return "\n".join(lines)


def _portfolio_delay(ctx: InsightContext) -> str:
    pm = ctx.pm[ctx.pm.status_as_of != "Completed"]
    if "delay_probability" not in pm:
        return "Delay predictions are not available - train the model first."
    pm = pm.sort_values("delay_probability", ascending=False)
    lines = ["**Delay probability by active project:**"]
    lines += [f"- {r.project_name}: {r.delay_probability:.0%} ({r.risk_class}), forecast finish "
              f"{r.forecast_end:%d %b %Y}" for r in pm.itertuples()]
    return "\n".join(lines)


HELP_TEXT = """I can explain project and portfolio performance. Try:

- *Why is Project Phoenix unhealthy?*
- *What are the budget issues on Titan?*
- *Compare Orion and Aurora*
- *Which projects are likely to be delayed?*
- *Give me an executive summary*
- *Who is overloaded?*"""
