"""Tests for the data generator, metrics, ML and insights engine.

Run:  pytest -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from projectpulse import config, insights, metrics, ml
from projectpulse.data_generator import generate_dataset
from projectpulse.database import create_schema, get_engine, load_tables, prepare, read_all


@pytest.fixture(scope="session")
def data() -> dict[str, pd.DataFrame]:
    return prepare(generate_dataset())


@pytest.fixture(scope="session")
def pm(data) -> pd.DataFrame:
    return metrics.project_metrics(data, metrics.data_as_of(data))


# --------------------------------------------------------------------------- generator
def test_volumes_match_brief(data):
    expected = {"projects": 12, "employees": 75, "tasks": 10_000, "sprints": 120, "risks": 300,
                "scrum_ceremonies": 500}
    for table, n in expected.items():
        assert len(data[table]) == n, table


def test_history_spans_24_months(data):
    start = data["projects"].start_date.min()
    end = metrics.data_as_of(data)
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    assert months == 24


def test_generator_is_deterministic():
    a, b = generate_dataset(seed=11), generate_dataset(seed=11)
    pd.testing.assert_frame_equal(a["tasks"], b["tasks"])


def test_departments(data):
    assert set(data["employees"].department) == {
        "Engineering", "Data Analytics", "Product Management", "Marketing", "Operations"}


def test_referential_integrity(data):
    emp = set(data["employees"].employee_id)
    proj = set(data["projects"].project_id)
    spr = set(data["sprints"].sprint_id)
    t = data["tasks"]
    assert set(t.project_id) <= proj
    assert set(t.sprint_id.dropna().astype(int)) <= spr
    assert set(t.employee_id.dropna().astype(int)) <= emp
    assert set(data["risks"].owner_id) <= emp
    assert set(data["projects"].project_manager_id) <= emp
    assert not data["performance"].duplicated(["employee_id", "sprint_id"]).any()


def test_sprint_points_derived_from_tasks(data):
    t = data["tasks"].dropna(subset=["sprint_id"])
    planned = t.groupby("sprint_id").story_points.sum()
    s = data["sprints"].set_index("sprint_id")
    assert (s.planned_story_points == planned.reindex(s.index).fillna(0)).all()
    assert (s.completed_story_points <= s.planned_story_points).all()


def test_task_dates_are_consistent(data):
    t = data["tasks"]
    done = t[t.status == "Done"]
    assert done.completion_date.notna().all()
    assert (done.completion_date >= done.created_date).all()
    assert (done.completion_date >= done.started_date).all()
    assert t[t.status != "Done"].completion_date.isna().all()
    assert (t.completion_date.dropna() <= metrics.data_as_of(data)).all()


def test_risk_scores(data):
    r = data["risks"]
    assert (r.risk_score == r.probability * r.impact).all()
    closed = r[r.status.isin(["Closed", "Accepted"])]
    assert closed.resolved_date.notna().all()
    assert r[r.status.isin(["Open", "Mitigating"])].resolved_date.isna().all()


# --------------------------------------------------------------------------- metrics
def test_health_formula_weights(pm):
    w = config.HEALTH_WEIGHTS
    expected = w["schedule"] * pm.schedule_health + w["budget"] * pm.budget_health + w["risk"] * pm.risk_health
    np.testing.assert_allclose(pm.health_score, expected)
    assert pm.health_score.between(0, 100).all()


@pytest.mark.parametrize("score,band", [(95, "Green"), (80, "Green"), (79.9, "Yellow"),
                                        (60, "Yellow"), (59.9, "Red"), (np.nan, "Grey")])
def test_rag_bands(score, band):
    assert metrics.rag(score) == band


def test_component_scores():
    assert metrics.schedule_health(1.1) == 100
    assert metrics.schedule_health(0.8) == pytest.approx(50)
    assert metrics.budget_health(1.0) == 100
    assert metrics.budget_health(0.8) == pytest.approx(25)
    assert metrics.risk_health(0) == 100
    assert metrics.risk_health(200) < metrics.risk_health(50)


def test_evm_identities(pm):
    np.testing.assert_allclose(pm.cost_variance, pm.ev - pm.ac)
    np.testing.assert_allclose(pm.schedule_variance, pm.ev - pm.pv)
    active = pm[pm.status_as_of != "Completed"]
    np.testing.assert_allclose(active.cpi, active.ev / active.ac)


def test_cost_to_date_matches_actual_cost_at_snapshot(data, pm):
    actual = data["projects"].set_index("project_id").actual_cost
    np.testing.assert_allclose(pm.set_index("project_id").ac, actual.loc[pm.project_id], rtol=1e-6)


def test_portfolio_story(pm):
    """The generated portfolio should contain healthy, watch and troubled projects."""
    bands = set(pm.rag)
    assert {"Green", "Yellow", "Red"} <= bands
    worst = pm.nsmallest(2, "health_score").project_name.tolist()
    assert set(worst) == {"Project Titan", "Project Phoenix"}


def test_as_of_replay(data):
    early = metrics.project_metrics(data, "2025-06-30")
    assert len(early) < 12
    assert early.progress.between(0, 1).all()


def test_utilisation(data):
    daily = metrics.daily_assignment(data["tasks"], data["sprints"])
    in_sprints = data["tasks"].dropna(subset=["sprint_id"]).planned_hours.sum()
    assert daily.hours.sum() == pytest.approx(in_sprints, rel=1e-6)
    u = metrics.utilisation_by_employee(daily, data["employees"], "2026-07-01", "2026-09-30")
    assert (u.utilization >= 0).all()
    assert (u.utilization > config.OVERLOAD_THRESHOLD).any()


def test_employee_performance_score(data):
    perf = metrics.employee_performance(data["tasks"], data["performance"], data["sprints"],
                                        data["employees"])
    assert perf.performance_score.between(0, 100).all()
    assert perf["rank"].is_monotonic_increasing
    assert perf.task_completion_rate.between(0, 1).all()


def test_burndown_reaches_completed_points(data):
    sprint = data["sprints"].iloc[10]
    bd = metrics.burndown(data["tasks"], sprint)
    assert bd.remaining.iloc[0] <= sprint.planned_story_points
    assert bd.ideal.iloc[-1] == 0


# --------------------------------------------------------------------------- ml
@pytest.fixture(scope="session")
def model(data) -> ml.DelayModel:
    return ml.train(data["project_history"])


def test_model_quality(model):
    assert model.metrics["roc_auc"] > 0.7
    assert model.confusion.sum() == model.n_test
    assert set(model.importance.feature) == set(ml.FEATURES)


def test_model_ranks_troubled_projects_highest(model, pm):
    active = pm[pm.status_as_of != "Completed"]
    scored = model.score_frame(ml.current_features(active))
    top2 = scored.nlargest(2, "delay_probability").project_name.tolist()
    assert set(top2) == {"Project Titan", "Project Phoenix"}
    assert scored.delay_probability.between(0, 1).all()


@pytest.mark.parametrize("p,label", [(0.1, "Low Risk"), (0.5, "Medium Risk"), (0.9, "High Risk")])
def test_delay_classes(p, label):
    assert metrics.classify_delay(p) == label


# --------------------------------------------------------------------------- insights
@pytest.fixture(scope="session")
def ictx(data, pm, model) -> insights.InsightContext:
    active = pm.status_as_of != "Completed"
    scored = model.score_frame(ml.current_features(pm[active]))
    pmx = pm.merge(scored[["project_id", "delay_probability", "risk_class"]], on="project_id", how="left")
    as_of = metrics.data_as_of(data)
    o = metrics.open_risks_as_of(data["risks"], as_of).copy()
    o["project_name"] = o.project_id.map(pm.set_index("project_id").project_name)
    daily = metrics.daily_assignment(data["tasks"], data["sprints"])
    util = metrics.utilisation_by_employee(daily, data["employees"], as_of - pd.Timedelta(weeks=8), as_of)
    team = {int(k): list(v) for k, v in daily.groupby("project_id").employee_id.unique().items()}
    return insights.InsightContext(pmx, o, util, data["tasks"], team)


def test_diagnosis_for_unhealthy_project(ictx):
    row = ictx.project("Project Phoenix")
    diag = insights.diagnose(row, ictx)
    text = diag.to_markdown()
    assert "health score" in text and "Recommendations" in text
    assert diag.rag == "Red"
    assert len(diag.drivers) >= 3


@pytest.mark.parametrize("question,expected", [
    ("Why is Project Phoenix unhealthy?", "Project Phoenix"),
    ("compare orion and titan", "| Metric |"),
    ("give me an executive summary", "Portfolio health"),
    ("who is overloaded?", "overloaded"),
    ("which projects are likely to be delayed", "Delay probability"),
    ("hello", "I can explain"),
])
def test_chat_router(ictx, question, expected):
    assert expected in insights.answer(question, ictx)


# --------------------------------------------------------------------------- database
def test_round_trip_sqlite(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'pp.db'}")
    tables = generate_dataset()
    create_schema(engine)
    counts = load_tables(engine, tables)
    assert counts["tasks"] == 10_000
    back = read_all(engine)
    assert len(back["risks"]) == 300
    assert back["tasks"].completion_date.dtype.kind == "M"
