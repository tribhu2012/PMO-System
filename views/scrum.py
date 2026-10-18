"""Page 5 - Scrum Analytics Dashboard."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from projectpulse import config, metrics
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import GRID, INK, SERIES, STATUS

CEREMONY_ORDER = ["Sprint Planning", "Daily Standup", "Sprint Review", "Retrospective"]

ctx = state.get_ctx()
ui.page_header("Scrum Analytics", "Velocity, predictability, flow and ceremony health", "Delivery", ctx)

sp = metrics.sprint_metrics(ctx.sprints, ctx.f.end)
sp["project_name"] = sp.project_id.map(ctx.project_names)
closed = sp[sp.is_closed]
if sp.empty:
    ui.empty_state("No sprints overlap the selected period.")
    st.stop()

tasks = ctx.tasks[ctx.tasks.sprint_id.isin(ctx.sprints.sprint_id)]
flow = metrics.task_flow_times(tasks)
flow = flow[flow.completion_date.between(ctx.f.start, ctx.f.end)]
reliability = closed.velocity.sum() / max(closed.planned_story_points.sum(), 1)
success = closed.successful.mean()

ui.kpi_grid([
    dict(label="Sprint Velocity", value=ui.fmt_num(closed.velocity.mean()), icon="speed",
         sub=f"Avg story points per sprint · {len(closed)} closed sprints"),
    dict(label="Commitment Reliability", value=ui.fmt_pct(reliability), icon="handshake",
         tone="good" if reliability >= config.SPRINT_SUCCESS_THRESHOLD else "warn",
         badge=ui.chip(f"≥ {config.SPRINT_SUCCESS_THRESHOLD:.0%}",
                       "good" if reliability >= config.SPRINT_SUCCESS_THRESHOLD else "warn"),
         sub="Completed ÷ committed story points"),
    dict(label="Attendance Rate", value=ui.fmt_pct(ctx.ceremonies.attendance_rate.mean()), icon="how_to_reg",
         tone="violet", sub=f"{len(ctx.ceremonies)} ceremonies recorded"),
    dict(label="Avg Cycle Time", value=f"{flow.cycle_time_days.mean():.1f} d" if len(flow) else "–",
         icon="autorenew", sub="Work started → done"),
    dict(label="Avg Lead Time", value=f"{flow.lead_time_days.mean():.1f} d" if len(flow) else "–",
         icon="timer", sub="Created → done"),
    dict(label="Sprint Success Rate", value=ui.fmt_pct(success), icon="emoji_events",
         tone="good" if success >= 0.6 else "warn",
         sub=f"Sprints delivering ≥ {config.SPRINT_SUCCESS_THRESHOLD:.0%} of commitment"),
])

# --------------------------------------------------------------------------- velocity
options = sp.groupby("project_name").size().sort_index().index.tolist()
with ui.card("velocity"):
    ctrl = ui.card_header("Velocity Trend",
                          "Committed vs completed story points per sprint, with a 3-sprint rolling average",
                          controls=0.26)
    proj = ctrl.selectbox("Project", options, key="scrum_project", label_visibility="collapsed",
                          index=options.index("Project Phoenix") if "Project Phoenix" in options else 0)
    ps = sp[sp.project_name == proj].sort_values("sprint_number")
    pclosed = ps[ps.is_closed]
    labels = ps.sprint_name.str.replace(r"^\w+ ", "", regex=True)
    fig = go.Figure()
    fig.add_bar(x=labels, y=ps.planned_story_points, name="Committed", marker_color="#c9dcf5",
                hovertemplate="%{x}<br>Committed %{y} SP<extra></extra>")
    fig.add_bar(x=labels, y=ps.velocity, name="Completed", marker_color=SERIES[0],
                hovertemplate="%{x}<br>Completed %{y} SP<extra></extra>")
    fig.add_scatter(x=labels[ps.is_closed.values], y=pclosed.velocity.rolling(3, min_periods=1).mean(),
                    name="Rolling avg (3)", mode="lines", line=dict(color=SERIES[1], width=2),
                    hovertemplate="%{x}<br>Rolling avg %{y:.0f} SP<extra></extra>")
    fig.update_layout(barmode="group", hovermode="x unified", yaxis_title="Story points")
    ui.chart(fig, height=300, key="velocity")

# --------------------------------------------------------------------------- burndown + success
H = 330
c1, c2 = ui.row(2)
with c1, ui.card("burndown"):
    ctrl = ui.card_header("Sprint Burndown", f"{proj} · remaining story points vs ideal", controls=0.36)
    sprint_labels = ps.sprint_name.tolist()
    pick = ctrl.selectbox("Sprint", sprint_labels, index=len(sprint_labels) - 1, key="burndown_sprint",
                          label_visibility="collapsed")
    srow = ps[ps.sprint_name == pick].iloc[0]
    bd = metrics.burndown(ctx.tasks, srow, ctx.f.end)
    fig = go.Figure()
    fig.add_scatter(x=bd.date, y=bd.ideal, name="Ideal", line=dict(color=INK["muted"], dash="dot"),
                    hovertemplate="%{x|%d %b}<br>Ideal %{y:.0f} SP<extra></extra>")
    fig.add_scatter(x=bd.date, y=bd.remaining, name="Remaining", line=dict(color=SERIES[0], shape="hv"),
                    fill="tozeroy", fillcolor="rgba(42,120,214,0.07)",
                    hovertemplate="%{x|%d %b}<br>Remaining %{y:.0f} SP<extra></extra>")
    fig.update_layout(hovermode="x unified", yaxis=dict(title="Story points", rangemode="tozero"))
    ui.chart(fig, height=H - 30, key="burndown")
    status = "in progress" if srow.status == "Active" else "closed"
    ui.note(f"{srow.start_date:%d %b} – {srow.end_date:%d %b %Y} ({status}) · {srow.velocity} of "
            f"{srow.planned_story_points} SP completed ({srow.commitment_reliability:.0%})")

with c2, ui.card("success"):
    ui.card_header("Sprint Success Rate by Project",
                   f"Share of closed sprints delivering ≥ {config.SPRINT_SUCCESS_THRESHOLD:.0%} of commitment")
    rate = closed.groupby("project_name").agg(rate=("successful", "mean"), n=("sprint_id", "count"),
                                              rel=("commitment_reliability", "mean")).sort_values("rate")
    fig = go.Figure(go.Bar(
        x=rate.rate, y=rate.index.str.replace("Project ", ""), orientation="h", width=0.55,
        marker_color=[STATUS["critical"] if r < 0.5 else SERIES[0] for r in rate.rate],
        text=[f"{r:.0%}" for r in rate.rate], textposition="outside", cliponaxis=False,
        customdata=rate[["n", "rel"]].values,
        hovertemplate="%{y}<br>Success %{x:.0%} of %{customdata[0]} sprints<br>"
                      "Avg reliability %{customdata[1]:.0%}<extra></extra>"))
    fig.update_layout(xaxis=dict(range=[0, 1.15], tickformat=".0%", showgrid=True, gridcolor=GRID),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)"), margin=dict(t=8))
    ui.chart(fig, height=H - 30, key="success")
    ui.note("Red = fewer than half of sprints successful.")

# --------------------------------------------------------------------------- trends
H2 = 290
c1, c2 = ui.row(2)
with c1, ui.card("sp_trend"):
    ui.card_header("Story Point Completion Trend", "Story points completed per month, all projects in scope")
    done = ctx.tasks[(ctx.tasks.status == "Done") & ctx.tasks.completion_date.between(ctx.f.start, ctx.f.end)]
    m = done.groupby(done.completion_date.dt.to_period("M").dt.to_timestamp()).story_points.sum()
    fig = go.Figure()
    fig.add_scatter(x=m.index, y=m.values, name="Completed", line=dict(color=SERIES[0]),
                    mode="lines+markers", fill="tozeroy", fillcolor="rgba(42,120,214,0.07)",
                    marker=dict(size=7, line=dict(color="#fff", width=1.5)),
                    hovertemplate="%{x|%b %Y}<br>Completed %{y:,} SP<extra></extra>")
    fig.update_layout(hovermode="x unified", yaxis=dict(title="Story points", rangemode="tozero"),
                      showlegend=False, margin=dict(t=8))
    ui.chart(fig, height=H2, key="sp_trend")

with c2, ui.card("attendance"):
    ui.card_header("Ceremony Attendance Trend", "Average attendance per month by ceremony type")
    cer = ctx.ceremonies.assign(month=ctx.ceremonies.ceremony_date.dt.to_period("M").dt.to_timestamp())
    att = cer.groupby(["month", "ceremony_type"]).attendance_rate.mean().reset_index()
    fig = go.Figure()
    for i, ctype in enumerate(CEREMONY_ORDER):
        t = att[att.ceremony_type == ctype]
        fig.add_scatter(x=t.month, y=t.attendance_rate, name=ctype, mode="lines+markers",
                        line=dict(color=SERIES[i]), marker=dict(size=6),
                        hovertemplate="%{x|%b %Y}<br>" + ctype + ": %{y:.0%}<extra></extra>")
    fig.update_layout(hovermode="x unified", yaxis=dict(tickformat=".0%", range=[0.5, 1.02]))
    ui.chart(fig, height=H2, key="attendance")

# --------------------------------------------------------------------------- ceremony table
with ui.card("ceremonies"):
    ctrl = ui.card_header("Ceremony Summary", "Daily stand-ups are sampled observations", controls=0.2)
    summary = (ctx.ceremonies.groupby("ceremony_type")
               .agg(records=("ceremony_id", "count"), attendance=("attendance_rate", "mean"),
                    avg_duration=("duration_minutes", "mean"), action_items=("action_items", "sum"),
                    items_per_meeting=("action_items", "mean"))
               .reindex(CEREMONY_ORDER).dropna(how="all").reset_index())
    summary["attendance"] = summary.attendance * 100
    with ctrl:
        ui.csv_download(sp.drop(columns=["is_closed"]).round({"commitment_reliability": 3}),
                        f"sprints_{ctx.as_of}.csv", "Export sprints")
    st.dataframe(summary, hide_index=True, width="stretch", height="content", column_config={
        "ceremony_type": "Ceremony", "records": "Records",
        "attendance": st.column_config.ProgressColumn("Attendance", min_value=0, max_value=100, format="%.0f%%"),
        "avg_duration": st.column_config.NumberColumn("Avg duration (min)", format="%.0f"),
        "action_items": "Action items",
        "items_per_meeting": st.column_config.NumberColumn("Items / meeting", format="%.1f"),
    })
