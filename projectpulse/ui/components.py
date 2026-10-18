"""Reusable Streamlit UI components: page header, KPI grid, cards, charts, exports.

Layout rules
------------
* Every page opens with ``page_header``, a one-sentence ``headline`` (the answer
  first) and a ``kpi_grid`` of four cards: the numbers a stakeholder needs.
* Secondary charts go inside ``details()``, collapsed by default. The sidebar's
  "Analyst view" switch expands them all.
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
TONES = {"accent": "pp-tone-accent", "good": "pp-tone-good", "warn": "pp-tone-warn", "bad": "pp-tone-bad",
         "violet": "pp-tone-violet"}


# --------------------------------------------------------------------------- header
def page_header(title: str, subtitle: str, eyebrow: str = "", ctx=None, note: str = "") -> None:
    """Title block, with the active filter scope as a plain line of text on the right.

    ``eyebrow`` is accepted for compatibility; the sidebar already shows the section.
    """
    scope = []
    if ctx is not None:
        f = ctx.f
        scope.append(f"<b>{f.start:%d %b %Y} – {f.end:%d %b %Y}</b>")
        scope.append(html.escape("All departments" if f.dept_all else ", ".join(f.departments)))
        scope.append(html.escape(
            "All projects" if not f.project_labels else
            (f.project_labels[0].replace("Project ", "") if len(f.project_labels) == 1
             else f"{len(f.project_labels)} projects")))
    if note:
        scope.append(note)
    sep = "<span class='pp-sep'>|</span>"
    st.markdown(
        f"""<div class="pp-header"><div>
        <div class="pp-title">{html.escape(title)}</div>
        <div class="pp-subtitle">{html.escape(subtitle)}</div></div>
        <div class="pp-context">{sep.join(scope)}</div></div>""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- KPIs
def chip(text: str, kind: str = "neutral", icon: str = "") -> str:
    icon_html = f"<span aria-hidden='true'>{icon}</span>" if icon else ""  # shape keeps status readable without colour
    return f"<span class='pp-chip {CHIP_CLASS[kind]}'>{icon_html}{html.escape(text)}</span>"


def rag_chip(rag: str) -> str:
    return chip(rag, RAG_KIND.get(rag, "neutral"), RAG_ICONS.get(rag, ""))


def kpi_card(label: str, value: str, sub: str = "", badge: str = "", help: str = "",
             icon: str = "monitoring", tone: str = "accent") -> str:
    """``icon`` is accepted for compatibility; cards carry a small status square instead."""
    title = f" title='{html.escape(help)}'" if help else ""
    return (f"<div class='pp-kpi {TONES.get(tone, 'pp-tone-accent')}'{title}>"
            f"<div class='pp-kpi-label'><span class='pp-dot'></span>{html.escape(label)}</div>"
            f"<div class='pp-kpi-value'><span>{value}</span>{badge}</div>"
            f"<div class='pp-kpi-sub'>{sub}</div></div>")


def kpi_grid(cards: Sequence[dict]) -> None:
    """Render KPI cards in one CSS grid (one column per card on desktop, 2 on tablet and phone)."""
    st.markdown(f"<div class='pp-kpis pp-kpis-{len(cards)}'>" + "".join(kpi_card(**c) for c in cards)
                + "</div>", unsafe_allow_html=True)


def headline(text: str, tone: str = "neutral", icon: str = "lightbulb") -> None:
    """The page's takeaway in one sentence, shown above the numbers. ``text`` may contain <b>.
    The square takes the tone's colour; ``icon`` is accepted for compatibility."""
    st.markdown(f"<div class='pp-headline pp-hl-{tone}'><span class='pp-mark'></span><div>{text}</div></div>",
                unsafe_allow_html=True)


kpi_row = kpi_grid  # backwards-compatible name


# --------------------------------------------------------------------------- cards
def row(spec=2, gap: str = "medium", parent=None):
    """Columns for a row of cards (cards inside stretch to equal height)."""
    return (parent or st).columns(spec, gap=gap)


def details(label: str = "Show details"):
    """Collapsed section for secondary charts; open when the sidebar's Analyst view is on."""
    return st.expander(label, expanded=bool(st.session_state.get("analyst_view")),
                       icon=":material/unfold_more:")


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
