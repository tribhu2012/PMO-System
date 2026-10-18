"""Synthetic Jira-style data generator for TechNova Solutions.

Design principles
-----------------
* **Internally consistent.** Sprint story points are *derived* from the tasks
  in each sprint, project cost is derived from earned progress, performance
  rows are aggregated from tasks. Nothing is sampled in isolation, so every
  KPI on every page reconciles with every other.
* **Causal, not random.** Each project carries a latent health profile
  (``healthy`` / ``watch`` / ``troubled``). The profile drives schedule slip,
  cost overrun, declining commitment reliability, overloaded teams, more and
  longer-lived risks and falling ceremony attendance - so the dashboards tell
  a coherent story and the ML model has real signal to find.
* **Reproducible.** A single seeded ``numpy.random.Generator`` drives
  everything; same seed, same data set.

Volumes (fixed by the brief): 12 projects, 75 employees, 10,000 tasks,
120 sprints, 300 risks, 500 ceremony records, 24 months of history.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config

N_EMPLOYEES = 75
N_TASKS = 10_000
N_SPRINTS = 120
N_RISKS = 300
N_CEREMONIES = 500
N_HISTORY = 480

DEPARTMENTS = ["Engineering", "Data Analytics", "Product Management", "Marketing", "Operations"]

# (role, headcount) per department - totals 75.
DEPT_ROLES: dict[str, list[tuple[str, int]]] = {
    "Engineering": [
        ("Project Manager", 2), ("Scrum Master", 2), ("Tech Lead", 3),
        ("Senior Software Engineer", 7), ("Software Engineer", 9),
        ("QA Engineer", 3), ("DevOps Engineer", 2),
    ],
    "Data Analytics": [
        ("Project Manager", 1), ("Scrum Master", 1), ("Analytics Lead", 1),
        ("Senior Data Analyst", 3), ("Data Analyst", 4), ("Data Engineer", 3),
        ("Data Scientist", 1),
    ],
    "Product Management": [
        ("Project Manager", 2), ("Scrum Master", 1), ("Senior Product Manager", 2),
        ("Product Manager", 3), ("Product Owner", 2), ("UX Designer", 2),
    ],
    "Marketing": [
        ("Project Manager", 1), ("Marketing Manager", 1), ("Marketing Analyst", 3),
        ("Content Strategist", 2), ("Digital Marketing Specialist", 2),
        ("Graphic Designer", 2),
    ],
    "Operations": [
        ("Project Manager", 1), ("Operations Manager", 1), ("Business Analyst", 3),
        ("Operations Analyst", 3), ("Process Improvement Specialist", 2),
    ],
}

FIRST_NAMES = [
    "Aisha", "Daniel", "Priya", "Marcus", "Elena", "Kenji", "Sofia", "Omar", "Grace",
    "Lucas", "Mei", "Andre", "Hannah", "Ravi", "Chloe", "Diego", "Fatima", "Noah",
    "Isabel", "Tariq", "Olivia", "Samuel", "Yuki", "Jamal", "Clara", "Mateo", "Leila",
    "Ethan", "Nadia", "Victor", "Amara", "Owen", "Ingrid", "Kofi", "Zara", "Julian",
    "Anika", "Tomas", "Rosa", "Arjun", "Maya", "Felix", "Hana", "Gabriel", "Lena",
    "Malik", "Sara", "Hugo", "Keira", "Rohan", "Ava", "Bilal", "Nora", "Theo",
    "Imani", "Leo", "Camila", "Sanjay", "Freya", "Kwame", "Lucia", "Ivan", "Tara",
    "Emeka", "Jasmine", "Pablo", "Mira", "Caleb", "Selin", "Adrian", "Naomi", "Bao",
    "Esther", "Rafael", "Ayesha", "Nikhil",
]
LAST_NAMES = [
    "Patel", "Nguyen", "Okafor", "Schmidt", "Garcia", "Tanaka", "Haddad", "Kowalski",
    "Mensah", "Rossi", "Chen", "Johnson", "Silva", "Andersen", "Kapoor", "Moreau",
    "Bhatt", "Williams", "Ibrahim", "Murphy", "Lopez", "Novak", "Sato", "Adeyemi",
    "Fischer", "Khan", "Reyes", "O'Brien", "Yilmaz", "Dubois", "Park", "Mwangi",
    "Larsen", "Costa", "Sharma", "Thompson", "Alvarez", "Kim", "Osei", "Becker",
    "Ahmed", "Walsh", "Hoang", "Petrov", "Nakamura", "Bianchi", "Diaz", "Owusu",
    "Lindqvist", "Rahman", "Carter", "Ortiz", "Jansen", "Ali", "Brooks", "Ferreira",
]


@dataclass(frozen=True)
class ProjectSpec:
    name: str
    key: str
    description: str
    department: str
    priority: str
    start: str
    planned_months: int
    schedule_factor: float  # actual duration / planned duration
    cost_factor: float  # actual cost / earned value (1 / CPI)
    profile: str  # healthy | watch | troubled
    team_size: int
    pm_index: int  # which of the department's project managers runs it
    family: str  # task-name template family
    components: tuple[str, ...]


PROJECT_SPECS: list[ProjectSpec] = [
    ProjectSpec("Project Mercury", "MER", "Marketing automation platform rollout", "Marketing",
                "Medium", "2024-10-14", 7, 1.00, 0.97, "healthy", 7, 0, "marketing",
                ("email nurture flows", "lead scoring", "campaign calendar", "CRM sync",
                 "landing pages", "attribution report")),
    ProjectSpec("Project Vanguard", "VAN", "Cloud migration wave 2 (legacy apps to AWS)",
                "Engineering", "Critical", "2024-10-21", 10, 1.32, 1.17, "troubled", 10, 0,
                "engineering", ("billing service", "identity provider", "batch scheduler",
                "file storage", "VPC networking", "legacy CRM", "monitoring stack")),
    ProjectSpec("Project Atlas", "ATL", "Enterprise data warehouse modernisation",
                "Data Analytics", "High", "2024-11-04", 9, 1.16, 1.09, "watch", 9, 0,
                "data", ("sales fact table", "customer dimension", "finance mart",
                "dbt models", "Snowflake ingestion", "data catalogue")),
    ProjectSpec("Project Helios", "HEL", "Dynamic pricing engine", "Product Management",
                "High", "2025-02-03", 7, 1.07, 1.04, "watch", 8, 0, "product",
                ("price rules engine", "competitor feed", "discount approval",
                 "pricing dashboard", "A/B pricing tests", "margin guardrails")),
    ProjectSpec("Project Titan", "TTN", "ERP integration & order-to-cash redesign",
                "Operations", "Critical", "2025-06-02", 18, 1.31, 1.16, "troubled", 11, 0,
                "operations", ("order-to-cash", "procure-to-pay", "inventory sync",
                "vendor master", "financial close", "warehouse scanning")),
    ProjectSpec("Project Phoenix", "PHX", "Customer portal re-platform", "Engineering",
                "Critical", "2025-08-04", 12, 1.38, 1.10, "troubled", 10, 1, "engineering",
                ("login flow", "account dashboard", "payment gateway", "notification service",
                 "user profile", "search API", "session management")),
    ProjectSpec("Project Quantum", "QTM", "Supply chain optimisation models", "Operations",
                "High", "2025-10-06", 13, 1.15, 1.07, "watch", 9, 0, "operations",
                ("demand forecast", "safety stock", "route planning", "supplier scorecard",
                 "S&OP workflow", "replenishment rules")),
    ProjectSpec("Project Orion", "ORN", "Mobile app 3.0", "Engineering", "High",
                "2025-12-01", 11, 0.98, 0.98, "healthy", 9, 0, "engineering",
                ("onboarding screens", "push notifications", "offline mode", "in-app chat",
                 "biometric login", "accessibility audit")),
    ProjectSpec("Project Nebula", "NEB", "Customer 360 analytics", "Data Analytics",
                "Medium", "2026-01-12", 9, 1.02, 0.99, "healthy", 8, 0, "data",
                ("identity resolution", "churn features", "CLV model", "segment builder",
                 "customer dashboard", "consent data")),
    ProjectSpec("Project Aurora", "AUR", "AI recommendation service", "Engineering", "High",
                "2026-02-02", 10, 1.20, 1.08, "watch", 9, 1, "engineering",
                ("feature store", "ranking model", "recommendation API", "model monitoring",
                 "feedback loop", "GPU inference cluster")),
    ProjectSpec("Project Horizon", "HOR", "Self-service product analytics", "Product Management",
                "Medium", "2026-04-06", 8, 1.00, 0.97, "healthy", 7, 1, "product",
                ("event taxonomy", "funnel reports", "cohort explorer", "tracking SDK",
                 "metrics layer", "usage alerts")),
    ProjectSpec("Project Sentinel", "SEN", "Brand refresh & web experience", "Marketing", "Low",
                "2026-05-04", 7, 0.97, 0.98, "healthy", 7, 0, "marketing",
                ("brand guidelines", "homepage redesign", "product pages", "SEO migration",
                 "launch campaign", "social templates")),
]

BUDGETS = {  # USD
    "Project Mercury": 640_000, "Project Vanguard": 2_750_000, "Project Atlas": 1_450_000,
    "Project Helios": 1_050_000, "Project Titan": 3_100_000, "Project Phoenix": 2_400_000,
    "Project Quantum": 1_350_000, "Project Orion": 1_600_000, "Project Nebula": 920_000,
    "Project Aurora": 1_850_000, "Project Horizon": 780_000, "Project Sentinel": 520_000,
}

PROFILE = {
    #               reliability  trend   load  risk_w  risk_tau  attend  quality  overrun
    "healthy": dict(reliability=0.93, trend=0.00, load=0.94, risk_weight=1.0, risk_tau=35,
                    attendance=0.93, quality=0.8, overrun=1.03),
    "watch": dict(reliability=0.88, trend=-0.08, load=1.08, risk_weight=1.5, risk_tau=70,
                  attendance=0.87, quality=1.1, overrun=1.10),
    "troubled": dict(reliability=0.87, trend=-0.24, load=1.35, risk_weight=2.4, risk_tau=150,
                     attendance=0.80, quality=1.5, overrun=1.22),
}
REPORTED_STATUS = {"healthy": "On Track", "watch": "At Risk", "troubled": "Delayed"}

TASK_TEMPLATES = {
    "engineering": {
        "Story": ["Implement {c}", "Build {c} UI", "Create {c} REST endpoint",
                  "Integrate {c} with {c2}", "Add role-based access to {c}"],
        "Task": ["Write unit tests for {c}", "Refactor {c} module", "Set up CI pipeline for {c}",
                 "Add observability to {c}", "Update {c} technical docs"],
        "Bug": ["Fix {c} timeout error", "Resolve {c} null-pointer exception",
                "Fix {c} layout issue on mobile", "Fix race condition in {c}"],
        "Spike": ["Spike: evaluate architecture for {c}", "Spike: load-test {c}"],
    },
    "product": {
        "Story": ["Deliver {c} MVP", "Design {c} user flow", "Build {c} configuration screen",
                  "Integrate {c} with {c2}", "Launch {c} beta"],
        "Task": ["Write acceptance criteria for {c}", "Run usability test on {c}",
                 "Define KPIs for {c}", "Prepare {c} release notes"],
        "Bug": ["Fix incorrect calculation in {c}", "Resolve {c} permission bug",
                "Fix {c} rounding error"],
        "Spike": ["Spike: market research for {c}", "Spike: vendor evaluation for {c}"],
    },
    "data": {
        "Story": ["Build {c}", "Create {c} dashboard", "Automate {c} pipeline",
                  "Join {c} with {c2}", "Publish {c} to semantic layer"],
        "Task": ["Validate {c} data quality", "Document {c} lineage", "Backfill {c} history",
                 "Optimise {c} query performance"],
        "Bug": ["Fix {c} ETL failure", "Resolve duplicate rows in {c}",
                "Fix timezone drift in {c}"],
        "Spike": ["Spike: profile source systems for {c}", "Spike: assess tooling for {c}"],
    },
    "marketing": {
        "Story": ["Launch {c}", "Design {c} creative assets", "Build {c} in CMS",
                  "Connect {c} to {c2}", "Set up {c} A/B test"],
        "Task": ["Draft copy for {c}", "Review {c} with legal", "Localise {c}",
                 "Analyse {c} performance"],
        "Bug": ["Fix broken links on {c}", "Fix tracking pixel on {c}",
                "Resolve {c} rendering issue"],
        "Spike": ["Spike: competitor audit for {c}", "Spike: audience research for {c}"],
    },
    "operations": {
        "Story": ["Configure {c} in ERP", "Redesign {c} process", "Automate {c} approvals",
                  "Integrate {c} with {c2}", "Roll out {c} to region"],
        "Task": ["Map current-state {c} process", "Run UAT for {c}", "Write SOP for {c}",
                 "Train key users on {c}", "Cleanse {c} master data"],
        "Bug": ["Fix {c} integration error", "Resolve {c} posting defect",
                "Fix {c} sync delay"],
        "Spike": ["Spike: fit-gap analysis for {c}", "Spike: assess vendor API for {c}"],
    },
}

RISK_TEMPLATES = {
    "Technical": ["Performance of {c} may not meet SLA under peak load",
                  "Integration between {c} and {c2} is more complex than estimated",
                  "Technical debt in {c} could slow delivery"],
    "Resource": ["Key {role} may be unavailable during {c} delivery",
                 "Team is over-allocated across concurrent projects",
                 "Skills gap in {c} technology stack"],
    "Schedule": ["Dependency on {c} could delay downstream milestones",
                 "UAT window for {c} may be compressed",
                 "Late requirement sign-off for {c}"],
    "Budget": ["Licence costs for {c} may exceed estimate",
               "Contractor rates increasing for {c} specialists",
               "Unplanned infrastructure spend for {c}"],
    "Scope": ["Stakeholders requesting additional features in {c}",
              "Unclear acceptance criteria for {c}",
              "Regulatory change may expand {c} scope"],
    "Vendor": ["Vendor delivery of {c} component may slip",
               "Third-party API for {c} lacks required capability"],
    "Security": ["Data privacy review of {c} not yet complete",
                 "Penetration test findings on {c} may require rework"],
    "Compliance": ["Audit requirements for {c} not fully captured",
                   "SOX controls impact on {c} process"],
}
RISK_CATEGORY_WEIGHTS = {"Technical": 0.22, "Resource": 0.16, "Schedule": 0.17, "Budget": 0.11,
                         "Scope": 0.13, "Vendor": 0.08, "Security": 0.07, "Compliance": 0.06}

FIB = np.array([1, 2, 3, 5, 8, 13])
SP_PROBS = {
    "Story": [0.06, 0.16, 0.28, 0.28, 0.16, 0.06],
    "Task": [0.20, 0.30, 0.28, 0.16, 0.06, 0.00],
    "Bug": [0.35, 0.33, 0.22, 0.10, 0.00, 0.00],
    "Spike": [0.00, 0.30, 0.40, 0.30, 0.00, 0.00],
}
ISSUE_TYPES = ["Story", "Task", "Bug", "Spike"]
ISSUE_PROBS = [0.60, 0.21, 0.14, 0.05]
PRIORITIES = ["Critical", "High", "Medium", "Low"]
PRIORITY_PROBS = [0.08, 0.27, 0.45, 0.20]
HOURS_PER_SP = 3.0


def _allocate(total: int, weights) -> np.ndarray:
    """Split an integer total proportionally to weights (largest-remainder)."""
    w = np.asarray(weights, dtype=float)
    raw = w / w.sum() * total
    base = np.floor(raw).astype(int)
    remainder = total - base.sum()
    if remainder:
        base[np.argsort(-(raw - base))[:remainder]] += 1
    return base


def _days(n: float) -> pd.Timedelta:
    return pd.Timedelta(days=int(round(n)))


class TechNovaGenerator:
    """Builds the full TechNova Solutions data set as pandas DataFrames."""

    def __init__(self, seed: int = config.RANDOM_SEED, as_of: str = config.DATA_AS_OF):
        self.rng = np.random.default_rng(seed)
        self.as_of = pd.Timestamp(as_of)

    # ------------------------------------------------------------------ public
    def generate(self) -> dict[str, pd.DataFrame]:
        employees = self._employees()
        self._traits = employees.set_index("employee_id")[["util", "skill", "quality", "collab"]]
        projects = self._projects(employees)
        self._assign_teams(employees, projects)
        sprints = self._sprints(projects)
        tasks = self._tasks(employees, projects, sprints)
        sprints = self._finalise_sprints(sprints, tasks)
        projects = self._finalise_projects(projects, tasks)
        risks = self._risks(employees, projects)
        ceremonies = self._ceremonies(projects, sprints)
        performance = self._performance(tasks, sprints, projects)
        history = self._project_history()

        public_projects = projects.drop(columns=[
            "key", "profile", "schedule_factor", "cost_factor", "projected_end",
            "sprint_window_start", "family", "components", "team_size", "pm_index",
        ])
        return {
            "employees": employees.drop(columns=["util", "skill", "quality", "collab"]),
            "projects": public_projects,
            "sprints": sprints,
            "tasks": tasks,
            "risks": risks,
            "scrum_ceremonies": ceremonies,
            "performance": performance,
            "project_history": history,
        }

    # --------------------------------------------------------------- employees
    def _employees(self) -> pd.DataFrame:
        rng = self.rng
        pairs = [(f, l) for f in FIRST_NAMES for l in LAST_NAMES]
        picks = rng.choice(len(pairs), size=N_EMPLOYEES, replace=False)
        names = [f"{pairs[i][0]} {pairs[i][1]}" for i in picks]

        rows, eid = [], 1001
        for dept, roles in DEPT_ROLES.items():
            for role, count in roles:
                for _ in range(count):
                    senior = any(k in role for k in ("Senior", "Lead", "Manager", "Owner"))
                    tenure_years = rng.uniform(3, 11) if senior else rng.uniform(0.4, 7)
                    hire = self.as_of - _days(tenure_years * 365.25)
                    capacity = int(rng.choice([40, 32, 24], p=[0.84, 0.11, 0.05]))
                    z = rng.normal()  # latent "strong performer" factor
                    rows.append({
                        "employee_id": eid,
                        "employee_name": names[eid - 1001],
                        "department": dept,
                        "role": role,
                        "hire_date": hire.normalize(),
                        "weekly_capacity_hours": capacity,
                        # hidden traits - drive generation, never stored
                        "util": float(np.clip(rng.normal(0.90, 0.15), 0.45, 1.30)),
                        "skill": float(np.clip(0.035 * z + rng.normal(0, 0.015), -0.08, 0.08)),
                        "quality": float(np.exp(-0.30 * z + rng.normal(0, 0.2))),
                        "collab": float(np.clip(3.95 + 0.30 * z + rng.normal(0, 0.25), 2.6, 4.9)),
                    })
                    eid += 1
        assert len(rows) == N_EMPLOYEES
        return pd.DataFrame(rows)

    # ---------------------------------------------------------------- projects
    def _projects(self, employees: pd.DataFrame) -> pd.DataFrame:
        pms = employees[employees.role == "Project Manager"]
        rows = []
        for pid, spec in enumerate(PROJECT_SPECS, start=1):
            start = pd.Timestamp(spec.start)
            planned_end = start + pd.DateOffset(months=spec.planned_months)
            planned_days = (planned_end - start).days
            projected_end = start + _days(planned_days * spec.schedule_factor)
            completed = projected_end <= self.as_of
            dept_pms = pms[pms.department == spec.department].employee_id.tolist()
            rows.append({
                "project_id": pid,
                "project_name": spec.name,
                "description": spec.description,
                "project_manager_id": dept_pms[spec.pm_index % len(dept_pms)],
                "department": spec.department,
                "start_date": start,
                "planned_end_date": planned_end,
                "actual_end_date": projected_end if completed else pd.NaT,
                "budget": float(BUDGETS[spec.name]),
                "actual_cost": 0.0,  # finalised from earned progress
                "status": "Completed" if completed else REPORTED_STATUS[spec.profile],
                "priority": spec.priority,
                # generation-only attributes
                "key": spec.key,
                "profile": spec.profile,
                "schedule_factor": spec.schedule_factor,
                "cost_factor": spec.cost_factor,
                "projected_end": projected_end,
                "sprint_window_start": start + _days(planned_days * 0.12),  # initiation phase
                "family": spec.family,
                "components": spec.components,
                "team_size": spec.team_size,
                "pm_index": spec.pm_index,
            })
        return pd.DataFrame(rows)

    def _assign_teams(self, employees: pd.DataFrame, projects: pd.DataFrame) -> None:
        """Staff each project, favouring its own department and people who are free."""
        rng = self.rng
        delivery = employees[employees.role != "Project Manager"]
        scrum_masters = delivery[delivery.role == "Scrum Master"].employee_id.to_numpy()
        others = delivery[delivery.role != "Scrum Master"]
        windows: dict[int, list[tuple[pd.Timestamp, pd.Timestamp]]] = defaultdict(list)

        def overlap(eid: int, start, end) -> int:
            return sum(1 for s, e in windows[eid] if s <= end and start <= e)

        self.teams: dict[int, list[int]] = {}
        for p in projects.sort_values("start_date").itertuples():
            start, end = p.start_date, min(p.projected_end, self.as_of + pd.Timedelta(days=30))
            sm_load = np.array([overlap(e, start, end) for e in scrum_masters])
            sm = int(scrum_masters[rng.choice(np.flatnonzero(sm_load == sm_load.min()))])

            weights = np.array([
                (3.0 if dept == p.department else 1.0) / (1 + overlap(eid, start, end)) ** 2
                for eid, dept in zip(others.employee_id, others.department)
            ])
            picks = rng.choice(others.employee_id.to_numpy(), size=p.team_size - 1,
                               replace=False, p=weights / weights.sum())
            team = [sm] + [int(x) for x in picks]
            for eid in team:
                windows[eid].append((start, end))
            self.teams[p.project_id] = team
        self.windows = windows

    # ----------------------------------------------------------------- sprints
    def _sprints(self, projects: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        anchors, avail = {}, {}
        for p in projects.itertuples():
            if pd.notna(p.actual_end_date):
                anchor = p.actual_end_date - pd.Timedelta(days=14)  # hypercare after last sprint
            else:
                anchor = self.as_of  # an active sprint straddles the as-of date
            anchors[p.project_id] = anchor
            avail[p.project_id] = (anchor - p.sprint_window_start).days

        counts = _allocate(N_SPRINTS, list(avail.values()))
        rows = []
        for (pid, days), n in zip(avail.items(), counts):
            length = int(np.clip(round(days / n / 7) * 7, 14, 35))
            proj = projects.set_index("project_id").loc[pid]
            if pd.notna(proj.actual_end_date):
                last_end = anchors[pid]
            else:
                last_end = self.as_of + _days(rng.integers(4, length - 4))
            first_start = last_end - pd.Timedelta(days=n * length)
            first_start -= pd.Timedelta(days=first_start.weekday())  # Monday starts
            earliest = proj.start_date + pd.Timedelta(days=14)
            while first_start < earliest and length > 14:
                length -= 7
                first_start = last_end - pd.Timedelta(days=n * length)
                first_start -= pd.Timedelta(days=first_start.weekday())
            for k in range(n):
                s = first_start + pd.Timedelta(days=k * length)
                e = s + pd.Timedelta(days=length - 3)  # Monday -> Friday
                rows.append({
                    "project_id": pid,
                    "sprint_number": k + 1,
                    "sprint_name": f"{proj.key} Sprint {k + 1}",
                    "start_date": s,
                    "end_date": e,
                    "status": "Active" if s <= self.as_of <= e else "Closed",
                    "length_days": length,
                })
        sprints = pd.DataFrame(rows)
        # A sprint can only be in the future if it is the active one.
        sprints = sprints[sprints.start_date <= self.as_of]
        sprints = sprints.sort_values(["start_date", "project_id"]).reset_index(drop=True)
        sprints.insert(0, "sprint_id", np.arange(1, len(sprints) + 1))
        assert len(sprints) == N_SPRINTS, len(sprints)
        return sprints

    # ------------------------------------------------------------------- tasks
    def _tasks(self, employees, projects, sprints) -> pd.DataFrame:
        rng = self.rng
        emp = employees.set_index("employee_id")
        proj = projects.set_index("project_id")
        sm_ids = set(employees.loc[employees.role == "Scrum Master", "employee_id"])

        # project delivery windows, used to work out who is split across projects
        win = {pid: (g.start_date.min(), g.end_date.max()) for pid, g in sprints.groupby("project_id")}
        member_of = defaultdict(list)
        for pid, team in self.teams.items():
            for eid in team:
                member_of[eid].append(pid)

        # 1) planned hours per (sprint, member) cell
        cells = []
        for s in sprints.itertuples():
            p = proj.loc[s.project_id]
            prof = PROFILE[p.profile]
            mid = s.start_date + (s.end_date - s.start_date) / 2
            weeks = s.length_days / 7
            for eid in self.teams[s.project_id]:
                concurrent = sum(1 for q in member_of[eid] if win[q][0] <= mid <= win[q][1]) or 1
                factor = 0.45 if eid in sm_ids else 1.0
                target = (emp.at[eid, "weekly_capacity_hours"] * weeks * emp.at[eid, "util"]
                          * prof["load"] * factor / concurrent
                          * rng.normal(1.0, 0.06))
                cells.append((s.sprint_id, s.project_id, eid, max(target, 4.0)))
        cells = pd.DataFrame(cells, columns=["sprint_id", "project_id", "employee_id", "target"])

        # 2) split 10,000 tasks between sprint work and remaining backlog
        hours_p = cells.groupby("project_id").target.sum()
        backlog_ratio = {}
        for pid, p in proj.iterrows():
            if pd.notna(p.actual_end_date):
                backlog_ratio[pid] = 0.0
            else:
                ws = win[pid][0]
                done_frac = (self.as_of - ws).days / max((p.projected_end - ws).days, 1)
                done_frac = float(np.clip(done_frac, 0.05, 0.98))
                # Share of sprint work that will actually be Done by the as-of date:
                # the active sprint is only part-way through and late spill-over is open.
                n_sprints = (sprints.project_id == pid).sum()
                sprint_done = 1 - 0.55 / n_sprints - (1 - PROFILE[p.profile]["reliability"]) * 0.4
                backlog_ratio[pid] = max(sprint_done / done_frac - 1, 0.0)
        share = hours_p / hours_p.sum()
        n_sprint_total = N_TASKS / sum(share[pid] * (1 + backlog_ratio[pid]) for pid in share.index)
        sprint_counts = _allocate(int(round(n_sprint_total)), share.values)
        backlog_counts = np.array([int(round(c * backlog_ratio[pid]))
                                   for pid, c in zip(share.index, sprint_counts)])
        # absorb rounding so the grand total is exact
        diff = N_TASKS - sprint_counts.sum() - backlog_counts.sum()
        sprint_counts[np.argmax(sprint_counts)] += diff

        sprint_lookup = sprints.set_index("sprint_id")
        sprint_index = sprints.groupby("project_id").sprint_number.max()
        rows = []

        # 3) sprint tasks
        for pid, n_proj in zip(share.index, sprint_counts):
            p = proj.loc[pid]
            prof = PROFILE[p.profile]
            pc = cells[cells.project_id == pid].reset_index(drop=True)
            per_cell = _allocate(n_proj, pc.target.values)
            reliab = {}
            for sid in pc.sprint_id.unique():
                s = sprint_lookup.loc[sid]
                pos = (s.sprint_number - 1) / max(sprint_index[pid] - 1, 1)
                reliab[sid] = prof["reliability"] + prof["trend"] * pos ** 1.3 + rng.normal(0, 0.03)

            for cell, n in zip(pc.itertuples(), per_cell):
                if n == 0:
                    continue
                s = sprint_lookup.loc[cell.sprint_id]
                itypes = rng.choice(ISSUE_TYPES, size=n, p=ISSUE_PROBS)
                sps = np.array([rng.choice(FIB, p=SP_PROBS[t]) for t in itypes])
                raw = sps * HOURS_PER_SP * rng.lognormal(0, 0.3, size=n)
                planned = np.maximum(raw * cell.target / raw.sum(), 0.5)
                for itype, sp, ph in zip(itypes, sps, planned):
                    rows.append(self._sprint_task(p, prof, s, cell.employee_id, itype, int(sp),
                                                  float(ph), reliab[cell.sprint_id] +
                                                  emp.at[cell.employee_id, "skill"]))

        # 4) backlog (not yet in a sprint) for active projects
        for pid, n in zip(share.index, backlog_counts):
            p = proj.loc[pid]
            team = [e for e in self.teams[pid] if e not in sm_ids]
            for _ in range(n):
                rows.append(self._backlog_task(p, int(rng.choice(team))))

        tasks = pd.DataFrame(rows)
        tasks = tasks.sort_values(["created_date", "project_id"], kind="stable").reset_index(drop=True)
        tasks.insert(0, "task_id", np.arange(1, len(tasks) + 1))
        seq = tasks.groupby("project_id").cumcount() + 1
        keys = tasks.project_id.map(proj.key)
        tasks.insert(1, "task_key", keys + "-" + seq.astype(str))
        assert len(tasks) == N_TASKS, len(tasks)
        return tasks

    def _task_name(self, p, itype: str) -> str:
        comps = p.components
        i, j = self.rng.choice(len(comps), size=2, replace=False)
        tpl = self.rng.choice(TASK_TEMPLATES[p.family][itype])
        return tpl.format(c=comps[i], c2=comps[j])

    def _sprint_task(self, p, prof, s, eid, itype, sp, planned, reliability) -> dict:
        rng = self.rng
        start, end, length = s.start_date, s.end_date, s.length_days
        p_end = p.actual_end_date if pd.notna(p.actual_end_date) else self.as_of
        created = max(p.start_date, start - _days(rng.integers(0, 36)))
        size_penalty = 0.05 if sp >= 8 else 0.0
        p_done = float(np.clip(reliability - size_penalty, 0.30, 0.99))
        active = s.status == "Active"
        if active:  # only part of the sprint has elapsed
            frac = max((self.as_of - start).days / length, 0.05)
            p_done *= min(1.0, frac ** 1.15)
        cycle = max(1, int(round(rng.gamma(2.0, 0.55 + sp * 0.32))))

        status, started, completed = "Done", None, None
        horizon = min(end, self.as_of)
        if rng.random() < p_done:  # finished inside the sprint
            latest_start = max((horizon - start).days - cycle, 0)
            started = start + _days(rng.integers(0, latest_start + 1))
            completed = min(started + _days(cycle), horizon)
        elif not active:  # spill-over, finished later (or still open)
            started = start + _days(rng.uniform(0.3, 0.8) * length)
            completed = end + _days(rng.integers(2, 26))
            if completed > p_end:
                if pd.notna(p.actual_end_date):
                    completed = max(end + pd.Timedelta(days=1), p_end - pd.Timedelta(days=1))
                else:
                    completed, status = None, rng.choice(["In Progress", "In Review", "Blocked"],
                                                         p=[0.5, 0.3, 0.2])
        else:  # open item in the active sprint
            if rng.random() < 0.6:
                started = start + _days(rng.integers(0, max((self.as_of - start).days, 0) + 1))
                status = rng.choice(["In Progress", "In Review", "Blocked"], p=[0.55, 0.3, 0.15])
            else:
                status = "To Do"

        overrun = rng.lognormal(np.log(prof["overrun"]), 0.18)
        if status == "Done":
            actual = planned * overrun
        elif started is not None:
            actual = planned * overrun * rng.uniform(0.2, 0.8)
        else:
            actual = None
        return {
            "project_id": p.name,
            "sprint_id": s.name,
            "employee_id": eid,
            "task_name": self._task_name(p, itype),
            "issue_type": itype,
            "story_points": sp,
            "planned_hours": round(planned, 1),
            "actual_hours": None if actual is None else round(actual, 1),
            "status": status,
            "priority": rng.choice(PRIORITIES, p=PRIORITY_PROBS),
            "created_date": created,
            "started_date": started,
            "due_date": end,
            "completion_date": completed,
        }

    def _backlog_task(self, p, eid) -> dict:
        rng = self.rng
        itype = rng.choice(ISSUE_TYPES, p=ISSUE_PROBS)
        sp = int(rng.choice(FIB, p=SP_PROBS[itype]))
        span = (self.as_of - p.start_date).days
        created = p.start_date + _days(span * rng.beta(2.2, 1.2))
        status = rng.choice(["To Do", "In Progress", "Blocked"], p=[0.88, 0.08, 0.04])
        started = None
        if status != "To Do":
            started = created + _days(rng.integers(0, max((self.as_of - created).days, 0) + 1))
        planned = sp * HOURS_PER_SP * rng.lognormal(0, 0.3)
        return {
            "project_id": p.name,
            "sprint_id": None,
            "employee_id": eid,
            "task_name": self._task_name(p, itype),
            "issue_type": itype,
            "story_points": sp,
            "planned_hours": round(planned, 1),
            "actual_hours": round(planned * rng.uniform(0.1, 0.5), 1) if started else None,
            "status": status,
            "priority": rng.choice(PRIORITIES, p=PRIORITY_PROBS),
            "created_date": created,
            "started_date": started,
            "due_date": p.planned_end_date,
            "completion_date": None,
        }

    # -------------------------------------------------------------- finalising
    def _finalise_sprints(self, sprints: pd.DataFrame, tasks: pd.DataFrame) -> pd.DataFrame:
        t = tasks[tasks.sprint_id.notna()].merge(
            sprints[["sprint_id", "end_date"]], on="sprint_id")
        cutoff = t.end_date.where(t.end_date <= self.as_of, self.as_of)
        t["done_in_sprint"] = t.completion_date.notna() & (t.completion_date <= cutoff)
        agg = t.groupby("sprint_id").agg(
            planned_story_points=("story_points", "sum"),
            completed_story_points=("story_points", lambda x: x[t.loc[x.index, "done_in_sprint"]].sum()),
        )
        out = sprints.drop(columns=["length_days"]).merge(agg, on="sprint_id", how="left")
        out[["planned_story_points", "completed_story_points"]] = (
            out[["planned_story_points", "completed_story_points"]].fillna(0).astype(int))
        self._sprint_len = sprints.set_index("sprint_id").length_days
        return out

    def _finalise_projects(self, projects: pd.DataFrame, tasks: pd.DataFrame) -> pd.DataFrame:
        sp = tasks.groupby("project_id").story_points.sum()
        done = tasks[tasks.status == "Done"].groupby("project_id").story_points.sum()
        progress = (done / sp).reindex(projects.project_id).fillna(0).to_numpy()
        noise = self.rng.normal(1.0, 0.01, size=len(projects))
        projects = projects.copy()
        projects["actual_cost"] = np.round(
            projects.budget * progress * projects.cost_factor * noise, 2)
        return projects

    # ------------------------------------------------------------------- risks
    def _risks(self, employees, projects) -> pd.DataFrame:
        rng = self.rng
        emp = employees.set_index("employee_id")
        weights = []
        for p in projects.itertuples():
            end = p.actual_end_date if pd.notna(p.actual_end_date) else self.as_of
            weights.append(PROFILE[p.profile]["risk_weight"] * (end - p.start_date).days)
        counts = _allocate(N_RISKS, weights)

        prob_weights = {
            "healthy": [0.24, 0.32, 0.26, 0.13, 0.05],
            "watch": [0.12, 0.25, 0.30, 0.22, 0.11],
            "troubled": [0.05, 0.14, 0.28, 0.31, 0.22],
        }
        cats = list(RISK_CATEGORY_WEIGHTS)
        rows = []
        for p, n in zip(projects.itertuples(), counts):
            prof = PROFILE[p.profile]
            completed = pd.notna(p.actual_end_date)
            end = p.actual_end_date if completed else self.as_of
            span = (end - p.start_date).days
            team = self.teams[p.project_id] + [p.project_manager_id]
            for _ in range(n):
                skew = 0.75 if (p.profile == "troubled" and not completed) else 1.0
                identified = p.start_date + _days(span * rng.random() ** skew)
                identified = min(identified, end - pd.Timedelta(days=1))
                cat = rng.choice(cats, p=list(RISK_CATEGORY_WEIGHTS.values()))
                comps = p.components
                i, j = rng.choice(len(comps), size=2, replace=False)
                owner = int(rng.choice(team))
                desc = rng.choice(RISK_TEMPLATES[cat]).format(
                    c=comps[i], c2=comps[j], role=emp.at[owner, "role"].lower())
                prob = int(rng.choice([1, 2, 3, 4, 5], p=prob_weights[p.profile]))
                impact = int(rng.choice([1, 2, 3, 4, 5], p=prob_weights[p.profile]))
                age = (end - identified).days
                tau = prof["risk_tau"] * (1.25 if prob * impact >= 15 else 1.0)

                if completed:
                    closed = True
                else:
                    closed = rng.random() < 1 - np.exp(-age / tau)
                if closed:
                    status = "Accepted" if (prob * impact <= 6 and rng.random() < 0.25) else "Closed"
                    delay = rng.exponential(tau)
                    if delay >= age:  # closed before the as-of date, so re-draw inside the window
                        delay = rng.uniform(0.15, 0.95) * age
                    resolved = identified + _days(max(1, delay))
                    mitigation = 100
                else:
                    p_mitigating = 0.55 if p.profile == "healthy" else 0.40
                    if rng.random() < p_mitigating:
                        status, mitigation = "Mitigating", int(rng.integers(25, 91))
                    else:
                        status, mitigation = "Open", int(rng.integers(0, 21))
                    resolved = pd.NaT
                rows.append({
                    "project_id": p.project_id,
                    "category": cat,
                    "risk_description": desc,
                    "probability": prob,
                    "impact": impact,
                    "risk_score": prob * impact,
                    "owner_id": owner,
                    "status": status,
                    "identified_date": identified,
                    "resolved_date": resolved,
                    "mitigation_progress": mitigation,
                })
        risks = pd.DataFrame(rows).sort_values("identified_date").reset_index(drop=True)
        risks.insert(0, "risk_id", np.arange(1, len(risks) + 1))
        assert len(risks) == N_RISKS
        return risks

    # -------------------------------------------------------------- ceremonies
    def _ceremonies(self, projects, sprints) -> pd.DataFrame:
        rng = self.rng
        proj = projects.set_index("project_id")
        last = sprints.groupby("project_id").sprint_number.max()

        def record(s, ctype, day):
            p = proj.loc[s.project_id]
            prof = PROFILE[p.profile]
            pos = (s.sprint_number - 1) / max(last[s.project_id] - 1, 1)
            trend = (-0.10 * pos) if p.profile == "troubled" else (-0.03 * pos)
            standup_adj = -0.03 if ctype == "Daily Standup" else 0.0
            attendance = float(np.clip(prof["attendance"] + trend + standup_adj
                                       + rng.normal(0, 0.04), 0.5, 1.0))
            weeks = self._sprint_len[s.sprint_id] / 7
            troubled = p.profile == "troubled"
            duration = {
                "Sprint Planning": rng.normal(55 * weeks, 15),
                "Daily Standup": rng.normal(19 if troubled else 15, 3),
                "Sprint Review": rng.normal(30 * weeks, 10),
                "Retrospective": rng.normal(22 * weeks + (15 if troubled else 0), 8),
            }[ctype]
            items_mean = {"Sprint Planning": 2.0, "Daily Standup": 0.7,
                          "Sprint Review": 2.5, "Retrospective": 4.0}[ctype]
            items_mean += 1.5 if troubled else (0.6 if p.profile == "watch" else 0)
            return {
                "project_id": s.project_id,
                "sprint_id": s.sprint_id,
                "ceremony_type": ctype,
                "ceremony_date": day,
                "attendance_rate": round(attendance, 3),
                "duration_minutes": int(max(5, round(duration))),
                "action_items": int(rng.poisson(items_mean)),
            }

        rows = []
        for s in sprints.itertuples():
            rows.append(record(s, "Sprint Planning", s.start_date))
            if s.end_date <= self.as_of:
                rows.append(record(s, "Sprint Review", s.end_date))
                rows.append(record(s, "Retrospective", s.end_date))
        # Daily stand-ups are sampled (one record = one observed stand-up) to fill to 500.
        n_standups = N_CEREMONIES - len(rows)
        picks = rng.choice(len(sprints), size=n_standups, replace=True)
        for i in picks:
            s = sprints.iloc[i]
            horizon = min(s.end_date, self.as_of)
            days = pd.bdate_range(s.start_date + pd.Timedelta(days=1), horizon)
            day = days[rng.integers(0, len(days))] if len(days) else s.start_date
            rows.append(record(s, "Daily Standup", day))
        out = pd.DataFrame(rows).sort_values(["ceremony_date", "project_id"]).reset_index(drop=True)
        out.insert(0, "ceremony_id", np.arange(1, len(out) + 1))
        assert len(out) == N_CEREMONIES
        return out

    # ------------------------------------------------------------- performance
    def _performance(self, tasks, sprints, projects) -> pd.DataFrame:
        rng = self.rng
        profile = projects.set_index("project_id").profile
        traits = self._traits
        t = tasks[tasks.sprint_id.notna()].merge(
            sprints[["sprint_id", "end_date"]], on="sprint_id")
        cutoff = t.end_date.where(t.end_date <= self.as_of, self.as_of)
        t["done"] = t.completion_date.notna() & (t.completion_date <= cutoff)
        t["sp_done"] = t.story_points.where(t.done, 0)
        g = t.groupby(["employee_id", "sprint_id", "project_id"]).agg(
            stories_assigned=("task_id", "count"),
            stories_completed=("done", "sum"),
            story_points_completed=("sp_done", "sum"),
        ).reset_index()
        q = {k: v["quality"] for k, v in PROFILE.items()}
        rate = (0.05 * g.stories_completed * g.employee_id.map(traits.quality)
                * g.project_id.map(profile).map(q))
        g["bugs_reopened"] = rng.poisson(rate.to_numpy())
        g["bugs_reopened"] = np.minimum(g.bugs_reopened, g.stories_completed)
        stress = g.project_id.map(profile).map({"healthy": 0.0, "watch": 0.08, "troubled": 0.2})
        g["peer_review_score"] = np.clip(
            g.employee_id.map(traits.collab) - stress + rng.normal(0, 0.3, len(g)), 1, 5).round(1)
        cols = ["employee_id", "sprint_id", "stories_assigned", "stories_completed",
                "story_points_completed", "bugs_reopened", "peer_review_score"]
        return g[cols].sort_values(["sprint_id", "employee_id"]).reset_index(drop=True)

    # ----------------------------------------------------------- ML training
    def _project_history(self) -> pd.DataFrame:
        """Archived mid-project snapshots (2019-2024) with known delay outcomes."""
        rng = self.rng
        n = N_HISTORY
        bu = np.clip(rng.normal(1.03, 0.09, n), 0.80, 1.45)
        risks = rng.poisson(rng.gamma(2.5, 2.4, n)).clip(0, 35)
        ru = np.clip(rng.normal(0.90, 0.13, n), 0.50, 1.40)
        vel = np.clip(rng.normal(200, 60, n), 50, 450)
        remaining = np.clip(rng.lognormal(5.0, 0.75, n), 5, 1200).round().astype(int)
        z = (-0.30 + 10.0 * (bu - 1.03) + 0.17 * (risks - 6) + 5.0 * (ru - 0.90)
             - 0.010 * (vel - 200) + 0.004 * (remaining - 150) + rng.normal(0, 0.9, n))
        delayed = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
        years = rng.integers(2019, 2025, n)
        depts = rng.choice(DEPARTMENTS, size=n, p=[0.36, 0.18, 0.16, 0.15, 0.15])
        return pd.DataFrame({
            "history_id": np.arange(1, n + 1),
            "project_code": [f"TN-{y % 100:02d}-{i:03d}" for i, y in enumerate(years, start=1)],
            "department": depts,
            "close_year": years,
            "budget_utilization": bu.round(3),
            "open_risks": risks,
            "avg_resource_utilization": ru.round(3),
            "sprint_velocity": vel.round(1),
            "tasks_remaining": remaining,
            "delayed": delayed,
        })


def generate_dataset(seed: int = config.RANDOM_SEED, as_of: str = config.DATA_AS_OF
                     ) -> dict[str, pd.DataFrame]:
    """Convenience wrapper: build every table and return ``{table_name: DataFrame}``."""
    gen = TechNovaGenerator(seed=seed, as_of=as_of)
    return gen.generate()
