"""Data loading, caching, global filters and the per-page filtered context."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st

from .. import config, metrics, ml
from ..database import create_schema, create_views, database_ready, get_engine, load_tables, read_all

PERIODS = {
    "Last 3 months": 3,
    "Last 6 months": 6,
    "Last 12 months": 12,
    "Full history (24 months)": 24,
    "Custom range": None,
}
DEFAULT_PERIOD = "Last 12 months"


# --------------------------------------------------------------------------- data
def _version() -> int:
    return st.session_state.setdefault("data_version", 0)


def bootstrap_database() -> None:
    """Generate the synthetic data set and load it (used by the in-app setup button)."""
    from ..data_generator import generate_dataset

    engine = get_engine()
    create_schema(engine)
    load_tables(engine, generate_dataset())
    create_views(engine)


@st.cache_resource(show_spinner="Loading portfolio data…")
def _load(version: int) -> dict[str, pd.DataFrame]:
    return read_all(get_engine())


def load_data() -> dict[str, pd.DataFrame]:
    engine = get_engine()
    if not database_ready(engine):
        if engine.dialect.name == "sqlite":
            with st.spinner("First run: generating TechNova Solutions demo data…"):
                bootstrap_database()
        else:
            st.error("The database is empty. Run `python scripts/load_data.py` "
                     "or use the button below.")
            if st.button("Generate & load demo data", type="primary"):
                with st.spinner("Generating 10,000 tasks and loading PostgreSQL…"):
                    bootstrap_database()
                st.rerun()
            st.stop()
    return _load(_version())


def refresh_data() -> None:
    st.session_state.data_version = _version() + 1
    st.cache_data.clear()


@st.cache_data(show_spinner=False)
def daily_assignment(_data, version: int) -> pd.DataFrame:
    return metrics.daily_assignment(_data["tasks"], _data["sprints"])


@st.cache_data(show_spinner="Computing project metrics…")
def project_metrics(_data, as_of: str, version: int) -> pd.DataFrame:
    return metrics.project_metrics(_data, as_of, daily_assignment(_data, version))


@st.cache_data(show_spinner="Replaying portfolio history…")
def health_trend(_data, start: str, end: str, version: int) -> pd.DataFrame:
    """Portfolio and per-project health at each month-end in the window."""
    rows = []
    month_ends = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="ME")
    if len(month_ends) == 0 or month_ends[-1] < pd.Timestamp(end):
        month_ends = month_ends.append(pd.DatetimeIndex([pd.Timestamp(end)]))
    for d in month_ends:
        pm = project_metrics(_data, d.strftime("%Y-%m-%d"), version)
        pm = pm[pm.status_as_of != "Completed"]
        for r in pm.itertuples():
            rows.append({"date": d, "project_id": r.project_id, "project_name": r.project_name,
                         "health_score": r.health_score, "budget": r.budget})
    return pd.DataFrame(rows)


@st.cache_resource(show_spinner="Training delay-prediction model…")
def delay_model(_data, version: int) -> ml.DelayModel:
    model = ml.load()
    if model is None or version > 0:
        model = ml.train(_data["project_history"])
        ml.save(model)
    return model


# --------------------------------------------------------------------------- filters
@dataclass
class Filters:
    start: pd.Timestamp
    end: pd.Timestamp
    departments: list[str]
    project_ids: list[int]
    period: str
    dept_all: bool = True
    project_labels: list[str] | None = None

    @property
    def label(self) -> str:
        return f"{self.start:%d %b %Y} – {self.end:%d %b %Y}"


def sidebar_filters(data: dict[str, pd.DataFrame]) -> Filters:
    projects = data["projects"]
    data_end = metrics.data_as_of(data)
    history_start = (data_end - pd.DateOffset(months=config.HISTORY_MONTHS) + pd.Timedelta(days=1)).normalize()

    # Defaults live in session state (not on the widgets) so "Reset" can overwrite them cleanly.
    st.session_state.setdefault("f_period", DEFAULT_PERIOD)
    st.session_state.setdefault("f_depts", [])
    st.session_state.setdefault("f_projects", [])
    with st.sidebar:
        head, reset = st.columns([3, 2], vertical_alignment="center")
        head.markdown("<div class='pp-side-title'>Filters</div>", unsafe_allow_html=True)
        reset.button("Reset", icon=":material/restart_alt:", type="tertiary", key="f_reset",
                     on_click=_reset_filters, help="Back to the last 12 months, all departments and projects")
        period = st.selectbox("Period", list(PERIODS), key="f_period")
        months = PERIODS[period]
        if months is None:
            rng = st.date_input("Date range", value=(history_start.date(), data_end.date()),
                                min_value=history_start.date(), max_value=data_end.date(),
                                key="f_dates", format="YYYY-MM-DD")
            start, end = (rng if isinstance(rng, (tuple, list)) and len(rng) == 2
                          else (history_start.date(), data_end.date()))
            start, end = pd.Timestamp(start), pd.Timestamp(end)
        else:
            end = data_end
            start = max(history_start, (end - pd.DateOffset(months=months) + pd.Timedelta(days=1)).normalize())

        depts = sorted(projects.department.unique())
        sel_depts = st.multiselect("Department", depts, key="f_depts",
                                   placeholder="All departments")
        sel_depts = sel_depts or depts
        options = projects[projects.department.isin(sel_depts)].sort_values("project_name")
        names = options.project_name.tolist()
        st.session_state.f_projects = [n for n in st.session_state.f_projects if n in names]
        sel_names = st.multiselect("Project", names, key="f_projects",
                                   placeholder="All projects")
        sel_ids = options[options.project_name.isin(sel_names or names)].project_id.tolist()
    return Filters(start, end, sel_depts, sel_ids, period,
                   dept_all=len(sel_depts) == len(depts), project_labels=sel_names)


def _reset_filters() -> None:
    st.session_state.f_period = DEFAULT_PERIOD
    st.session_state.f_depts = []
    st.session_state.f_projects = []


# --------------------------------------------------------------------------- page context
@dataclass
class PageContext:
    data: dict[str, pd.DataFrame]
    f: Filters
    version: int
    data_end: pd.Timestamp
    projects: pd.DataFrame  # filtered projects (started by end of window)
    pm: pd.DataFrame  # project metrics as of window end, filtered
    tasks: pd.DataFrame
    sprints: pd.DataFrame  # sprints overlapping the window
    risks: pd.DataFrame
    ceremonies: pd.DataFrame
    performance: pd.DataFrame
    employees: pd.DataFrame  # people in scope (department / project filter)
    daily: pd.DataFrame

    @property
    def as_of(self) -> str:
        return self.f.end.strftime("%Y-%m-%d")

    @property
    def project_names(self) -> dict[int, str]:
        return dict(zip(self.data["projects"].project_id, self.data["projects"].project_name))


def build_context(data: dict[str, pd.DataFrame], f: Filters) -> PageContext:
    version = _version()
    p = data["projects"]
    projects = p[p.project_id.isin(f.project_ids) & (p.start_date <= f.end)]
    ids = set(projects.project_id)
    pm = project_metrics(data, f.end.strftime("%Y-%m-%d"), version)
    pm = pm[pm.project_id.isin(ids)].reset_index(drop=True)

    tasks = data["tasks"][data["tasks"].project_id.isin(ids)]
    s = data["sprints"]
    sprints = s[s.project_id.isin(ids) & (s.start_date <= f.end) & (s.end_date >= f.start)]
    risks = data["risks"][data["risks"].project_id.isin(ids)]
    c = data["scrum_ceremonies"]
    ceremonies = c[c.project_id.isin(ids) & c.ceremony_date.between(f.start, f.end)]
    perf = data["performance"][data["performance"].sprint_id.isin(sprints.sprint_id)]

    e = data["employees"]
    employees = e[e.department.isin(f.departments)]
    all_projects = len(f.project_ids) == len(p[p.department.isin(f.departments)])
    if not all_projects:
        workers = tasks.employee_id.dropna().astype(int).unique()
        employees = employees[employees.employee_id.isin(workers)]

    return PageContext(data, f, version, metrics.data_as_of(data), projects, pm, tasks, sprints,
                       risks, ceremonies, perf, employees, daily_assignment(data, version))


def get_ctx() -> PageContext:
    ctx = st.session_state.get("ctx")
    if ctx is None:  # page opened directly before app.py populated state
        st.error("Open the app through `streamlit run app.py`.")
        st.stop()
    return ctx


def delivery_staff(employees: pd.DataFrame) -> pd.DataFrame:
    """Utilisation is measured for delivery roles; project managers are excluded."""
    return employees[employees.role != "Project Manager"]


def active_window_util(ctx: PageContext) -> pd.DataFrame:
    staff = delivery_staff(ctx.employees)
    return metrics.utilisation_by_employee(ctx.daily, staff, ctx.f.start, ctx.f.end)


def safe_mean(s: pd.Series) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.mean()) if len(s) else np.nan
