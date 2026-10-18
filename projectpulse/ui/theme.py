"""Visual system: design tokens, palette, Plotly template and global CSS.

Direction: a PMO board pack
---------------------------
The dashboards should read like the status report a programme office hands to
a steering committee, not like a SaaS template. That means:

* Type   - a serif (Source Serif 4) for page titles and headline figures, the way
           a printed report sets its numbers; Public Sans for everything you read
           or operate. Numbers use tabular figures so columns line up.
* Colour - one deep navy for identity; a muted, report-style RAG set (green,
           amber, red) that is always paired with a shape and a word.
* Form   - flat cards with hairline borders and small radii, no drop shadows,
           no icon tiles, no pills. Hierarchy comes from type size and spacing.

Colour roles
------------
* ``SERIES``    - categorical identity, assigned in fixed order (never cycled).
* ``STATUS``    - good / warning / serious / critical; never colour alone.
* ``SEQ_BLUE``  - single-hue navy ramp for magnitude (counts, intensity).
* ``DIVERGING`` - navy <-> stone <-> brick for values around a midpoint
                  (e.g. utilisation around 100 %).
* ``PLANNED``, ``AREA``, ``BAND`` - the baseline series, area fills under a line,
                  and the RAG background bands behind trend charts.

Layout primitives (see components.py)
-------------------------------------
* KPI grid  - one HTML grid, one column per card (four on most pages).
* Cards     - keyed ``st.container(border=True, height="stretch")``; cards in the
              same row stretch to the tallest one, styled via ``.st-key-card_*``.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --------------------------------------------------------------------------- tokens
NAVY = "#1f3a5c"
SERIES = ["#1f3a5c", "#c06a2b", "#3b8075", "#8a9bb4", "#8c5a86", "#7a8a3a", "#c9a24f", "#a3473b"]
STATUS = {"good": "#2f7d4f", "warning": "#c9961c", "serious": "#cc6c3a", "critical": "#b5392d"}
RAG_COLORS = {"Green": STATUS["good"], "Yellow": STATUS["warning"], "Red": STATUS["critical"],
              "Grey": "#a1a6ae"}
RAG_ICONS = {"Green": "●", "Yellow": "▲", "Red": "■", "Grey": "○"}
# Plain-text status for tables (shape + word; table cells cannot be coloured).
RAG_EMOJI = {"Green": "● Green", "Yellow": "▲ Yellow", "Red": "■ Red", "Grey": "○ n/a"}
PROJECT_STATUS_COLORS = {"On Track": STATUS["good"], "At Risk": STATUS["warning"],
                         "Delayed": STATUS["critical"], "Completed": "#8a9bb4"}
SEVERITY_COLORS = {"High": STATUS["critical"], "Medium": STATUS["serious"], "Low": "#c9ccd2"}
DELAY_CLASS_COLORS = {"Low Risk": STATUS["good"], "Medium Risk": STATUS["warning"],
                      "High Risk": STATUS["critical"]}

SEQ_BLUE = ["#e6ebf2", "#d3dce8", "#bfcbdc", "#aabace", "#94a8c1", "#7e96b3", "#6884a5",
            "#537296", "#406186", "#2f5076", "#1f3a5c", "#172d48", "#102136"]
DIVERGING = [[0.0, "#2f5076"], [0.25, "#94a8c1"], [0.5, "#eeeeec"], [0.75, "#d9958a"],
             [1.0, "#a3352a"]]

PLANNED = "#c5cfdc"  # baseline / committed series next to an actual
AREA = "rgba(31,58,92,0.07)"  # fill under a navy line
BAND = {"Green": "rgba(47,125,79,0.07)", "Yellow": "rgba(201,150,28,0.09)", "Red": "rgba(181,57,45,0.06)"}
BAND_STRONG = {"Green": "rgba(47,125,79,0.20)", "Yellow": "rgba(201,150,28,0.24)",
               "Red": "rgba(181,57,45,0.18)"}

INK = {"primary": "#15191f", "secondary": "#4a505b", "muted": "#7d838d"}
GRID = "#eceef1"
AXIS = "#cfd3d9"
SURFACE = "#ffffff"
PAGE = "#f3f4f6"
BORDER = "#dfe2e7"
ACCENT_SOFT = "#e9eef4"
FONT = '"Public Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
SERIF = '"Source Serif 4", "Source Serif Pro", Georgia, "Times New Roman", serif'
FONTS_URL = ("https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700"
             "&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&display=swap")


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
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=AXIS,
                        font=dict(family=FONT, size=12, color=INK["primary"])),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(size=11.5, color=INK["secondary"]), title_text="",
                    traceorder="normal"),
        xaxis=dict(showgrid=False, linecolor=AXIS, ticks="", tickfont=dict(color=INK["muted"], size=11),
                   title=dict(font=dict(color=INK["muted"], size=11.5)), zeroline=False, automargin=True),
        yaxis=dict(gridcolor=GRID, gridwidth=1, linecolor="rgba(0,0,0,0)",
                   tickfont=dict(color=INK["muted"], size=11),
                   title=dict(font=dict(color=INK["muted"], size=11.5)), zeroline=False, automargin=True),
        bargap=0.34,
        bargroupgap=0.08,
        barcornerradius=1,
        coloraxis=dict(colorbar=dict(outlinewidth=0, thickness=10, tickfont=dict(color=INK["muted"]))),
    )
    template.data.scatter = [go.Scatter(line=dict(width=2), marker=dict(size=7, line=dict(width=0)))]
    template.data.bar = [go.Bar(marker=dict(line=dict(width=0)))]
    pio.templates["projectpulse"] = template
    pio.templates.default = "projectpulse"


CSS = f"""
<style>
@import url("{FONTS_URL}");
:root {{
  --pp-bg: {PAGE};
  --pp-surface: {SURFACE};
  --pp-border: {BORDER};
  --pp-rule: {GRID};
  --pp-ink: {INK['primary']};
  --pp-ink-2: {INK['secondary']};
  --pp-muted: {INK['muted']};
  --pp-accent: {NAVY};
  --pp-accent-soft: {ACCENT_SOFT};
  --pp-good: {STATUS['good']};
  --pp-warn: {STATUS['warning']};
  --pp-bad: {STATUS['critical']};
  --pp-radius: 6px;
  --pp-sans: {FONT};
  --pp-serif: {SERIF};
}}

