"""Page 8 - AI Insights (template-based analyst assistant)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from projectpulse import config, insights, metrics, ml
from projectpulse.ui import components as ui
from projectpulse.ui import state

ctx = state.get_ctx()
ui.page_header("AI Insights", "Ask why a project is unhealthy and get drivers plus recommendations",
               "Intelligence", ctx)
if ctx.pm.empty:
    ui.empty_state()
    st.stop()

# --------------------------------------------------------------------------- context
model = state.delay_model(ctx.data, ctx.version)
pm = ctx.pm.copy()
active = pm.status_as_of != "Completed"
if active.any():
    scored = model.score_frame(ml.current_features(pm[active]))
    pm = pm.merge(scored[["project_id", "delay_probability", "risk_class"]], on="project_id", how="left")
else:
    pm["delay_probability"] = float("nan")

open_r = metrics.open_risks_as_of(ctx.risks, ctx.f.end).copy()
open_r["project_name"] = open_r.project_id.map(ctx.project_names)
window_start = ctx.f.end - pd.Timedelta(weeks=8)
util = metrics.utilisation_by_employee(ctx.daily, ctx.data["employees"], window_start, ctx.f.end)
recent = ctx.daily[(ctx.daily.date > window_start) & (ctx.daily.date <= ctx.f.end)]
team = {int(k): list(v) for k, v in recent.groupby("project_id").employee_id.unique().items()}
ictx = insights.InsightContext(pm=pm, open_risks=open_r, utilization=util,
                               tasks=ctx.tasks[ctx.tasks.created_date <= ctx.f.end], team=team)

act = pm[active.values] if active.any() else pm.iloc[0:0]
red = act[act.rag == "Red"]
watch = act[act.rag == "Yellow"]
high = open_r[open_r.risk_score >= config.HIGH_RISK_SCORE]
overloaded = util[(util.utilization > config.OVERLOAD_THRESHOLD) & (util.role != "Project Manager")]
overrun = (act.eac - act.budget).clip(lower=0).sum()
riskiest = act.sort_values("delay_probability", ascending=False).head(1)

ui.kpi_grid([
    dict(label="Needs Intervention", value=f"{len(red)}", icon="emergency", tone="bad" if len(red) else "good",
         sub=", ".join(red.project_name.str.replace("Project ", "")) or "No red projects"),
    dict(label="On Watch", value=f"{len(watch)}", icon="visibility", tone="warn" if len(watch) else "good",
         sub=", ".join(watch.project_name.str.replace("Project ", "")) or "No yellow projects"),
    dict(label="High-Severity Risks", value=f"{len(high)}", icon="crisis_alert", tone="bad" if len(high) else "good",
         sub=f"of {len(open_r)} open risks"),
    dict(label="Overloaded People", value=f"{len(overloaded)}", icon="local_fire_department",
         tone="warn" if len(overloaded) else "good", sub="Above 100% over the last 8 weeks"),
    dict(label="Forecast Overrun", value=ui.fmt_money(overrun), icon="trending_up",
         tone="bad" if overrun > 0 else "good", sub="Σ (EAC − budget), active projects"),
    dict(label="Highest Delay Risk",
         value=f"{riskiest.delay_probability.iloc[0]:.0%}" if len(riskiest) and pd.notna(riskiest.delay_probability.iloc[0]) else "–",
         icon="psychology", tone="violet",
         sub=riskiest.project_name.iloc[0] if len(riskiest) else "No active projects"),
])

# --------------------------------------------------------------------------- briefing + diagnosis
c1, c2 = ui.row([1, 1])
with c1, ui.card("briefing"):
    ctrl = ui.card_header("Executive Briefing", "Auto-generated from portfolio metrics", controls=0.32)
    briefing = insights.portfolio_briefing(ictx)
    actions = []
    for r in act[act.rag != "Green"].sort_values("health_score").itertuples():
        d = insights.diagnose(pm[pm.project_id == r.project_id].iloc[0], ictx)
        if d.drivers:
            actions.append(f"{ui.rag_chip(r.rag)} <b>{r.project_name.replace('Project ', '')}</b> · "
                           f"{d.drivers[0].recommendation}")
    ctrl.download_button("Download .md", briefing.encode(), f"executive_briefing_{ctx.as_of}.md",
                         mime="text/markdown", icon=":material/description:", type="tertiary")
    st.markdown(briefing)
    if actions:
        st.markdown("<div class='pp-card-title' style='font-size:14px;margin-top:6px'>Priority actions this week</div>"
                    + "".join(f"<div class='pp-action'>{a}</div>" for a in actions), unsafe_allow_html=True)

with c2, ui.card("diagnosis"):
    ctrl = ui.card_header("Project Diagnosis", "Why the health score is what it is", controls=0.42)
    order = pm.sort_values("health_score").project_name.tolist()
    pick = ctrl.selectbox("Project", order, key="diag_project", label_visibility="collapsed")
    diag = insights.diagnose(pm[pm.project_name == pick].iloc[0], ictx)
    st.markdown(diag.to_markdown())

# --------------------------------------------------------------------------- chat
with ui.card("chat"):
    ui.card_header("Ask ProjectPulse", "Rule-based assistant · every answer is generated from live metrics, not an LLM")
    if "chat" not in st.session_state:
        st.session_state.chat = [{"role": "assistant", "content": insights.HELP_TEXT}]

    worst = pm.sort_values("health_score").project_name.iloc[0].replace("Project ", "")
    suggestions = [f"Why is Project {worst} unhealthy?", "Give me an executive summary",
                   "Which projects are likely to be delayed?", "Who is overloaded?", "Compare Orion and Titan"]
    clicked = st.pills("Suggestions", suggestions, key="chat_suggest", label_visibility="collapsed")

    long_chat = sum(len(m["content"]) for m in st.session_state.chat[-12:]) > 1500
    with st.container(height=520 if long_chat else "content", border=False):
        for msg in st.session_state.chat[-12:]:
            with st.chat_message(msg["role"], avatar=":material/person:" if msg["role"] == "user"
                                 else ":material/auto_awesome:"):
                st.markdown(msg["content"])

    prompt = st.chat_input("Ask about a project, budget, risks, team or delays…")
    question = prompt or (clicked if clicked and st.session_state.get("_last_pill") != clicked else None)
    st.session_state._last_pill = clicked
    if question:
        st.session_state.chat.append({"role": "user", "content": question})
        st.session_state.chat.append({"role": "assistant", "content": insights.answer(question, ictx)})
        st.rerun()

    if len(st.session_state.chat) > 1 and st.button("Clear conversation", icon=":material/delete_sweep:",
                                                     type="tertiary"):
        st.session_state.chat = st.session_state.chat[:1]
        st.session_state._last_pill = None
        st.rerun()
