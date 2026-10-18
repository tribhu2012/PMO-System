"""Page 1 - Executive Dashboard."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from projectpulse import config, insights, metrics
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import (
    AREA, BAND, GRID, INK, PLANNED, PROJECT_STATUS_COLORS, RAG_EMOJI, SERIES, SEVERITY_COLORS, STATUS,
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
health_rag = metrics.rag(k["portfolio_health"])

trend = state.health_trend(ctx.data, ctx.f.start.strftime("%Y-%m-%d"), ctx.as_of, ctx.version)
trend = trend[trend.project_id.isin(pm.project_id)]
weighted = trend.assign(w=trend.health_score * trend.budget).groupby("date")[["w", "budget"]].sum()
monthly = (weighted.w / weighted.budget).rename("health").reset_index()
prev_health = monthly.health.iloc[-2] if len(monthly) >= 2 else k["portfolio_health"]
health_delta = k["portfolio_health"] - prev_health

ictx = state.insight_context(ctx)
act = ictx.pm[ictx.pm.status_as_of != "Completed"].sort_values("health_score")
needs = act[act.rag != "Green"]
red = act[act.rag == "Red"]
overrun = (act.eac - act.budget).clip(lower=0).sum()


def _names(df: pd.DataFrame) -> str:
    n = df.project_name.str.replace("Project ", "").tolist()
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " and " + n[-1]


trend_word = "up" if health_delta >= 0 else "down"
if len(red):
    ask = (f"<b>{len(red)} project{'s' if len(red) > 1 else ''} need{'' if len(red) > 1 else 's'} a "
           f"decision:</b> {_names(red)}.")
elif len(needs):
    ask = f"No project is Red. <b>{len(needs)} on watch:</b> {_names(needs)}."
else:
    ask = "<b>Every active project is Green.</b>"
ui.headline(f"Portfolio health is <b>{k['portfolio_health']:.0f} ({health_rag})</b>, {trend_word} "
            f"{abs(health_delta):.1f} points on last month. {ask}",
            tone={"Green": "good", "Yellow": "warn", "Red": "bad"}.get(health_rag, "neutral"))

ui.kpi_grid([
    dict(label="Portfolio Health", value=f"{k['portfolio_health']:.0f}", icon="favorite",
         tone={"Green": "good", "Yellow": "warn", "Red": "bad"}.get(health_rag, "accent"),
         badge=ui.rag_chip(health_rag),
         sub=f"{k['active_projects']} active projects · {'▲' if health_delta >= 0 else '▼'} "
             f"{abs(health_delta):.1f} vs last month",
         help="Budget-weighted average health score of active projects"),
    dict(label="Budget Used", value=ui.fmt_pct(k["budget_utilization"]), icon="account_balance_wallet",
         tone="bad" if overrun > 0 else "good",
         sub=f"Forecast overrun {ui.fmt_money(overrun)} · CPI {k['portfolio_cpi']:.2f}",
         help="Actual cost to date ÷ budget, active projects. Overrun = Σ(EAC − budget)."),
    dict(label="Delayed Projects", value=f"{k['delayed_projects']}", icon="schedule",
         tone="bad" if k["delayed_projects"] >= 3 else ("warn" if k["delayed_projects"] else "good"),
         sub=f"of {k['total_projects']} in scope · SPI {k['portfolio_spi']:.2f}",
         help="Completed late, or forecast to finish >10% of duration past plan"),
    dict(label="High Risks", value=f"{k['high_risks']}", icon="crisis_alert",
         tone="bad" if k["high_risks"] else "good",
         sub=f"of {k['open_risks']} open risks · score ≥ {config.HIGH_RISK_SCORE}"),
])

# --------------------------------------------------------------------------- decisions
with ui.card("decisions"):
    ui.card_header("Needs a Decision", "Lowest-health Red and Yellow projects · main driver and the recommended action")
    if needs.empty:
        ui.note("Nothing to escalate. All active projects are Green.")
    items = []
    for r in needs.head(3).itertuples():
        d = insights.diagnose(ictx.pm[ictx.pm.project_id == r.project_id].iloc[0], ictx)
        why = d.drivers[0].text if d.drivers else "Health is below target."
        do = d.drivers[0].recommendation if d.drivers else "Review in the weekly status meeting."
        items.append(f"<div class='pp-decision'><div class='pp-dhead'>{ui.rag_chip(r.rag)}"
                     f"<span class='pp-dscore'>{r.health_score:.0f}</span></div>"
                     f"<div class='pp-dname'>{html.escape(r.project_name)}</div>"
                     f"<div class='pp-dpm'>{html.escape(r.project_manager)} · {html.escape(r.department)}</div>"
                     f"<div class='pp-dwhy'>{html.escape(why)}</div>"
                     f"<div class='pp-ddo'><b>Action</b>{html.escape(do)}</div></div>")
    st.markdown(f"<div class='pp-decisions'>{''.join(items)}</div>", unsafe_allow_html=True)
    if len(needs) > 3:
        ui.note(f"+ {len(needs) - 3} more below target. See Project Portfolio.")

# --------------------------------------------------------------------------- health trend
with ui.card("health_trend"):
    ui.card_header("Portfolio Health Trend", "Budget-weighted health of active projects at each month-end")
    lo = max(0, min(monthly.health.min(), config.HEALTH_YELLOW) - 8)
    hi = min(100, max(monthly.health.max(), config.HEALTH_GREEN) + 6)
    fig = go.Figure()
    for y0, y1, color, label in [
            (lo, config.HEALTH_YELLOW, BAND["Red"], f"Red < {config.HEALTH_YELLOW}"),
            (config.HEALTH_YELLOW, config.HEALTH_GREEN, BAND["Yellow"],
             f"Yellow {config.HEALTH_YELLOW}–{config.HEALTH_GREEN - 1}"),
            (config.HEALTH_GREEN, hi, BAND["Green"], f"Green ≥ {config.HEALTH_GREEN}")]:
        if y1 > y0:
            fig.add_hrect(y0=y0, y1=y1, fillcolor=color, line_width=0, layer="below")
            fig.add_annotation(x=1, xref="paper", y=(y0 + y1) / 2, text=label, showarrow=False,
                               xanchor="left", xshift=8, font=dict(size=11, color=INK["muted"]))
    fig.add_hline(y=config.HEALTH_GREEN, line=dict(color=STATUS["good"], dash="dash", width=1))
    delta = monthly.health.diff()
    month = monthly.date.dt.to_period("M").dt.to_timestamp()  # label each month-end point by its month
    fig.add_scatter(x=month, y=monthly.health, mode="lines+markers", name="Portfolio",
                    line=dict(color=SERIES[0], width=2.5),
                    marker=dict(size=7, color=SERIES[0], line=dict(color="#fff", width=1.5)),
                    customdata=delta.fillna(0),
                    hovertemplate="%{x|%b %Y}<br>Health <b>%{y:.1f}</b> (%{customdata:+.1f})<extra></extra>")
    last = monthly.iloc[-1]
    fig.add_scatter(x=[month.iloc[-1]], y=[last.health], mode="markers", hoverinfo="skip", showlegend=False,
                    marker=dict(size=13, color=SERIES[0], line=dict(color="#fff", width=3)))
    fig.add_annotation(x=month.iloc[-1], y=last.health, text=f"<b>{last.health:.0f}</b>", showarrow=False,
                       yshift=18, font=dict(size=14, color=INK["primary"]))
    fig.update_layout(showlegend=False, margin=dict(t=10, r=96, l=8, b=4),
                      yaxis=dict(range=[lo, hi], dtick=10, title=None),
                      xaxis=dict(tickformat="%b %Y", dtick="M1", showgrid=False,
                                 range=[month.min() - pd.Timedelta(days=12),
                                        month.max() + pd.Timedelta(days=12)]))
    ui.chart(fig, height=300, key="health_trend")

det = ui.details("Show details: budget, status, risks and departments")

# --------------------------------------------------------------------------- row 1
H1 = 300
with det, ui.card("budget"):
    ctrl = ui.card_header("Budget Trend", "Cumulative or monthly spend, planned vs actual", controls=0.36)
    mode = ctrl.segmented_control("View", ["To date", "Monthly"], default="To date",
                                  key="budget_mode", label_visibility="collapsed", width="stretch")
    bt = metrics.budget_trend(ctx.projects, ctx.tasks, ctx.f.start, ctx.f.end)
    fig = go.Figure()
    if mode == "Monthly":
        fig.add_bar(x=bt.month, y=bt.planned, name="Planned", marker_color=PLANNED,
                    hovertemplate="%{x|%b %Y}<br>Planned $%{y:,.0f}<extra></extra>")
        fig.add_bar(x=bt.month, y=bt.actual, name="Actual", marker_color=SERIES[0],
                    hovertemplate="%{x|%b %Y}<br>Actual $%{y:,.0f}<extra></extra>")
        fig.update_layout(barmode="group")
    else:
        fig.add_scatter(x=bt.month, y=bt.planned_cum, name="Planned (baseline)",
                        line=dict(color=INK["muted"], dash="dot"),
                        hovertemplate="%{x|%b %Y}<br>Planned $%{y:,.0f}<extra></extra>")
        fig.add_scatter(x=bt.month, y=bt.actual_cum, name="Actual", line=dict(color=SERIES[0]),
                        fill="tozeroy", fillcolor=AREA,
                        hovertemplate="%{x|%b %Y}<br>Actual $%{y:,.0f}<extra></extra>")
    fig.update_layout(hovermode="x unified", yaxis_tickprefix="$", yaxis_tickformat="~s")
    ui.chart(fig, height=H1, key="budget_trend")

# --------------------------------------------------------------------------- row 2
H2 = 270
c1, c2 = ui.row(2, parent=det)
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
with det, ui.card("dept"):
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

# --------------------------------------------------------------------------- full list
with det, ui.card("attention"):
    ctrl = ui.card_header("All Active Projects", "Lowest health first", controls=0.2)
    watch = pm[pm.status_as_of != "Completed"].sort_values("health_score")
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