/* ---------- base type ---------- */
html, body, .stApp, [data-testid="stMarkdownContainer"], [data-testid="stSidebar"], button, input, textarea {{
  font-family: var(--pp-sans); }}
.stApp {{ font-feature-settings: "tnum" 1, "lnum" 1; }}

/* ---------- page frame ---------- */
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.4rem; padding-bottom: 3rem; padding-left: 2.2rem; padding-right: 2.2rem;
  max-width: 1400px; }}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] {{ background: #fbfbfc; border-right: 1px solid var(--pp-border); }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {{ border-radius: 4px; margin: 0; padding-top: 3px;
  padding-bottom: 3px; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {{ color: var(--pp-ink-2); font-weight: 500;
  font-size: 13.5px; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {{ background: #f0f2f5; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{ background: var(--pp-accent-soft); }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] span {{
  color: var(--pp-accent); font-weight: 600; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{
  color: var(--pp-muted) !important; font-size: 11.5px; font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase; }}
section[data-testid="stSidebar"] hr {{ margin: 0.7rem 0; border-color: var(--pp-border); }}
section[data-testid="stSidebar"] label p {{ font-size: 12.5px; font-weight: 500; color: var(--pp-ink-2); }}
.pp-side-title {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--pp-muted);
  font-weight: 600; }}
.pp-side-foot {{ font-size: 12px; color: var(--pp-muted); line-height: 1.5; }}
.pp-side-foot b {{ color: var(--pp-ink-2); font-weight: 600; }}

/* ---------- page header ---------- */
.pp-header {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 8px 24px;
  flex-wrap: wrap; padding-bottom: 14px; margin-bottom: 18px; border-bottom: 1px solid var(--pp-border); }}
.pp-title {{ font-family: var(--pp-serif); font-size: 32px; font-weight: 600; color: var(--pp-ink);
  letter-spacing: -0.01em; line-height: 1.15; }}
.pp-subtitle {{ color: var(--pp-ink-2); font-size: 14px; margin-top: 6px; }}
.pp-context {{ font-size: 13px; color: var(--pp-muted); text-align: right; line-height: 1.6; }}
.pp-context b {{ color: var(--pp-ink-2); font-weight: 600; }}
.pp-context .pp-sep {{ margin: 0 8px; color: var(--pp-border); }}
.pp-ms {{ font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1;
  letter-spacing: normal; text-transform: none; white-space: nowrap; direction: ltr;
  -webkit-font-feature-settings: 'liga'; font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; }}

/* ---------- headline: the page's answer, set as a statement ---------- */
.pp-headline {{ display: flex; gap: 12px; align-items: baseline; margin: 0 0 20px; max-width: 980px;
  font-size: 17px; line-height: 1.55; color: var(--pp-ink-2); }}
.pp-headline b {{ color: var(--pp-ink); font-weight: 600; }}
.pp-headline .pp-mark {{ flex: none; width: 10px; height: 10px; border-radius: 1px; background: var(--pp-accent);
  transform: translateY(-1px); }}
.pp-hl-good .pp-mark {{ background: var(--pp-good); }}
.pp-hl-warn .pp-mark {{ background: var(--pp-warn); }}
.pp-hl-bad  .pp-mark {{ background: var(--pp-bad); }}

/* ---------- KPI grid ---------- */
.pp-kpis {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }}
.pp-kpis-4 {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
.pp-kpis-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
@media (max-width: 1280px) {{ .pp-kpis {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  .pp-kpis-4 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
@media (max-width: 640px)  {{ .pp-kpis, .pp-kpis-3 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }} }}
.pp-kpi {{ background: var(--pp-surface); border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
  padding: 16px 18px 14px; display: flex; flex-direction: column; gap: 6px; min-height: 128px; min-width: 0; }}
.pp-kpi-label {{ display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--pp-ink-2);
  font-weight: 500; line-height: 1.3; }}
.pp-kpi-label .pp-dot {{ flex: none; width: 8px; height: 8px; border-radius: 1px; background: var(--pp-border); }}
.pp-tone-good .pp-dot {{ background: var(--pp-good); }}
.pp-tone-warn .pp-dot {{ background: var(--pp-warn); }}
.pp-tone-bad  .pp-dot {{ background: var(--pp-bad); }}
.pp-tone-violet .pp-dot, .pp-tone-accent .pp-dot {{ background: var(--pp-accent); }}
.pp-kpi-value {{ font-family: var(--pp-serif); font-size: 34px; font-weight: 600; color: var(--pp-ink);
  letter-spacing: -0.01em; line-height: 1.1; display: flex; align-items: baseline; gap: 10px;
  flex-wrap: nowrap; min-width: 0; font-variant-numeric: lining-nums tabular-nums; }}
.pp-kpi-value .pp-chip {{ flex: none; font-family: var(--pp-sans); }}
.pp-kpi-sub {{ margin-top: auto; font-size: 12.5px; color: var(--pp-muted); line-height: 1.4;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}

/* ---------- status chips: shape + word, no fill ---------- */
.pp-chip {{ display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600;
  white-space: nowrap; line-height: 1.4; letter-spacing: 0; }}
.pp-chip span {{ font-size: 10px; }}
.pp-good {{ color: var(--pp-good); }}
.pp-warn {{ color: #9a7210; }}
.pp-warn span {{ color: var(--pp-warn); }}
.pp-bad  {{ color: var(--pp-bad); }}
.pp-neutral {{ color: var(--pp-muted); }}

/* ---------- cards ---------- */
[class*="st-key-card_"] {{ background: var(--pp-surface); border-color: var(--pp-border) !important;
  border-radius: var(--pp-radius) !important; box-shadow: none; padding: 18px 20px 16px 20px !important; }}
.pp-card-title {{ font-size: 15px; font-weight: 600; color: var(--pp-ink); line-height: 1.3; }}
.pp-card-caption {{ font-size: 12.5px; color: var(--pp-muted); margin-top: 2px; line-height: 1.4; }}
.pp-action {{ font-size: 13px; color: var(--pp-ink-2); line-height: 1.5; padding: 9px 0;
  border-top: 1px solid var(--pp-rule); }}
.pp-action b {{ color: var(--pp-ink); }}
.pp-note {{ font-size: 12px; color: var(--pp-muted); }}
.pp-legend {{ display: flex; gap: 14px; flex-wrap: wrap; font-size: 12.5px; color: var(--pp-ink-2);
  align-items: center; }}
[class*="st-key-card_"] [data-testid="stPlotlyChart"] {{ background: transparent; }}

/* ---------- decision list: one equal column per project ---------- */
.pp-decisions {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0; margin-top: 14px; }}
@media (max-width: 1100px) {{ .pp-decisions {{ grid-template-columns: minmax(0, 1fr); }} }}
.pp-decision {{ display: flex; flex-direction: column; gap: 6px; padding: 2px 22px; min-width: 0;
  border-left: 1px solid var(--pp-rule); }}
.pp-decision:first-child {{ padding-left: 0; border-left: none; }}
@media (max-width: 1100px) {{ .pp-decision {{ padding: 14px 0; border-left: none; border-top: 1px solid var(--pp-rule); }}
  .pp-decision:first-child {{ border-top: none; padding-top: 4px; }} }}
.pp-dhead {{ display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }}
.pp-dscore {{ font-family: var(--pp-serif); font-size: 28px; font-weight: 600; color: var(--pp-ink);
  line-height: 1; font-variant-numeric: lining-nums tabular-nums; }}
.pp-dname {{ font-size: 15px; font-weight: 600; color: var(--pp-ink); line-height: 1.3; }}
.pp-dpm {{ font-size: 12.5px; color: var(--pp-muted); margin-top: -4px; }}
.pp-dwhy {{ font-size: 13.5px; color: var(--pp-ink-2); line-height: 1.5; }}
.pp-ddo {{ font-size: 13.5px; color: var(--pp-ink); line-height: 1.5; margin-top: auto; padding-top: 10px;
  border-top: 1px solid var(--pp-rule); }}
.pp-ddo b {{ display: block; font-size: 12px; font-weight: 600; color: var(--pp-accent); margin-bottom: 2px; }}

/* ---------- widgets ---------- */
[data-testid="stMetricValue"] {{ font-family: var(--pp-serif); font-size: 1.45rem; font-weight: 600; color: var(--pp-ink); }}
[data-testid="stMetricLabel"] p {{ font-size: 12px; color: var(--pp-muted); }}
[data-testid="stExpander"] details {{ background: transparent; border-radius: var(--pp-radius);
  border-color: var(--pp-border); }}
[data-testid="stExpander"] summary p {{ font-weight: 600; color: var(--pp-ink-2); font-size: 14px; }}
[data-testid="stChatMessage"] {{ background: #f7f8f9; border-radius: var(--pp-radius); padding: 12px 14px; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
