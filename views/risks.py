"""Page 4 - Risk Management."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from projectpulse import config, metrics
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import GRID, INK, SEQ_BLUE, SERIES, SEVERITY_COLORS, STATUS

ctx = state.get_ctx()
ui.page_header("Risk Management", "Risk register, exposure and mitigation progress", "Delivery", ctx)

names = ctx.project_names
emp = ctx.data["employees"].set_index("employee_id").employee_name
risks = ctx.risks.copy()
if risks.empty:
    ui.empty_state()
    st.stop()
risks["project_name"] = risks.project_id.map(names)
risks["owner"] = risks.owner_id.map(emp)
risks["severity"] = risks.risk_score.map(metrics.risk_severity)

open_r = metrics.open_risks_as_of(risks, ctx.f.end).copy()
open_r["age_days"] = (ctx.f.end - open_r.identified_date).dt.days
in_window = risks[risks.identified_date.between(ctx.f.start, ctx.f.end)]
closed_window = risks[risks.resolved_date.between(ctx.f.start, ctx.f.end)]
high = open_r[open_r.risk_score >= config.HIGH_RISK_SCORE]
at_end = ctx.f.end >= ctx.data_end
mitigation = open_r.mitigation_progress.mean() / 100 if at_end and len(open_r) else np.nan
closure_rate = len(closed_window) / max(len(closed_window) + len(open_r), 1)

ui.kpi_grid([
    dict(label="Open Risks", value=f"{len(open_r)}", icon="warning",
         sub=f"{len(in_window)} raised · {len(closed_window)} resolved in period"),
    dict(label="High Risk Items", value=f"{len(high)}", icon="crisis_alert",
         tone="bad" if len(high) else "good",
         badge=ui.chip(f"score ≥ {config.HIGH_RISK_SCORE}", "bad" if len(high) else "good"),
         sub=f"{(high.status == 'Open').sum()} with no mitigation started" if len(high) else "None open"),
    dict(label="Mitigation Progress", value=ui.fmt_pct(mitigation), icon="shield", tone="violet",
         sub=f"{(open_r.status == 'Mitigating').sum()} of {len(open_r)} open risks being mitigated",
         help="Average mitigation completion across unresolved risks"),
    dict(label="Closure Rate", value=ui.fmt_pct(closure_rate), icon="task_alt", tone="good",
         sub="Resolved ÷ (resolved + still open)"),
    dict(label="Risk Exposure", value=f"{open_r.risk_score.sum():,.0f}", icon="stacked_bar_chart",
         sub="Σ probability × impact of open risks"),
    dict(label="Avg Age of Open Risks", value=f"{open_r.age_days.mean():.0f} d" if len(open_r) else "–",
         icon="hourglass_bottom", tone="warn" if len(open_r) and open_r.age_days.mean() > 60 else "accent",
         sub=f"{(open_r.age_days > 90).sum()} open for more than 90 days"),
])

# --------------------------------------------------------------------------- matrix + scatter
H = 380
c1, c2 = ui.row(2)
with c1, ui.card("matrix"):
    ui.card_header("Risk Matrix", "Open risks by probability and impact · red outline = high-severity zone")
    grid = (open_r.groupby(["probability", "impact"]).size()
            .unstack(fill_value=0).reindex(index=range(1, 6), columns=range(1, 6), fill_value=0))
    score = np.outer(np.arange(1, 6), np.arange(1, 6))
    text = [[f"{grid.values[i, j]}" if grid.values[i, j] else "" for j in range(5)] for i in range(5)]
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=[f"Impact {j}" for j in range(1, 6)], y=[f"P{i}" for i in range(1, 6)],
        colorscale=[[0, "#f5f6f9"], [0.0001, SEQ_BLUE[1]], [0.5, SEQ_BLUE[6]], [1, SEQ_BLUE[11]]],
        text=text, texttemplate="%{text}", textfont=dict(size=15),
        customdata=score, xgap=4, ygap=4, showscale=False,
        hovertemplate="Probability %{y} · %{x}<br>Score %{customdata}<br>%{z} open risks<extra></extra>"))
    for i in range(5):
        for j in range(5):
            if score[i, j] >= config.HIGH_RISK_SCORE:
                fig.add_shape(type="rect", x0=j - 0.47, x1=j + 0.47, y0=i - 0.47, y1=i + 0.47,
                              line=dict(color=STATUS["critical"], width=2))
    fig.update_layout(xaxis=dict(linecolor="rgba(0,0,0,0)"), margin=dict(t=8),
                      yaxis=dict(title="Probability", gridcolor="rgba(0,0,0,0)"))
    ui.chart(fig, height=H, key="matrix")

with c2, ui.card("pi_scatter"):
    ui.card_header("Probability vs Impact", "Each dot is an open risk (jittered) · size and colour = severity")
    rng = np.random.default_rng(7)
    d = open_r.assign(px=open_r.impact + rng.uniform(-0.28, 0.28, len(open_r)),
                      py=open_r.probability + rng.uniform(-0.28, 0.28, len(open_r)))
    fig = go.Figure()
    for sev in ["Low", "Medium", "High"]:
        s = d[d.severity == sev]
        if s.empty:
            continue
        fig.add_scatter(
            x=s.px, y=s.py, mode="markers", name=sev,
            marker=dict(size=9 + s.risk_score / 2, color=SEVERITY_COLORS[sev], opacity=0.85,
                        line=dict(color="#fff", width=1.5)),
            customdata=np.stack([s.project_name, s.risk_description, s.risk_score, s.status], axis=-1),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Score %{customdata[2]} · "
                          "%{customdata[3]}<extra></extra>")
    fig.update_layout(xaxis=dict(title="Impact", range=[0.5, 5.5], dtick=1, showgrid=True, gridcolor=GRID),
                      yaxis=dict(title="Probability", range=[0.5, 5.5], dtick=1))
    ui.chart(fig, height=H, key="pi_scatter")

# --------------------------------------------------------------------------- trends
H2 = 330
c1, c2 = ui.row([3, 2])
with c1, ui.card("trend"):
    ui.card_header("Risk Trends", "Open risks at each month-end by severity, with risks raised and resolved")
    month_ends = pd.date_range(ctx.f.start, ctx.f.end, freq="ME")
    if len(month_ends) == 0 or month_ends[-1] < ctx.f.end:
        month_ends = month_ends.append(pd.DatetimeIndex([ctx.f.end]))
    rows = []
    for m in month_ends:
        o = metrics.open_risks_as_of(risks, m)
        for sev in ["High", "Medium", "Low"]:
            rows.append({"month": m, "severity": sev, "open": int((o.severity == sev).sum())})
    trend = pd.DataFrame(rows)
    month_key = lambda s: s.dt.to_period("M").dt.to_timestamp(how="end").dt.normalize()  # noqa: E731
    raised = risks.groupby(month_key(risks.identified_date)).size()
    resolved = risks.groupby(month_key(risks.resolved_date)).size()
    fig = go.Figure()
    for sev in ["Low", "Medium", "High"]:
        t = trend[trend.severity == sev]
        fig.add_bar(x=t.month, y=t.open, name=f"Open · {sev}",
                    marker=dict(color=SEVERITY_COLORS[sev], line=dict(color="#fff", width=1)),
                    hovertemplate="%{x|%b %Y}<br>" + sev + ": %{y}<extra></extra>")
    fig.add_scatter(x=month_ends, y=raised.reindex(month_ends.normalize()).fillna(0).values,
                    name="Raised", mode="lines+markers", line=dict(color=SERIES[0]),
                    hovertemplate="%{x|%b %Y}<br>Raised %{y}<extra></extra>")
    fig.add_scatter(x=month_ends, y=resolved.reindex(month_ends.normalize()).fillna(0).values,
                    name="Resolved", mode="lines+markers", line=dict(color=SERIES[2], dash="dot"),
                    hovertemplate="%{x|%b %Y}<br>Resolved %{y}<extra></extra>")
    fig.update_layout(barmode="stack", hovermode="x unified", bargap=0.4)
    ui.chart(fig, height=H2, key="risk_trend")

with c2, ui.card("exposure"):
    ui.card_header("Exposure by Project", "Σ score of open risks")
    exp = open_r.groupby("project_name").risk_score.sum().sort_values()
    fig = go.Figure(go.Bar(x=exp.values, y=exp.index.str.replace("Project ", ""), orientation="h",
                           marker_color=SERIES[0], text=exp.values, textposition="outside", width=0.55,
                           cliponaxis=False, hovertemplate="%{y}: exposure %{x}<extra></extra>"))
    fig.update_layout(xaxis=dict(visible=False, range=[0, max(exp.max(), 1) * 1.2] if len(exp) else None),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)"), margin=dict(t=8))
    ui.chart(fig, height=H2, key="exposure")

# --------------------------------------------------------------------------- top risks
with ui.card("top_risks"):
    ctrl = ui.card_header("Top Risks", "Unresolved risks ranked by score, then age", controls=0.18)
    top = open_r.sort_values(["risk_score", "age_days"], ascending=[False, False])
    view = top[["risk_id", "project_name", "category", "risk_description", "probability", "impact",
                "risk_score", "severity", "status", "owner", "age_days", "mitigation_progress"]]
    with ctrl:
        ui.csv_download(view, f"open_risks_{ctx.as_of}.csv")
    st.dataframe(view, hide_index=True, width="stretch", height=420, column_config={
        "risk_id": st.column_config.NumberColumn("ID", format="R-%d"),
        "project_name": "Project", "category": "Category",
        "risk_description": st.column_config.TextColumn("Description", width="large"),
        "probability": "P", "impact": "I",
        "risk_score": st.column_config.NumberColumn("Score"),
        "severity": "Severity", "status": "Status", "owner": "Owner",
        "age_days": st.column_config.NumberColumn("Age (days)"),
        "mitigation_progress": st.column_config.ProgressColumn("Mitigation", min_value=0, max_value=100,
                                                               format="%d%%"),
    })
