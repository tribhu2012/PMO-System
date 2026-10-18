"""Page 3 - Resource Management."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from projectpulse import config, metrics
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import DIVERGING, GRID, INK, SERIES, STATUS

ctx = state.get_ctx()
ui.page_header("Resource Management", "Capacity, allocation and workload balance for delivery staff",
               "Delivery", ctx)

staff = state.delivery_staff(ctx.employees)
if staff.empty:
    ui.empty_state()
    st.stop()

util = metrics.utilisation_by_employee(ctx.daily, staff, ctx.f.start, ctx.f.end)
allocated = util[util.assigned_hours > 0]
avg_util = allocated.assigned_hours.sum() / allocated.capacity_hours.sum() if len(allocated) else float("nan")
over = util[util.utilization > config.OVERLOAD_THRESHOLD]
under = util[(util.utilization < config.UNDERUTILISED_THRESHOLD) & (util.assigned_hours > 0)]
bench = util[util.assigned_hours == 0]

spare = len(under) + len(bench)
hot = over.department.value_counts()
ui.headline((f"<b>{len(over)} people are above 100% capacity</b>"
             + (f", mostly in {hot.index[0]} ({hot.iloc[0]})" if len(hot) else "")
             if len(over) else "<b>Nobody is above 100% capacity</b>")
            + f". <b>{spare}</b> {'have' if spare != 1 else 'has'} spare capacity to take on work.",
            tone="bad" if len(over) else "good", icon="groups")
ui.kpi_grid([
    dict(label="Average Utilization", value=ui.fmt_pct(avg_util), icon="speed",
         sub=f"{len(allocated)} allocated of {len(util)} delivery staff",
         help="Planned sprint hours ÷ capacity hours, people with any allocation"),
    dict(label="Overloaded Resources", value=f"{len(over)}", icon="local_fire_department",
         tone="bad" if len(over) else "good",
         badge=ui.chip(f"> {config.OVERLOAD_THRESHOLD:.0%}", "bad" if len(over) else "good"),
         sub=f"Peak {util.utilization.max():.0%}" if len(util) else ""),
    dict(label="Under-utilised Resources", value=f"{len(under)}", icon="battery_3_bar",
         tone="warn" if len(under) else "good",
         badge=ui.chip(f"< {config.UNDERUTILISED_THRESHOLD:.0%}", "warn" if len(under) else "good"),
         sub="Allocated but below target"),
    dict(label="On the Bench", value=f"{len(bench)}", icon="event_seat", tone="violet",
         sub="No sprint work in the period"),
])

# --------------------------------------------------------------------------- dept + capacity
H = 470
c1, c2 = ui.row([2, 3])
with c1, ui.card("dept_util"):
    ui.card_header("Department Utilization", "Assigned ÷ capacity hours, selected period")
    dept = util.groupby("department").agg(assigned=("assigned_hours", "sum"),
                                          capacity=("capacity_hours", "sum"),
                                          people=("employee_id", "count")).reset_index()
    dept["util"] = dept.assigned / dept.capacity
    dept = dept.sort_values("util")
    fig = go.Figure(go.Bar(
        x=dept.util, y=dept.department, orientation="h", marker_color=SERIES[0], width=0.55,
        text=dept.util.map("{:.0%}".format), textposition="outside", cliponaxis=False,
        customdata=dept.people, hovertemplate="%{y}<br>%{x:.0%} · %{customdata} people<extra></extra>"))
    fig.add_vline(x=1.0, line=dict(color=STATUS["critical"], dash="dot", width=1.5))
    fig.add_annotation(x=1.0, y=1.04, yref="paper", text="100% capacity", showarrow=False,
                       font=dict(size=11, color=INK["secondary"]))
    fig.update_layout(xaxis=dict(tickformat=".0%", range=[0, max(1.2, dept.util.max() * 1.15)],
                                 showgrid=True, gridcolor=GRID),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)"))
    ui.chart(fig, height=H, key="dept_util")

with c2, ui.card("capacity"):
    ui.card_header("Capacity vs Assignment", "Top 20 most-allocated people · bar = assigned hours · tick = capacity")
    top = util.sort_values("assigned_hours", ascending=False).head(20).iloc[::-1]
    colors = [STATUS["critical"] if u > config.OVERLOAD_THRESHOLD else SERIES[0] for u in top.utilization]
    fig = go.Figure()
    fig.add_bar(y=top.employee_name, x=top.assigned_hours, orientation="h", name="Assigned hours",
                marker_color=colors, customdata=top.utilization,
                hovertemplate="%{y}<br>Assigned %{x:,.0f} h (%{customdata:.0%})<extra></extra>")
    fig.add_scatter(y=top.employee_name, x=top.capacity_hours, mode="markers", name="Capacity",
                    marker=dict(symbol="line-ns", size=14, line=dict(width=3, color=INK["primary"])),
                    hovertemplate="%{y}<br>Capacity %{x:,.0f} h<extra></extra>")
    fig.update_layout(xaxis=dict(title="Hours in period", showgrid=True, gridcolor=GRID),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11)), bargap=0.3)
    ui.chart(fig, height=H - 24, key="cap_vs_assign")
    ui.note("Red bars are above 100% of capacity.")

det = ui.details("Show details: monthly workload heatmap and full resource register")

# --------------------------------------------------------------------------- heatmap
with det, ui.card("heatmap"):
    ctrl = ui.card_header("Workload Heatmap",
                          "Monthly utilisation per person · grey ≈ 90% target · red = overloaded · "
                          "blue = spare capacity · blank = unassigned", controls=0.26)
    dept_pick = ctrl.selectbox("Department", ["All departments"] + sorted(staff.department.unique()),
                               key="heat_dept", label_visibility="collapsed")
    monthly = metrics.utilisation_by_month(ctx.daily, staff, ctx.f.start, ctx.f.end)
    people = staff if dept_pick == "All departments" else staff[staff.department == dept_pick]
    months = pd.period_range(ctx.f.start, ctx.f.end, freq="M").to_timestamp()
    mat = (monthly[monthly.employee_id.isin(people.employee_id)]
           .pivot_table(index="employee_id", columns="month", values="utilization", aggfunc="sum")
           .reindex(index=people.employee_id, columns=months).fillna(0.0))
    order = mat.mean(axis=1).sort_values(ascending=False).index
    mat = mat.loc[order]
    names = people.set_index("employee_id").loc[order]
    labels = [f"{n} · {d[:3]}" for n, d in zip(names.employee_name, names.department)]
    z = (mat.values * 100).round(0)
    z[z == 0] = float("nan")
    fig = go.Figure(go.Heatmap(
        z=z, x=[m.strftime("%b %y") for m in months], y=labels,
        colorscale=DIVERGING, zmin=30, zmax=150, zmid=90, xgap=2, ygap=2,
        colorbar=dict(title=dict(text="Util %", font=dict(size=11)), ticksuffix="%", len=0.5, y=0.75),
        hovertemplate="%{y}<br>%{x}: %{z:.0f}%<extra></extra>"))
    fig.update_layout(yaxis=dict(autorange="reversed", tickfont=dict(size=10.5), gridcolor="rgba(0,0,0,0)"),
                      xaxis=dict(side="top"), margin=dict(t=24))
    with st.container(height=480, border=False):
        ui.chart(fig, height=max(320, 18 * len(labels) + 50), key="heatmap")
    ui.note(f"{len(labels)} people, sorted by average utilisation · scroll for more")

# --------------------------------------------------------------------------- table
with det, ui.card("register"):
    ctrl = ui.card_header("Resource Register", "Every delivery team member, sorted by utilisation", controls=0.18)
    view = util.assign(utilization=util.utilization * 100).sort_values("utilization", ascending=False)
    view = view[["employee_name", "department", "role", "weekly_capacity_hours", "projects",
                 "assigned_hours", "capacity_hours", "utilization"]]
    view["band"] = pd.cut(view.utilization, [-1, 0.001, config.UNDERUTILISED_THRESHOLD * 100,
                                             config.OVERLOAD_THRESHOLD * 100, 1e9],
                          labels=["○ Bench", "◇ Under-utilised", "● Healthy", "■ Overloaded"]).astype(str)
    with ctrl:
        ui.csv_download(view.round(1), f"resource_utilization_{ctx.as_of}.csv")
    st.dataframe(view, hide_index=True, width="stretch", height=400, column_config={
        "employee_name": "Employee", "department": "Department", "role": "Role",
        "weekly_capacity_hours": st.column_config.NumberColumn("Weekly cap. (h)"),
        "projects": st.column_config.NumberColumn("Projects"),
        "assigned_hours": st.column_config.NumberColumn("Assigned (h)", format="%.0f"),
        "capacity_hours": st.column_config.NumberColumn("Capacity (h)", format="%.0f"),
        "utilization": st.column_config.ProgressColumn("Utilization", min_value=0, max_value=150, format="%.0f%%"),
        "band": "Band",
    })
