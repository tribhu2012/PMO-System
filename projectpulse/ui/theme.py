"""Visual system: design tokens, palette, Plotly template and global CSS.

Colour roles
------------
* ``SERIES``    - categorical identity, assigned in fixed order (never cycled).
* ``STATUS``    - reserved for good / warning / serious / critical states and
                  always paired with an icon + label, never colour alone.
* ``SEQ_BLUE``  - single-hue ramp for magnitude (counts, intensity).
* ``DIVERGING`` - blue <-> grey <-> red for values with a meaningful midpoint
                  (e.g. utilisation around 100 %).

Layout primitives (see components.py)
-------------------------------------
* KPI grid  - one HTML grid, always 6 columns on desktop, so every KPI card on
              every page has identical width and height.
* Cards     - keyed ``st.container(border=True, height="stretch")``; cards in the
              same row stretch to the tallest one, styled via ``.st-key-card_*``.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --------------------------------------------------------------------------- tokens
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
RAG_COLORS = {"Green": STATUS["good"], "Yellow": STATUS["warning"], "Red": STATUS["critical"],
              "Grey": "#9ca3af"}
RAG_ICONS = {"Green": "●", "Yellow": "▲", "Red": "■", "Grey": "○"}
RAG_EMOJI = {"Green": "🟢 Green", "Yellow": "🟡 Yellow", "Red": "🔴 Red", "Grey": "⚪ n/a"}
PROJECT_STATUS_COLORS = {"On Track": STATUS["good"], "At Risk": STATUS["warning"],
                         "Delayed": STATUS["critical"], "Completed": SERIES[0]}
SEVERITY_COLORS = {"High": STATUS["critical"], "Medium": STATUS["serious"], "Low": "#c4c8d0"}
DELAY_CLASS_COLORS = {"Low Risk": STATUS["good"], "Medium Risk": STATUS["warning"],
                      "High Risk": STATUS["critical"]}

SEQ_BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
            "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
DIVERGING = [[0.0, "#1c5cab"], [0.25, "#86b6ef"], [0.5, "#f0efec"], [0.75, "#ec8a8a"],
             [1.0, "#b83232"]]

INK = {"primary": "#111827", "secondary": "#4b5563", "muted": "#8a919e"}
GRID = "#eef0f4"
AXIS = "#d5d9e0"
SURFACE = "#ffffff"
PAGE = "#f6f7fb"
BORDER = "#e4e7ee"
ACCENT_SOFT = "#eaf2fc"
FONT = 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'


def register_plotly_template() -> None:
    template = go.layout.Template()
    template.layout = go.Layout(
        font=dict(family=FONT, size=12, color=INK["secondary"]),
        title=dict(font=dict(size=13, color=INK["primary"]), x=0, xanchor="left", y=0.98),
        colorway=SERIES,
        paper_bgcolor=SURFACE,  # Streamlit paints the chart container; keep charts on the card's white
        plot_bgcolor=SURFACE,
        margin=dict(l=4, r=8, t=28, b=4),
        hovermode="closest",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=BORDER,
                        font=dict(family=FONT, size=12, color=INK["primary"])),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(size=11.5, color=INK["secondary"]), title_text="",
                    traceorder="normal"),
        xaxis=dict(showgrid=False, linecolor=AXIS, ticks="", tickfont=dict(color=INK["muted"], size=11),
                   title=dict(font=dict(color=INK["muted"], size=11.5)), zeroline=False, automargin=True),
        yaxis=dict(gridcolor=GRID, gridwidth=1, linecolor="rgba(0,0,0,0)",
                   tickfont=dict(color=INK["muted"], size=11),
                   title=dict(font=dict(color=INK["muted"], size=11.5)), zeroline=False, automargin=True),
        bargap=0.32,
        bargroupgap=0.08,
        barcornerradius=4,
        coloraxis=dict(colorbar=dict(outlinewidth=0, thickness=10, tickfont=dict(color=INK["muted"]))),
    )
    template.data.scatter = [go.Scatter(line=dict(width=2), marker=dict(size=8, line=dict(width=0)))]
    template.data.bar = [go.Bar(marker=dict(line=dict(width=0)))]
    pio.templates["projectpulse"] = template
    pio.templates.default = "projectpulse"


CSS = f"""
<style>
:root {{
  --pp-bg: {PAGE};
  --pp-surface: {SURFACE};
  --pp-border: {BORDER};
  --pp-ink: {INK['primary']};
  --pp-ink-2: {INK['secondary']};
  --pp-muted: {INK['muted']};
  --pp-accent: {SERIES[0]};
  --pp-accent-soft: {ACCENT_SOFT};
  --pp-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.04);
  --pp-radius: 14px;
}}

/* ---------- page frame ---------- */
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; padding-left: 2rem; padding-right: 2rem;
  max-width: 1440px; }}

