"""Page 7 - Predictive Analytics (project delay model)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from projectpulse import config, ml
from projectpulse.metrics import classify_delay
from projectpulse.ui import components as ui
from projectpulse.ui import state
from projectpulse.ui.theme import (
    AREA, BAND_STRONG, DELAY_CLASS_COLORS, GRID, INK, SEQ_BLUE, SERIES, SERIF, STATUS,
)

ctx = state.get_ctx()
model = state.delay_model(ctx.data, ctx.version)
ui.page_header("Predictive Analytics", "Probability that a project finishes after its planned end date",
               "Intelligence", ctx, note=f"Model: <b>{model.model_name}</b>")

pm = ctx.pm[ctx.pm.status_as_of != "Completed"]
scored = (model.score_frame(ml.current_features(pm)).sort_values("delay_probability", ascending=False)
          if len(pm) else pd.DataFrame())
n_high = int((scored.risk_class == "High Risk").sum()) if len(scored) else 0

m = model.metrics
n_med = int((scored.risk_class == "Medium Risk").sum()) if len(scored) else 0
n_low = len(scored) - n_high - n_med
high_names = (scored[scored.risk_class == "High Risk"].project_name.str.replace("Project ", "").tolist()
              if len(scored) else [])
ui.headline((f"<b>{n_high} of {len(scored)} active projects are likely to finish late</b> "
             f"({', '.join(high_names)})" if n_high else
             f"<b>None of the {len(scored)} active projects is at high risk of finishing late</b>")
            + f". On past projects the model ranks a late project above an on-time one "
              f"{m['roc_auc']:.0%} of the time.",
            tone="bad" if n_high else "good", icon="insights")
ui.kpi_grid([
    dict(label="High Risk", value=f"{n_high}", icon="notification_important",
         tone="bad" if n_high else "good", sub=f"Delay probability ≥ {config.DELAY_CLASS_BANDS['Medium Risk']:.0%}"),
    dict(label="Medium Risk", value=f"{n_med}", icon="error", tone="warn" if n_med else "good",
         sub=f"{config.DELAY_CLASS_BANDS['Low Risk']:.0%}–{config.DELAY_CLASS_BANDS['Medium Risk']:.0%}"),
    dict(label="Low Risk", value=f"{n_low}", icon="check_circle", tone="good",
         sub=f"Below {config.DELAY_CLASS_BANDS['Low Risk']:.0%}"),
    dict(label="Model ROC AUC", value=f"{m['roc_auc']:.2f}", icon="query_stats", tone="violet",
         sub=f"Accuracy {m['accuracy']:.0%} · recall {m['recall']:.0%} on {model.n_test} test projects"),
])

# --------------------------------------------------------------------------- live predictions
with ui.card("predictions"):
    ctrl = ui.card_header("Active Project Predictions",
                          "Delay probability from current budget, risk, utilisation, velocity and backlog",
                          controls=0.18)
    if scored.empty:
        ui.empty_state("No active projects in the current selection.")
    else:
        with ctrl:
            ui.csv_download(scored.round(4), f"delay_predictions_{ctx.as_of}.csv")
        H = max(280, 40 * len(scored) + 70)
        c1, c2 = st.columns([1, 1], gap="large")
        with c1:
            d = scored.iloc[::-1]
            fig = go.Figure(go.Bar(
                x=d.delay_probability, y=d.project_name.str.replace("Project ", ""), orientation="h",
                marker_color=[DELAY_CLASS_COLORS[c] for c in d.risk_class], width=0.6,
                text=[f"{p:.0%}" for p in d.delay_probability], textposition="outside", cliponaxis=False,
                customdata=d.risk_class,
                hovertemplate="%{y}<br>Delay probability %{x:.1%}<br>%{customdata}<extra></extra>"))
            for x, label in zip(config.DELAY_CLASS_BANDS.values(), ["35%", "65%"]):
                fig.add_vline(x=x, line=dict(color=INK["muted"], dash="dot", width=1))
            fig.update_layout(xaxis=dict(range=[0, 1.12], tickformat=".0%", showgrid=True, gridcolor=GRID),
                              yaxis=dict(gridcolor="rgba(0,0,0,0)"), margin=dict(t=8))
            ui.chart(fig, height=H, key="pred_bar")
            ui.note("● Low < 35% · ▲ Medium 35–65% · ■ High ≥ 65% (dotted lines)")
        with c2:
            view = scored[["project_name", "delay_probability", "risk_class", "budget_utilization",
                           "open_risks", "avg_resource_utilization", "sprint_velocity", "tasks_remaining"]]
            view = view.assign(project_name=view.project_name.str.replace("Project ", ""),
                               delay_probability=view.delay_probability * 100,
                               avg_resource_utilization=view.avg_resource_utilization * 100,
                               risk_class=view.risk_class.map({"Low Risk": "● Low", "Medium Risk": "▲ Medium",
                                                               "High Risk": "■ High"}))
            st.dataframe(view, hide_index=True, width="stretch", height="content", column_config={
                "project_name": "Project",
                "delay_probability": st.column_config.ProgressColumn("Delay", min_value=0, max_value=100, format="%.0f%%"),
                "risk_class": "Class",
                "budget_utilization": st.column_config.NumberColumn("AC÷EV", format="%.2f"),
                "open_risks": "Risks",
                "avg_resource_utilization": st.column_config.NumberColumn("Util.", format="%.0f%%"),
                "sprint_velocity": st.column_config.NumberColumn("Velocity", format="%.0f"),
                "tasks_remaining": "Backlog",
            })

with ui.card("whatif"):
    ctrl = ui.card_header("Prediction Interface",
                          "Start from a project, then move the drivers to run a what-if scenario", controls=0.3)
    presets = {"Typical project (training median)": model.train_medians.to_dict()}
    for r in scored.itertuples() if len(scored) else []:
        presets[r.project_name] = {f: getattr(r, f) if pd.notna(getattr(r, f)) else model.train_medians[f]
                                   for f in ml.FEATURES}
    pick = ctrl.selectbox("Start from", list(presets), key="whatif_preset",
                          index=1 if len(presets) > 1 else 0, label_visibility="collapsed")
    base = presets[pick]
    c1, c2, c3 = st.columns([5, 4, 5], gap="large")
    with c1:
        k = f"wi_{pick}"
        bu = st.slider("Budget utilization (AC ÷ EV)", 0.80, 1.50, float(round(base["budget_utilization"], 2)),
                       0.01, key=k + "bu", help="Above 1.0 means spending more than the value delivered")
        risks = st.slider("Open risks", 0, 40, int(base["open_risks"]), key=k + "r")
        ru = st.slider("Avg resource utilization", 0.50, 1.50, float(round(base["avg_resource_utilization"], 2)),
                       0.01, key=k + "ru", format="%.2f")
        vel = st.slider("Sprint velocity (SP / sprint)", 50, 450, int(base["sprint_velocity"]), key=k + "v")
        rem = st.slider("Tasks remaining", 0, 1200, int(base["tasks_remaining"]), key=k + "t")
    x = pd.DataFrame([{"budget_utilization": bu, "open_risks": risks, "avg_resource_utilization": ru,
                       "sprint_velocity": vel, "tasks_remaining": rem}])
    p = float(model.predict_proba(x)[0])
    cls = classify_delay(p)
    with c2:
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=p * 100,
            number=dict(suffix="%", valueformat=".0f", font=dict(size=40, color=INK["primary"], family=SERIF)),
            gauge=dict(axis=dict(range=[0, 100], tickcolor=INK["muted"], tickfont=dict(size=10)),
                       bar=dict(color=INK["primary"], thickness=0.25), borderwidth=0,
                       steps=[dict(range=[0, 35], color=BAND_STRONG["Green"]),
                              dict(range=[35, 65], color=BAND_STRONG["Yellow"]),
                              dict(range=[65, 100], color=BAND_STRONG["Red"])])))
        fig.update_layout(margin=dict(l=30, r=30, t=30, b=0), title=dict(text="Delay probability"))
        ui.chart(fig, height=250, key="whatif_gauge")
        kind = {"Low Risk": "good", "Medium Risk": "warn", "High Risk": "bad"}[cls]
        icon = {"Low Risk": "●", "Medium Risk": "▲", "High Risk": "■"}[cls]
        st.markdown(f"<div style='text-align:center'>{ui.chip(cls, kind, icon)}</div>", unsafe_allow_html=True)
    with c3:
        d = model.local_drivers(x.iloc[0]).sort_values("impact")
        fig = go.Figure(go.Bar(
            x=d.impact * 100, y=d.label.str.replace(" (AC ÷ EV)", "", regex=False), orientation="h", width=0.55,
            marker_color=[STATUS["critical"] if v > 0 else SERIES[0] for v in d.impact],
            hovertemplate="%{y}<br>%{x:+.1f} pts vs typical<extra></extra>"))
        fig.add_vline(x=0, line=dict(color=INK["muted"], width=1))
        fig.update_layout(title=dict(text="What moves the prediction"),
                          yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11)),
                          xaxis=dict(ticksuffix=" pts", showgrid=True, gridcolor=GRID))
        ui.chart(fig, height=250, key="whatif_drivers")
        ui.note("Red pushes delay risk up · navy pulls it down (vs a typical project).")

with st.expander("Model details & methodology", icon=":material/info:"):
    st.markdown(f"""
