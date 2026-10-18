"""ProjectPulse - Project Portfolio Management & Agile Analytics Platform.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from projectpulse import config
from projectpulse.ui import state
from projectpulse.ui.theme import inject_css, register_plotly_template

st.set_page_config(
    page_title=f"{config.APP_NAME} · {config.COMPANY_NAME}",
    page_icon="assets/icon.svg",
    layout="wide",
    initial_sidebar_state="auto",
)
register_plotly_template()
inject_css()
st.logo("assets/logo.svg", icon_image="assets/icon.svg", size="large")

data = state.load_data()

pages = {
    "Overview": [
        st.Page("views/executive.py", title="Executive Dashboard", icon=":material/space_dashboard:",
                default=True, url_path="executive"),
        st.Page("views/portfolio.py", title="Project Portfolio", icon=":material/folder_open:",
                url_path="portfolio"),
    ],
    "Delivery": [
        st.Page("views/resources.py", title="Resource Management", icon=":material/groups:",
                url_path="resources"),
        st.Page("views/risks.py", title="Risk Management", icon=":material/warning:",
                url_path="risks"),
        st.Page("views/scrum.py", title="Scrum Analytics", icon=":material/sprint:",
                url_path="scrum"),
        st.Page("views/team.py", title="Team Performance", icon=":material/military_tech:",
                url_path="team"),
    ],
    "Intelligence": [
        st.Page("views/predictive.py", title="Predictive Analytics", icon=":material/insights:",
                url_path="predictive"),
        st.Page("views/insights.py", title="AI Insights", icon=":material/auto_awesome:",
                url_path="insights"),
    ],
}
nav = st.navigation(pages, position="sidebar")

filters = state.sidebar_filters(data)
st.session_state.ctx = state.build_context(data, filters)

with st.sidebar:
    st.divider()
    foot, refresh = st.columns([3, 2], vertical_alignment="center")
    foot.markdown(f"<div class='pp-side-foot'>Data as of<br><b>{state.metrics.data_as_of(data):%d %b %Y}</b></div>",
                  unsafe_allow_html=True)
    if refresh.button("Refresh", icon=":material/refresh:", type="tertiary",
                      help="Reload from the database and clear cached metrics"):
        state.refresh_data()
        st.rerun()

nav.run()