/* ---------- sidebar (light) ---------- */
section[data-testid="stSidebar"] {{ background: #ffffff; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {{ border-radius: 8px; margin: 1px 0; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {{ color: #374151; font-weight: 500; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {{ background: #f4f6fa; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{
  background: var(--pp-accent-soft); }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] span {{
  color: #1d5fb4; font-weight: 600; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{
  color: #9aa1ad !important; text-transform: uppercase; letter-spacing: .08em; font-size: 11px; font-weight: 600; }}
section[data-testid="stSidebar"] hr {{ margin: 0.6rem 0; border-color: var(--pp-border); }}
section[data-testid="stSidebar"] label p {{ font-size: 12.5px; font-weight: 500; color: #4b5563; }}
.pp-side-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #9aa1ad;
  font-weight: 600; }}
.pp-side-foot {{ font-size: 11.5px; color: #9aa1ad; line-height: 1.5; }}

/* ---------- page header ---------- */
.pp-header {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 16px;
  flex-wrap: wrap; margin-bottom: 14px; }}
.pp-eyebrow {{ font-size: 11.5px; font-weight: 600; color: var(--pp-accent); text-transform: uppercase;
  letter-spacing: .08em; margin-bottom: 4px; }}
.pp-title {{ font-size: 26px; font-weight: 700; color: var(--pp-ink); letter-spacing: -0.02em; line-height: 1.2; }}
.pp-subtitle {{ color: var(--pp-ink-2); font-size: 14px; margin-top: 4px; }}
.pp-context {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.pp-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border-radius: 999px;
  background: var(--pp-surface); border: 1px solid var(--pp-border); font-size: 12.5px; color: var(--pp-ink-2);
  white-space: nowrap; box-shadow: var(--pp-shadow); }}
.pp-pill b {{ color: var(--pp-ink); font-weight: 600; }}
.pp-ms {{ font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1;
  letter-spacing: normal; text-transform: none; white-space: nowrap; direction: ltr;
  -webkit-font-feature-settings: 'liga'; font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; }}
.pp-pill .pp-ms {{ font-size: 15px; color: var(--pp-muted); }}

/* ---------- KPI grid ---------- */
.pp-kpis {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin-bottom: 10px; }}
@media (max-width: 1280px) {{ .pp-kpis {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
@media (max-width: 640px)  {{ .pp-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }} }}
.pp-kpi {{ background: var(--pp-surface); border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
  box-shadow: var(--pp-shadow); padding: 14px 16px; display: flex; flex-direction: column;
  gap: 8px; min-height: 136px; min-width: 0; }}
.pp-kpi-top {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
.pp-kpi-icon {{ flex: none; width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center;
  background: var(--pp-accent-soft); color: var(--pp-accent); font-size: 18px; }}
.pp-kpi-label {{ font-size: 12.5px; color: var(--pp-ink-2); font-weight: 500; line-height: 1.25;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
.pp-kpi-value {{ font-size: 26px; font-weight: 700; color: var(--pp-ink); letter-spacing: -0.02em; line-height: 1.1;
  display: flex; align-items: center; gap: 8px; flex-wrap: nowrap; min-width: 0; }}
.pp-kpi-value .pp-chip {{ flex: none; }}
.pp-kpi-sub {{ margin-top: auto; font-size: 12px; color: var(--pp-muted); line-height: 1.4;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
.pp-tone-good .pp-kpi-icon {{ background: rgba(12,163,12,0.10); color: #0a7f0a; }}
.pp-tone-warn .pp-kpi-icon {{ background: rgba(250,178,25,0.16); color: #a86b00; }}
.pp-tone-bad  .pp-kpi-icon {{ background: rgba(208,59,59,0.10); color: #b42f2f; }}
.pp-tone-violet .pp-kpi-icon {{ background: rgba(98,80,214,0.10); color: #5141c2; }}

/* ---------- chips ---------- */
.pp-chip {{ display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px;
  font-size: 11.5px; font-weight: 600; letter-spacing: 0; white-space: nowrap; line-height: 1.5; }}
.pp-good {{ color: #0a6e0a; background: rgba(12,163,12,0.10); }}
.pp-warn {{ color: #8a5a00; background: rgba(250,178,25,0.18); }}
.pp-bad  {{ color: #a52828; background: rgba(208,59,59,0.10); }}
.pp-neutral {{ color: var(--pp-ink-2); background: #f1f3f8; }}

/* ---------- cards ---------- */
[class*="st-key-card_"] {{ background: var(--pp-surface); border-color: var(--pp-border) !important;
  border-radius: var(--pp-radius) !important; box-shadow: var(--pp-shadow); padding: 18px 20px 16px 20px !important; }}
.pp-card-title {{ font-size: 15px; font-weight: 600; color: var(--pp-ink); line-height: 1.3; }}
.pp-card-caption {{ font-size: 12.5px; color: var(--pp-muted); margin-top: 2px; line-height: 1.4; }}
.pp-action {{ font-size: 13px; color: var(--pp-ink-2); line-height: 1.5; padding: 9px 0;
  border-top: 1px solid var(--pp-border); }}
.pp-action b {{ color: var(--pp-ink); }}
.pp-note {{ font-size: 12px; color: var(--pp-muted); }}
.pp-legend {{ display: flex; gap: 14px; flex-wrap: wrap; font-size: 12.5px; color: var(--pp-ink-2);
  align-items: center; }}

[class*="st-key-card_"] [data-testid="stPlotlyChart"] {{ background: transparent; }}

/* ---------- widgets ---------- */
[data-testid="stMetricValue"] {{ font-size: 1.3rem; font-weight: 700; color: var(--pp-ink); }}
[data-testid="stMetricLabel"] p {{ font-size: 12px; color: var(--pp-muted); }}
[data-testid="stExpander"] details {{ background: var(--pp-surface); border-radius: var(--pp-radius); }}
[data-testid="stChatMessage"] {{ background: #f8f9fc; border-radius: 12px; padding: 12px 14px; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
