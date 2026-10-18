"""Page 1 - Executive Dashboard."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from projectpulse import config, metrics
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import (
    AXIS, GRID, INK, PROJECT_STATUS_COLORS, RAG_EMOJI, SERIES, SEVERITY_COLORS, STATUS,
)

ctx = state.get_ctx()
pm = ctx.pm
ui.page_header("Executive Dashboard", "Portfolio health, budget, delivery and risk at a glance",
               "Overview", ctx)
if pm.empty:
    ui.empty_state()
    st.stop()

# --------------------------------------------------------------------------- KPIs
k = metrics.portfolio_kpis(pm)
util = state.active_window_util(ctx)
allocated = util[util.assigned_hours > 0]
avg_util = allocated.assigned_hours.sum() / allocated.capacity_hours.sum() if len(allocated) else float("nan")
overloaded = int((util.utilization > config.OVERLOAD_THRESHOLD).sum())
completed = int((pm.status_as_of == "Completed").sum())
health_rag = metrics.rag(k["portfolio_health"])

trend = state.health_trend(ctx.data, ctx.f.start.strftime("%Y-%m-%d"), ctx.as_of, ctx.version)
trend = trend[trend.project_id.isin(pm.project_id)]
weighted = trend.assign(w=trend.health_score * trend.budget).groupby("date")[["w", "budget"]].sum()
monthly = (weighted.w / weighted.budget).rename("health").reset_index()
prev_health = monthly.health.iloc[-2] if len(monthly) >= 2 else k["portfolio_health"]
health_delta = k["portfolio_health"] - prev_health

ui.kpi_grid([
    dict(label="Active Projects", value=f"{k['active_projects']}", icon="folder_open",
         sub=f"{k['total_projects']} in scope · {completed} completed"),
    dict(label="Portfolio Health", value=f"{k['portfolio_health']:.0f}", icon="favorite",
         tone={"Green": "good", "Yellow": "warn", "Red": "bad"}.get(health_rag, "accent"),
         badge=ui.rag_chip(health_rag),
         sub=f"{'▲' if health_delta >= 0 else '▼'} {abs(health_delta):.1f} pts vs prior month",
         help="Budget-weighted average health score of active projects"),
    dict(label="Budget Utilization", value=ui.fmt_pct(k["budget_utilization"]), icon="account_balance_wallet",
         sub=f"{ui.fmt_money(pm[pm.status_as_of != 'Completed'].ac.sum())} spent · CPI {k['portfolio_cpi']:.2f}",
         help="Actual cost to date ÷ budget, active projects"),
    dict(label="Delayed Projects", value=f"{k['delayed_projects']}", icon="schedule",
         tone="bad" if k["delayed_projects"] >= 3 else ("warn" if k["delayed_projects"] else "good"),
         sub=f"{int((pm.is_delayed & pm.completed_as_of).sum())} delivered late · SPI {k['portfolio_spi']:.2f}",
         help="Completed late, or forecast to finish >10% of duration past plan"),
    dict(label="Open Risks", value=f"{k['open_risks']}", icon="warning",
         tone="bad" if k["high_risks"] else "good",
         badge=ui.chip(f"{k['high_risks']} high", "bad" if k["high_risks"] else "good"),
         sub=f"Exposure {pm.risk_exposure.sum():,.0f} (probability × impact)"),
    dict(label="Resource Utilization", value=ui.fmt_pct(avg_util), icon="groups", tone="violet",
         badge=ui.chip(f"{overloaded} > 100%", "warn" if overloaded else "good"),
         sub="Allocated delivery staff, selected period"),
])

# --------------------------------------------------------------------------- row 1
H1 = 300
c1, c2 = ui.row([2, 3])
with c1, ui.card("gauge"):
    ui.card_header("Portfolio Health", "40% schedule · 30% budget · 30% risk")
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=k["portfolio_health"],
        number=dict(font=dict(size=40, color=INK["primary"]), valueformat=".0f"),
        delta=dict(reference=prev_health, valueformat=".1f", increasing=dict(color="#0a7f0a"),
                   decreasing=dict(color=STATUS["critical"])),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor=AXIS, tickfont=dict(color=INK["muted"], size=10)),
            bar=dict(color=INK["primary"], thickness=0.25),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            steps=[dict(range=[0, config.HEALTH_YELLOW], color="rgba(208,59,59,0.20)"),
                   dict(range=[config.HEALTH_YELLOW, config.HEALTH_GREEN], color="rgba(250,178,25,0.28)"),
                   dict(range=[config.HEALTH_GREEN, 100], color="rgba(12,163,12,0.20)")],
        ),
    ))
    fig.update_layout(margin=dict(l=28, r=28, t=16, b=0))
    ui.chart(fig, height=H1 - 56, key="gauge")
    bands = pm[pm.status_as_of != "Completed"].rag.value_counts()
    st.markdown("<div class='pp-legend' style='justify-content:center'>" + "".join(
        f"<span>{ui.rag_chip(r)} {bands.get(r, 0)}</span>" for r in ["Green", "Yellow", "Red"])
        + "<span class='pp-note'>active projects</span></div>", unsafe_allow_html=True)

with c2, ui.card("budget"):
    ctrl = ui.card_header("Budget Trend", "Cumulative or monthly spend, planned vs actual", controls=0.36)
    mode = ctrl.segmented_control("View", ["To date", "Monthly"], default="To date",
                                  key="budget_mode", label_visibility="collapsed", width="stretch")
    bt = metrics.budget_trend(ctx.projects, ctx.tasks, ctx.f.start, ctx.f.end)
    fig = go.Figure()
    if mode == "Monthly":
        fig.add_bar(x=bt.month, y=bt.planned, name="Planned", marker_color="#b7d3f6",
                    hovertemplate="%{x|%b %Y}<br>Planned $%{y:,.0f}<extra></extra>")
        fig.add_bar(x=bt.month, y=bt.actual, name="Actual", marker_color=SERIES[0],
                    hovertemplate="%{x|%b %Y}<br>Actual $%{y:,.0f}<extra></extra>")
        fig.update_layout(barmode="group")
    else:
        fig.add_scatter(x=bt.month, y=bt.planned_cum, name="Planned (baseline)",
                        line=dict(color=INK["muted"], dash="dot"),
                        hovertemplate="%{x|%b %Y}<br>Planned $%{y:,.0f}<extra></extra>")
        fig.add_scatter(x=bt.month, y=bt.actual_cum, name="Actual", line=dict(color=SERIES[0]),
                        fill="tozeroy", fillcolor="rgba(42,120,214,0.07)",
                        hovertemplate="%{x|%b %Y}<br>Actual $%{y:,.0f}<extra></extra>")
    fig.update_layout(hovermode="x unified", yaxis_tickprefix="$", yaxis_tickformat="~s")
    ui.chart(fig, height=H1, key="budget_trend")

# --------------------------------------------------------------------------- row 2
H2 = 270
c1, c2 = ui.row(2)
with c1, ui.card("status"):
    ui.card_header("Project Status Distribution", "Computed from SPI, forecast finish and health")
    order = ["On Track", "At Risk", "Delayed", "Completed"]
    counts = pm.computed_status.value_counts().reindex(order).fillna(0).astype(int)
    fig = go.Figure(go.Bar(
        x=counts.values, y=counts.index, orientation="h", width=0.55,
        marker_color=[PROJECT_STATUS_COLORS[s] for s in counts.index],
        text=[f"{v}  ·  {v / max(counts.sum(), 1):.0%}" for v in counts.values],
        textposition="outside", cliponaxis=False, textfont=dict(color=INK["secondary"]),
        hovertemplate="%{y}: %{x} projects<extra></extra>",
    ))
    fig.update_layout(yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                      xaxis=dict(visible=False, range=[0, max(counts.max(), 1) * 1.3]),
                      showlegend=False, margin=dict(t=8))
    ui.chart(fig, height=H2, key="status_dist")

with c2, ui.card("risk_breakdown"):
    ui.card_header("Risk Breakdown", "Open risks by category and severity")
    o = metrics.open_risks_as_of(ctx.risks, ctx.f.end).copy()
    if o.empty:
        ui.empty_state("No open risks for the current selection.")
    else:
        o["severity"] = o.risk_score.map(metrics.risk_severity)
        tab = (o.pivot_table(index="category", columns="severity", values="risk_id", aggfunc="count",
                             fill_value=0).reindex(columns=["High", "Medium", "Low"], fill_value=0))
        tab = tab.loc[tab.sum(axis=1).sort_values().index]
        fig = go.Figure()
        for sev in ["High", "Medium", "Low"]:
            fig.add_bar(y=tab.index, x=tab[sev], name=sev, orientation="h",
                        marker=dict(color=SEVERITY_COLORS[sev], line=dict(color="#fff", width=1.5)),
                        hovertemplate="%{y} · " + sev + ": %{x}<extra></extra>")
        fig.update_layout(barmode="stack", bargap=0.38, yaxis=dict(gridcolor="rgba(0,0,0,0)"),
                          xaxis=dict(gridcolor=GRID, showgrid=True))
        ui.chart(fig, height=H2, key="risk_breakdown")

# --------------------------------------------------------------------------- row 3
with ui.card("dept"):
    ui.card_header("Department Comparison", "Average health, cost performance and open risks by owning department")
    dept = pm.groupby("department").agg(
        health=("health_score", "mean"), ev=("ev", "sum"), ac=("ac", "sum"),
        risks=("open_risks", "sum"), projects=("project_id", "count")).reset_index()
    dept["cpi"] = dept.ev / dept.ac
    dept = dept.sort_values("health")
    fig = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.07,
                        subplot_titles=("Avg health score", "Cost performance (CPI)", "Open risks"))
    common = dict(orientation="h", marker_color=SERIES[0], textposition="outside", cliponaxis=False,
                  width=0.55, textfont=dict(color=INK["secondary"]))
    fig.add_bar(y=dept.department, x=dept.health, text=dept.health.round(0), customdata=dept.projects,
                hovertemplate="%{y}<br>Health %{x:.1f} · %{customdata} projects<extra></extra>",
                row=1, col=1, **common)
    fig.add_bar(y=dept.department, x=dept.cpi, text=dept.cpi.map("{:.2f}".format),
                hovertemplate="%{y}<br>CPI %{x:.2f}<extra></extra>", row=1, col=2, **common)
    fig.add_bar(y=dept.department, x=dept.risks, text=dept.risks,
                hovertemplate="%{y}<br>%{x} open risks<extra></extra>", row=1, col=3, **common)
    fig.add_vline(x=1.0, line=dict(color=INK["muted"], dash="dot", width=1), row=1, col=2)
    fig.update_xaxes(showgrid=False, showticklabels=False, linecolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    fig.update_xaxes(range=[0, 118], row=1, col=1)
    fig.update_xaxes(range=[0, max(1.25, dept.cpi.max() * 1.18)], row=1, col=2)
    fig.update_xaxes(range=[0, max(dept.risks.max(), 1) * 1.3], row=1, col=3)
    for a, xd in zip(fig.layout.annotations, ["x domain", "x2 domain", "x3 domain"]):
        a.update(xanchor="left", xref=xd, x=0, font=dict(size=12, color=INK["secondary"]))
    fig.update_layout(showlegend=False, margin=dict(t=30, r=24))
    ui.chart(fig, height=250, key="dept_cmp")

# --------------------------------------------------------------------------- row 4
H4 = 320
c1, c2 = ui.row([3, 2])
with c1, ui.card("health_trend"):
    ui.card_header("Portfolio Health Trend", "Budget-weighted health of active projects at each month-end")
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=config.HEALTH_YELLOW, fillcolor="rgba(208,59,59,0.05)", line_width=0)
    fig.add_hrect(y0=config.HEALTH_YELLOW, y1=config.HEALTH_GREEN, fillcolor="rgba(250,178,25,0.07)", line_width=0)
    fig.add_scatter(x=monthly.date, y=monthly.health, mode="lines+markers", name="Portfolio",
                    line=dict(color=SERIES[0]), marker=dict(size=8, line=dict(color="#fff", width=2)),
                    hovertemplate="%{x|%b %Y}<br>Health %{y:.1f}<extra></extra>")
    fig.update_layout(yaxis=dict(range=[0, 100]), showlegend=False, margin=dict(t=8))
    ui.chart(fig, height=H4, key="health_trend")

with c2, ui.card("attention"):
    ctrl = ui.card_header("Needs Attention", "Lowest-health active projects", controls=0.36)
    watch = pm[pm.status_as_of != "Completed"].nsmallest(8, "health_score")
    view = pd.DataFrame({
        "Project": watch.project_name.str.replace("Project ", ""),
        "Health": watch.health_score.round(0),
        "RAG": watch.rag.map(RAG_EMOJI),
        "SPI": watch.spi.round(2),
        "CPI": watch.cpi.round(2),
    })
    st.dataframe(view, hide_index=True, width="stretch", height="content",
                 column_config={"Health": st.column_config.ProgressColumn(
                     "Health", min_value=0, max_value=100, format="%.0f")})
    export = pm[["project_name", "department", "project_manager", "computed_status", "status",
                 "budget", "ac", "progress", "spi", "cpi", "health_score", "rag", "open_risks",
                 "high_risks"]].rename(columns={"ac": "actual_cost_to_date", "status": "reported_status"})
    with ctrl:
        ui.csv_download(export.round(3), f"portfolio_summary_{ctx.as_of}.csv", "Export")