- **Target:** `delayed` = project finished after its planned end date.
- **Features:** {", ".join(ml.FEATURE_LABELS.values())}.
- **Live mapping:** budget utilization = actual cost ÷ earned value (1/CPI); open risks as of the snapshot;
  utilisation of the project team over the last 8 weeks; velocity = mean of the last 3 closed sprints;
  tasks remaining = not Done.
- **Selection:** stratified 75/25 split. Candidates compared on 5-fold CV ROC AUC:
  {" · ".join(f"{k} {v:.3f}" for k, v in sorted(model.cv_scores.items(), key=lambda kv: -kv[1]))}.
- **Training data:** {model.n_train + model.n_test} archived project snapshots (2019–2024, `project_history`),
  trained {model.trained_at.replace('T', ' ')}.
- **Explainability:** global permutation importance; local "what-if" attribution resets each feature to the
  training median and measures the change in probability.
- **Caveat:** the archive is synthetic (generated with a known logistic process plus noise), so results
  demonstrate the workflow rather than real-world accuracy.
""")
    if st.button("Retrain model", icon=":material/model_training:"):
        state.delay_model.clear()
        model = ml.train(ctx.data["project_history"])
        ml.save(model)
        st.rerun()

# --------------------------------------------------------------------------- model diagnostics
H2 = 290
det = ui.details("Show details: how accurate the model is and what drives it")
c1, c2, c3 = ui.row(3, parent=det)
with c1, ui.card("cm"):
    ui.card_header("Confusion Matrix", f"Test set ({model.n_test} projects), threshold 0.50")
    cm = model.confusion
    text = [[f"<b>{cm[i, j]}</b><br>{cm[i, j] / cm.sum():.0%}" for j in range(2)] for i in range(2)]
    fig = go.Figure(go.Heatmap(
        z=cm, x=["Pred. on time", "Pred. delayed"], y=["Actual on time", "Actual delayed"],
        colorscale=[[0, SEQ_BLUE[0]], [1, SEQ_BLUE[8]]], showscale=False, xgap=4, ygap=4,
        text=text, texttemplate="%{text}", textfont=dict(size=15),
        hovertemplate="%{y} · %{x}: %{z}<extra></extra>"))
    fig.update_layout(yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                      xaxis=dict(side="top", linecolor="rgba(0,0,0,0)"), margin=dict(t=24))
    ui.chart(fig, height=H2, key="cm")

with c2, ui.card("roc"):
    ui.card_header("ROC Curve", f"Area under curve = {m['roc_auc']:.3f}")
    roc = model.roc
    fig = go.Figure()
    fig.add_scatter(x=[0, 1], y=[0, 1], mode="lines", name="Chance",
                    line=dict(color=INK["muted"], dash="dot", width=1), hoverinfo="skip")
    fig.add_scatter(x=roc.fpr, y=roc.tpr, mode="lines", name=model.model_name,
                    line=dict(color=SERIES[0]), fill="tozeroy", fillcolor=AREA,
                    customdata=roc.threshold.clip(upper=1),
                    hovertemplate="FPR %{x:.2f} · TPR %{y:.2f}<br>Threshold %{customdata:.2f}<extra></extra>")
    fig.update_layout(xaxis=dict(title="False positive rate", range=[0, 1], showgrid=True, gridcolor=GRID),
                      yaxis=dict(title="True positive rate", range=[0, 1.02]), showlegend=False,
                      margin=dict(t=8))
    ui.chart(fig, height=H2, key="roc")

with c3, ui.card("importance"):
    ui.card_header("Feature Importance", "Permutation importance (drop in ROC AUC)")
    imp = model.importance.sort_values("importance")
    fig = go.Figure(go.Bar(
        x=imp.importance, y=imp.label.str.replace(" (AC ÷ EV)", "", regex=False), orientation="h",
        marker_color=SERIES[0], width=0.55,
        error_x=dict(type="data", array=imp["std"], color=INK["muted"], thickness=1),
        hovertemplate="%{y}<br>ΔAUC %{x:.3f}<extra></extra>"))
    fig.update_layout(yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11)),
                      xaxis=dict(showgrid=True, gridcolor=GRID), margin=dict(t=8))
    ui.chart(fig, height=H2, key="importance")

# --------------------------------------------------------------------------- what-if
