"""Page 2 - Project Portfolio Dashboard."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from projectpulse import config
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import GRID, INK, PLANNED, RAG_COLORS, RAG_EMOJI, RAG_ICONS, SERIES

ctx = state.get_ctx()
pm = ctx.pm
ui.page_header("Project Portfolio", "Health score, earned value and schedule for every project",
               "Overview", ctx)
if pm.empty:
    ui.empty_state()
    st.stop()

counts = pm.rag.value_counts()
act = pm[pm.status_as_of != "Completed"]
red = act[act.rag == "Red"].sort_values("health_score")
parts = {"schedule": act.schedule_health.mean(), "budget": act.budget_health.mean(),
         "risk": act.risk_health.mean()}
weakest = min(parts, key=parts.get) if len(act) else None
lead = (f"<b>{len(red)} of {len(act)} active projects are Red</b> "
        f"({', '.join(red.project_name.str.replace('Project ', ''))})" if len(red)
        else f"<b>No active project is Red</b> ({len(act)} active)")
ui.headline(lead + (f". The weakest part of the health score is <b>{weakest}</b> "
                    f"(average {parts[weakest]:.0f} of 100)." if weakest else "."),
            tone="bad" if len(red) else "good")
ui.kpi_grid([
    dict(label="Green", value=f"{counts.get('Green', 0)}", icon="check_circle", tone="good",
         sub=f"Health ≥ {config.HEALTH_GREEN}"),
    dict(label="Yellow", value=f"{counts.get('Yellow', 0)}", icon="error", tone="warn",
         sub=f"Health {config.HEALTH_YELLOW}–{config.HEALTH_GREEN - 1}"),
    dict(label="Red", value=f"{counts.get('Red', 0)}", icon="report", tone="bad",
         sub=f"Health < {config.HEALTH_YELLOW}"),
    dict(label="Cost Variance", value=ui.fmt_money(pm.cost_variance.sum()), icon="payments",
         tone="bad" if pm.cost_variance.sum() < 0 else "good",
         sub=f"EV − AC · schedule variance {ui.fmt_money(pm.schedule_variance.sum())}"),
])

# --------------------------------------------------------------------------- register
with ui.card("register"):
    ctrl = ui.card_header("Portfolio Register",
                          "Health = 40% schedule (SPI) + 30% budget (CPI) + 30% risk (open exposure)",
                          controls=0.18)
    table = pm.sort_values("health_score")
    view = pd.DataFrame({
        "Project": table.project_name,
        "Manager": table.project_manager,
        "Department": table.department,
        "Priority": table.priority,
        "Status": table.computed_status,
        "Reported": table.status,
        "Budget": table.budget / 1e6,
        "Cost to date": table.ac / 1e6,
        "Progress": table.progress * 100,
        "SPI": table.spi,
        "CPI": table.cpi,
        "Health": table.health_score,
        "RAG": table.rag.map(RAG_EMOJI),
    })
    with ctrl:
        ui.csv_download(view.round(3), f"project_portfolio_{ctx.as_of}.csv")
    st.dataframe(
        view, hide_index=True, width="stretch", height="content",
        column_config={
            "Budget": st.column_config.NumberColumn("Budget", format="$%.2fM"),
            "Cost to date": st.column_config.NumberColumn("Cost to date", format="$%.2fM"),
            "Progress": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
            "SPI": st.column_config.NumberColumn(format="%.2f", help="Schedule Performance Index = EV / PV"),
            "CPI": st.column_config.NumberColumn(format="%.2f", help="Cost Performance Index = EV / AC"),
            "Health": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Reported": st.column_config.TextColumn(help="Status reported by the project manager"),
            "Status": st.column_config.TextColumn(help="Status computed from the metrics"),
        },
    )
    mismatch = table[(table.status != table.computed_status) & (table.status_as_of != "Completed")]
    if ctx.f.end >= ctx.data_end and len(mismatch):
        names = ", ".join(f"<b>{r.project_name}</b> (reported {r.status}, metrics say {r.computed_status})"
                          for r in mismatch.itertuples())
        ui.note(f"ⓘ Reported status differs from the metrics for {names}.")

# --------------------------------------------------------------------------- drill-down
with ui.card("drilldown"):
    ctrl = ui.card_header("Project Drill-down", "Earned value, forecast and timeline for a single project",
                          controls=0.3)
    names = pm.sort_values("health_score").project_name.tolist()
    pick = ctrl.selectbox("Project", names, key="portfolio_pick", label_visibility="collapsed")
    r = pm[pm.project_name == pick].iloc[0]

    st.markdown(
        f"<div class='pp-legend'><span>{ui.rag_chip(r.rag)} <b>Health {r.health_score:.0f}</b></span>"
        f"<span>{r.description}</span><span>PM <b>{r.project_manager}</b></span>"
        f"<span>{r.department}</span><span>Priority {r.priority}</span></div>",
        unsafe_allow_html=True)
    cols = st.columns(8)
    for col, (label, val) in zip(cols, [
        ("Planned Value", ui.fmt_money(r.pv)), ("Earned Value", ui.fmt_money(r.ev)),
        ("Actual Cost", ui.fmt_money(r.ac)), ("SPI", f"{r.spi:.2f}"), ("CPI", f"{r.cpi:.2f}"),
        ("EAC", ui.fmt_money(r.eac)), ("VAC", ui.fmt_money(r.vac)),
        ("Forecast finish", f"{r.forecast_end:%b %Y}"),
    ]):
        col.metric(label, val)

    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        fig = go.Figure()
        rows = [("Planned", r.start_date, r.planned_end_date, PLANNED),
                ("Actual" if r.completed_as_of else "Forecast", r.start_date, r.forecast_end,
                 RAG_COLORS[r.rag])]
        for label, s, e, color in rows:
            fig.add_bar(y=[label], x=[(e - s).days * 86400000], base=[s], orientation="h",
                        marker=dict(color=color), name=label, width=0.5,
                        hovertemplate=f"{label}: {s:%d %b %Y} → {e:%d %b %Y}<extra></extra>")
        fig.add_vline(x=ctx.f.end.timestamp() * 1000, line=dict(color=INK["primary"], width=1, dash="dot"))
        fig.add_annotation(x=ctx.f.end, y=1.1, yref="paper", text="as of", showarrow=False,
                           font=dict(size=11, color=INK["secondary"]))
        sp = ctx.data["sprints"]
        sp = sp[(sp.project_id == r.project_id) & (sp.start_date <= ctx.f.end)]
        fig.add_scatter(x=sp.start_date, y=["Sprints"] * len(sp), mode="markers", name="Sprint start",
                        marker=dict(symbol="line-ns", size=14, line=dict(width=2, color=SERIES[6])),
                        text=sp.sprint_name, hovertemplate="%{text}<br>%{x|%d %b %Y}<extra></extra>")
        fig.update_layout(xaxis=dict(type="date", showgrid=True, gridcolor=GRID), showlegend=False,
                          yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                          title=dict(text="Timeline"))
        ui.chart(fig, height=230, key="timeline")
    with c2:
        labels = ["Schedule", "Budget", "Risk"]
        vals = [r.schedule_health, r.budget_health, r.risk_health]
        fig = go.Figure(go.Bar(
            x=vals, y=labels, orientation="h", marker_color=SERIES[:3], width=0.55,
            text=[f"{v:.0f}" for v in vals], textposition="outside", cliponaxis=False,
            hovertemplate="%{y} health %{x:.0f}<extra></extra>"))
        fig.update_layout(xaxis=dict(range=[0, 112], visible=False),
                          yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                          title=dict(text="Health components (0–100)"))
        ui.chart(fig, height=230, key="components")

# --------------------------------------------------------------------------- charts
H = 420
det = ui.details("Show details: health composition and SPI × CPI quadrant")
c1, c2 = ui.row(2, parent=det)
with c1, ui.card("composition"):
    ui.card_header("Health Score Composition", "Weighted contribution of each component (max 100)")
    t = pm.sort_values("health_score")
    w = config.HEALTH_WEIGHTS
    parts = [("Schedule (40%)", t.schedule_health * w["schedule"], SERIES[0]),
             ("Budget (30%)", t.budget_health * w["budget"], SERIES[1]),
             ("Risk (30%)", t.risk_health * w["risk"], SERIES[2])]
    fig = go.Figure()
    for name, vals, color in parts:
        fig.add_bar(y=t.project_name.str.replace("Project ", ""), x=vals, name=name, orientation="h",
                    marker=dict(color=color, line=dict(color="#fff", width=1.5)),
                    hovertemplate="%{y}<br>" + name + ": %{x:.1f} pts<extra></extra>")
    fig.add_scatter(y=t.project_name.str.replace("Project ", ""), x=t.health_score + 2, mode="text",
                    text=[f"{RAG_ICONS[r]} {s:.0f}" for r, s in zip(t.rag, t.health_score)],
                    textposition="middle right", textfont=dict(color=INK["primary"], size=11.5),
                    showlegend=False, hoverinfo="skip")
    fig.update_layout(barmode="stack", bargap=0.35, xaxis=dict(range=[0, 114], showgrid=True, gridcolor=GRID),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)"))
    ui.chart(fig, height=H, key="health_comp")

with c2, ui.card("quadrant"):
    ui.card_header("Schedule vs Cost Performance", "Bubble size = budget · dotted lines mark SPI and CPI of 1.0")
    q = pm.dropna(subset=["spi", "cpi"])
    fig = go.Figure()
    fig.add_vline(x=1, line=dict(color=INK["muted"], dash="dot", width=1))
    fig.add_hline(y=1, line=dict(color=INK["muted"], dash="dot", width=1))
    for rag_band in ["Green", "Yellow", "Red"]:
        d = q[q.rag == rag_band]
        if d.empty:
            continue
        fig.add_scatter(
            x=d.spi, y=d.cpi, mode="markers+text", name=f"{RAG_ICONS[rag_band]} {rag_band}",
            text=d.project_name.str.replace("Project ", ""),
            textposition=["top center" if i % 2 == 0 else "bottom center"
                          for i in d.spi.rank(method="first").astype(int)],
            textfont=dict(size=11, color=INK["secondary"]),
            marker=dict(size=np.sqrt(d.budget) / 40 + 8, color=RAG_COLORS[rag_band], opacity=0.85,
                        line=dict(color="#fff", width=2)),
            customdata=np.stack([d.health_score, d.budget / 1e6], axis=-1),
            hovertemplate="<b>%{text}</b><br>SPI %{x:.2f} · CPI %{y:.2f}<br>Health %{customdata[0]:.0f}"
                          " · Budget $%{customdata[1]:.2f}M<extra></extra>")
    lo = min(q.spi.min(), q.cpi.min(), 0.7) - 0.05
    hi = max(q.spi.max(), q.cpi.max(), 1.1) + 0.05
    for x, y, label in [(hi, hi, "Ahead · under budget"), (lo, hi, "Behind · under budget"),
                        (hi, lo, "Ahead · over budget"), (lo, lo, "Behind · over budget")]:
        fig.add_annotation(x=x, y=y, text=label, showarrow=False, font=dict(size=10.5, color=INK["muted"]),
                           xanchor="right" if x == hi else "left", yanchor="top" if y == hi else "bottom")
    fig.update_layout(xaxis=dict(title="SPI (schedule)", range=[lo, hi], showgrid=True, gridcolor=GRID),
                      yaxis=dict(title="CPI (cost)", range=[lo, hi]))
    ui.chart(fig, height=H, key="spi_cpi")
