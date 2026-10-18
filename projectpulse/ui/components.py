"""Reusable Streamlit UI components: page header, KPI grid, cards, charts, exports.

Layout rules
------------
* Every page opens with ``page_header`` and a ``kpi_grid`` of exactly six cards,
  so KPI cards have the same width and height on every page.
* Content lives in ``card`` containers. Cards placed in the same ``row`` stretch
  to equal height; charts that sit side by side use the same plot height.
"""
from __future__ import annotations

import html
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .theme import RAG_ICONS, SURFACE

PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines",
                               "zoomIn2d", "zoomOut2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

CHIP_CLASS = {"good": "pp-good", "warn": "pp-warn", "bad": "pp-bad", "neutral": "pp-neutral"}
RAG_KIND = {"Green": "good", "Yellow": "warn", "Red": "bad", "Grey": "neutral"}
TONES = {"accent": "", "good": "pp-tone-good", "warn": "pp-tone-warn", "bad": "pp-tone-bad",
         "violet": "pp-tone-violet"}


def _icon(name: str) -> str:
    """Material Symbols ligature (font ships with Streamlit)."""
    return f"<span class='pp-ms' aria-hidden='true'>{name}</span>"


# --------------------------------------------------------------------------- header
def page_header(title: str, subtitle: str, eyebrow: str = "", ctx=None, note: str = "") -> None:
    """Title block plus pills summarising the active filters (so users always know the scope)."""
    pills = []
    if ctx is not None:
        f = ctx.f
        pills.append(f"<span class='pp-pill'>{_icon('calendar_month')}<b>{f.start:%d %b %Y}</b>"
                     f"– <b>{f.end:%d %b %Y}</b></span>")
        dept = "All departments" if f.dept_all else ", ".join(f.departments)
        pills.append(f"<span class='pp-pill'>{_icon('apartment')}{html.escape(dept)}</span>")
        proj = ("All projects" if not f.project_labels else
                (f.project_labels[0].replace("Project ", "") if len(f.project_labels) == 1
                 else f"{len(f.project_labels)} projects"))
        pills.append(f"<span class='pp-pill'>{_icon('folder')}{html.escape(proj)}</span>")
    if note:
        pills.append(f"<span class='pp-pill'>{_icon('info')}{note}</span>")
    st.markdown(
        f"""<div class="pp-header"><div>
        {f'<div class="pp-eyebrow">{html.escape(eyebrow)}</div>' if eyebrow else ''}
        <div class="pp-title">{html.escape(title)}</div>
        <div class="pp-subtitle">{html.escape(subtitle)}</div></div>
        <div class="pp-context">{''.join(pills)}</div></div>""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- KPIs
def chip(text: str, kind: str = "neutral", icon: str = "") -> str:
    icon_html = f"<span aria-hidden='true'>{icon}</span>" if icon else ""
    return f"<span class='pp-chip {CHIP_CLASS[kind]}'>{icon_html}{html.escape(text)}</span>"


def rag_chip(rag: str) -> str:
    return chip(rag, RAG_KIND.get(rag, "neutral"), RAG_ICONS.get(rag, ""))


def kpi_card(label: str, value: str, sub: str = "", badge: str = "", help: str = "",
             icon: str = "monitoring", tone: str = "accent") -> str:
    title = f" title='{html.escape(help)}'" if help else ""
    return (f"<div class='pp-kpi {TONES.get(tone, '')}'{title}>"
            f"<div class='pp-kpi-top'><div class='pp-kpi-icon'>{_icon(icon)}</div>"
            f"<div class='pp-kpi-label'>{html.escape(label)}</div></div>"
            f"<div class='pp-kpi-value'><span>{value}</span>{badge}</div>"
            f"<div class='pp-kpi-sub'>{sub}</div></div>")


def kpi_grid(cards: Sequence[dict]) -> None:
    """Render KPI cards in one CSS grid (6 columns desktop, 3 tablet, 2 phone)."""
    st.markdown("<div class='pp-kpis'>" + "".join(kpi_card(**c) for c in cards) + "</div>",
                unsafe_allow_html=True)


kpi_row = kpi_grid  # backwards-compatible name


# --------------------------------------------------------------------------- cards
def row(spec=2, gap: str = "medium"):
    """Columns for a row of cards (cards inside stretch to equal height)."""
    return st.columns(spec, gap=gap)


@contextmanager
def card(key: str) -> Iterator[None]:
    """White, bordered card. Fills the full height of its row."""
    with st.container(border=True, height="stretch", key=f"card_{key}"):
        yield


def card_header(title: str, caption: str = "", controls: float = 0.0):
    """Card title + caption. With ``controls`` > 0 returns a right-aligned column for widgets."""
    text = (f"<div class='pp-card-title'>{html.escape(title)}</div>"
            + (f"<div class='pp-card-caption'>{html.escape(caption)}</div>" if caption else ""))
    if controls <= 0:
        st.markdown(text, unsafe_allow_html=True)
        return None
    left, right = st.columns([1 - controls, controls], vertical_alignment="center", gap="small")
    left.markdown(text, unsafe_allow_html=True)
    return right


def section(title: str, caption: str = "") -> None:  # retained for compatibility
    card_header(title, caption)


def note(text: str) -> None:
    st.markdown(f"<div class='pp-note'>{text}</div>", unsafe_allow_html=True)


def chart(fig: go.Figure, height: int = 320, key: str | None = None) -> None:
    # Explicit backgrounds: Streamlit's frontend overrides template-level paper/plot colours.
    fig.update_layout(height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=key, theme=None)


def csv_download(df: pd.DataFrame, filename: str, label: str = "Export CSV",
                 key: str | None = None) -> None:
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=filename,
                       mime="text/csv", icon=":material/download:", key=key or f"dl_{filename}",
                       type="tertiary")


def empty_state(message: str = "No data for the current filters.") -> None:
    st.info(message, icon=":material/filter_alt_off:")


# --------------------------------------------------------------------------- formatting
def fmt_money(x: float, decimals: int = 1) -> str:
    if pd.isna(x):
        return "–"
    sign, x = ("-" if x < 0 else ""), abs(x)
    if x >= 1e6:
        return f"{sign}${x / 1e6:,.{decimals}f}M"
    if x >= 1e3:
        return f"{sign}${x / 1e3:,.0f}K"
    return f"{sign}${x:,.0f}"


def fmt_pct(x: float, decimals: int = 0) -> str:
    return "–" if pd.isna(x) else f"{x:.{decimals}%}"


def fmt_num(x: float, decimals: int = 0) -> str:
    return "–" if pd.isna(x) else f"{x:,.{decimals}f}"
