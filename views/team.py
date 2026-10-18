"""Page 6 - Team Performance Dashboard."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from projectpulse import config, metrics
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import GRID, INK, SERIES

ctx = state.get_ctx()
ui.page_header("Team Performance", "Delivery, quality and collaboration by person and department",
               "Delivery", ctx)

perf = metrics.employee_performance(ctx.tasks, ctx.performance, ctx.sprints, ctx.employees)
perf = perf[perf.employee_id.isin(ctx.employees.employee_id)]
if perf.empty:
    ui.empty_state()
    st.stop()

w = config.PERFORMANCE_WEIGHTS
totals = perf[["tasks_assigned", "tasks_completed", "on_time", "story_points_delivered",
               "bugs_reopened", "stories_completed"]].sum()
ui.kpi_grid([
    dict(label="Task Completion Rate", value=ui.fmt_pct(totals.tasks_completed / totals.tasks_assigned),
         icon="task_alt", tone="good",
         sub=f"{int(totals.tasks_completed):,} of {int(totals.tasks_assigned):,} sprint tasks"),
    dict(label="Story Points Delivered", value=f"{int(totals.story_points_delivered):,}", icon="bolt",
         sub=f"{perf.story_points_delivered.mean():.0f} SP per person"),
    dict(label="On-Time Delivery", value=ui.fmt_pct(totals.on_time / max(totals.tasks_completed, 1)),
         icon="event_available", sub="Done on or before sprint end"),
    dict(label="Defect Rate", value=ui.fmt_pct(totals.bugs_reopened / max(totals.stories_completed, 1), 1),
         icon="bug_report", tone="warn", sub=f"{int(totals.bugs_reopened)} bugs reopened"),
    dict(label="Peer Review Score", value=f"{perf.peer_review_score.mean():.2f}", icon="reviews",
         tone="violet", sub="Average out of 5 across sprints"),
    dict(label="Performance Score", value=f"{perf.performance_score.mean():.0f}", icon="military_tech",
         sub=f"{(perf.performance_score >= 85).sum()} people at 85 or above"),
])

# --------------------------------------------------------------------------- charts
H = 400
c1, c2 = ui.row([3, 2])
with c1, ui.card("top"):
    ui.card_header("Top Performers", f"Top 10 by performance score · {w['task_completion']:.0%} completion + "
                   f"{w['on_time']:.0%} on-time + {w['sprint_contribution']:.0%} contribution + "
                   f"{w['collaboration']:.0%} collaboration")
    top = perf.head(10).iloc[::-1]
    parts = [
        ("Task completion", w["task_completion"] * top.task_completion_rate * 100, SERIES[0]),
        ("On-time", w["on_time"] * top.on_time_rate * 100, SERIES[1]),
        ("Sprint contribution", w["sprint_contribution"] * top.sprint_contribution, SERIES[2]),
        ("Collaboration", w["collaboration"] * top.collaboration, SERIES[3]),
    ]
    labels = [f"{n} · {d[:3]}" for n, d in zip(top.employee_name, top.department)]
    fig = go.Figure()
    for name, vals, color in parts:
        fig.add_bar(y=labels, x=vals, name=name, orientation="h",
                    marker=dict(color=color, line=dict(color="#fff", width=1.5)),
                    hovertemplate="%{y}<br>" + name + ": %{x:.1f} pts<extra></extra>")
    fig.add_scatter(y=labels, x=top.performance_score + 1.5, mode="text",
                    text=top.performance_score.round(0).astype(int).astype(str),
                    textposition="middle right", showlegend=False, hoverinfo="skip",
                    textfont=dict(color=INK["primary"], size=11.5))
    fig.update_layout(barmode="stack", bargap=0.32, xaxis=dict(range=[0, 108], showgrid=True, gridcolor=GRID),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)"))
    ui.chart(fig, height=H, key="top_perf")

with c2, ui.card("dist"):
    ui.card_header("Performance Distribution", "Number of people per 4-point score band")
    fig = go.Figure(go.Histogram(
        x=perf.performance_score, xbins=dict(start=40, end=100, size=4), marker_color=SERIES[0],
        marker_line=dict(color="#fff", width=2),
        hovertemplate="Score %{x}<br>%{y} people<extra></extra>"))
    med = perf.performance_score.median()
    fig.add_vline(x=med, line=dict(color=INK["primary"], dash="dot", width=1.5))
    fig.add_annotation(x=med, y=1.03, yref="paper", text=f"median {med:.0f}", showarrow=False,
                       font=dict(size=11, color=INK["secondary"]))
    fig.update_layout(xaxis_title="Performance score", yaxis_title="People", bargap=0.04)
    ui.chart(fig, height=H, key="dist")

dept = perf.groupby("department").agg(
    score=("performance_score", "mean"), completion=("task_completion_rate", "mean"),
    on_time=("on_time_rate", "mean"), defect=("defect_rate", "mean"),
    peer=("peer_review_score", "mean"), people=("employee_id", "count")).reset_index()
dept = dept.sort_values("score", ascending=False)
H2 = 260
c1, c2 = ui.row([1, 1])
with c1, ui.card("dept_chart"):
    ui.card_header("Department Comparison", "Average performance score per department")
    fig = go.Figure(go.Bar(
        y=dept.department, x=dept.score, orientation="h", marker_color=SERIES[0], width=0.55,
        text=dept.score.round(0), textposition="outside", cliponaxis=False, customdata=dept.people,
        hovertemplate="%{y}<br>Avg score %{x:.1f} · %{customdata} people<extra></extra>"))
    fig.update_layout(xaxis=dict(range=[0, 108], showgrid=True, gridcolor=GRID),
                      yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"), margin=dict(t=8))
    ui.chart(fig, height=H2, key="dept_score")
with c2, ui.card("dept_table"):
    ui.card_header("Department KPIs", "Averages across people in scope")
    tbl = dept.assign(completion=dept.completion * 100, on_time=dept.on_time * 100, defect=dept.defect * 100)
    st.dataframe(tbl, hide_index=True, width="stretch", height="content", column_config={
        "department": "Department", "people": "People",
        "score": st.column_config.NumberColumn("Score", format="%.1f"),
        "completion": st.column_config.NumberColumn("Completion", format="%.0f%%"),
        "on_time": st.column_config.NumberColumn("On-time", format="%.0f%%"),
        "defect": st.column_config.NumberColumn("Defects", format="%.1f%%"),
        "peer": st.column_config.NumberColumn("Peer", format="%.2f"),
    })

# --------------------------------------------------------------------------- ranking
with ui.card("ranking"):
    ctrl = ui.card_header("Employee Ranking", "All people in scope, ranked by performance score", controls=0.18)
    view = perf.assign(
        band=perf.performance_score.map(metrics.performance_band),
        task_completion_rate=perf.task_completion_rate * 100,
        on_time_rate=perf.on_time_rate * 100,
        defect_rate=perf.defect_rate * 100,
    )[["rank", "employee_name", "department", "role", "sprints", "tasks_assigned", "tasks_completed",
       "story_points_delivered", "task_completion_rate", "on_time_rate", "defect_rate",
       "peer_review_score", "performance_score", "band"]]
    with ctrl:
        ui.csv_download(view.round(2), f"employee_performance_{ctx.as_of}.csv")
    st.dataframe(view, hide_index=True, width="stretch", height=460, column_config={
        "rank": st.column_config.NumberColumn("#", width="small"),
        "employee_name": "Employee", "department": "Department", "role": "Role",
        "sprints": "Sprints", "tasks_assigned": "Assigned", "tasks_completed": "Done",
        "story_points_delivered": st.column_config.NumberColumn("SP delivered", format="%d"),
        "task_completion_rate": st.column_config.NumberColumn("Completion", format="%.0f%%"),
        "on_time_rate": st.column_config.NumberColumn("On-time", format="%.0f%%"),
        "defect_rate": st.column_config.NumberColumn("Defects", format="%.1f%%"),
        "peer_review_score": st.column_config.NumberColumn("Peer", format="%.2f"),
        "performance_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
        "band": "Band",
    })
