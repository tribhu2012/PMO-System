"""Page 9 - Data Import (spreadsheets from Jira, the PMO and HR -> database)."""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import streamlit as st

from projectpulse import importer, metrics
from projectpulse.database import get_engine, import_history, prepare, record_import, replace_all
from projectpulse.ui import components as ui
from projectpulse.ui import state

ctx = state.get_ctx()
engine = get_engine()
ui.page_header("Data Import", "Load the dashboard from the Jira, PMO and HR spreadsheets", "Admin")

log = import_history(engine)
last = log.iloc[0] if len(log) else None
if last is not None:
    src = "the spreadsheets" if last.source == "spreadsheet" else "the synthetic demo generator"
    ui.headline(f"Current data was loaded from <b>{src}</b> on <b>{pd.Timestamp(last.imported_at):%d %b %Y %H:%M}</b>"
                f" and runs to <b>{ctx.data_end:%d %b %Y}</b>.", icon="database")
else:
    ui.headline("No import has been logged yet. The dashboard is showing the demo data.", icon="database")

flash = st.session_state.pop("import_flash", None)
if flash:
    st.success(flash, icon=":material/check_circle:")

# --------------------------------------------------------------------------- step 1
with ui.card("templates"):
    ui.card_header("1 · Get the workbooks", "One workbook per data owner. Keep the sheet names and headers.")
    st.dataframe(pd.DataFrame([
        {"Workbook": f"{key}.xlsx", "Sheets": ", ".join(sheets),
         "Filled in by": ", ".join(dict.fromkeys(importer.SHEETS[s].owner for s in sheets)),
         "Typical refresh": {"jira_export": "Nightly (Jira sync)", "pmo_portfolio": "Weekly",
                             "hr_resources": "Monthly"}[key]}
        for key, (_, sheets) in importer.WORKBOOKS.items()]), hide_index=True, width="stretch")
    ui.note("Dark blue headers are required. Each workbook has an Instructions tab listing every column "
            "and its allowed values. CSV exports from Jira work too: the sheet is recognised by its headers.")

    @st.cache_data(show_spinner=False)
    def _templates() -> dict[str, bytes]:
        return importer.write_workbooks()

    cols = st.columns(4)
    for col, (name, data) in zip(cols, _templates().items()):
        col.download_button(f"Blank {name}", data, file_name=name, icon=":material/download:",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"tpl_{name}", width="stretch")
    if cols[3].button("Export current data", icon=":material/table_view:", width="stretch",
                      help="The data now in the dashboard, in the same three workbooks. "
                           "A good starting point for editing."):
        with st.spinner("Writing workbooks…"):
            st.session_state.export_books = importer.write_workbooks(ctx.data)
    if "export_books" in st.session_state:
        ecols = st.columns(4)
        for col, (name, data) in zip(ecols, st.session_state.export_books.items()):
            col.download_button(f"Current {name}", data, file_name=f"current_{name}",
                                icon=":material/download:", key=f"exp_{name}", width="stretch",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --------------------------------------------------------------------------- step 2
with ui.card("upload"):
    ui.card_header("2 · Upload and check", "Nothing changes until you confirm in step 3.")
    files = st.file_uploader("Workbooks or CSV files", type=["xlsx", "csv"], accept_multiple_files=True,
                             key="import_files", label_visibility="collapsed")
    result = None
    if files:
        raw = [(f.name, f.getvalue()) for f in files]
        digest = hashlib.sha1(b"".join(n.encode() + d for n, d in raw)).hexdigest()
        if st.session_state.get("import_digest") != digest:
            with st.spinner(f"Checking {len(raw)} file(s)…"):
                st.session_state.import_result = importer.validate_files(raw, ctx.data["project_history"])
                st.session_state.import_digest = digest
                st.session_state.import_names = [n for n, _ in raw]
        result = st.session_state.import_result

    if result is not None:
        n_err, n_warn = len(result.errors), len(result.warnings)
        found = result.sheets_found
        chips = "".join(
            f"<span>{ui.chip(name, 'good' if name in found else ('bad' if spec.required else 'neutral'), '✓' if name in found else '·')}</span>"
            for name, spec in importer.SHEETS.items())
        st.markdown(f"<div class='pp-legend'>{chips}</div>", unsafe_allow_html=True)
        if n_err:
            ui.headline(f"<b>{n_err:,} error{'s' if n_err != 1 else ''}</b> to fix before this can be loaded"
                        + (f", plus {n_warn:,} warning{'s' if n_warn != 1 else ''}" if n_warn else "")
                        + ". Fix them in the spreadsheet and upload again.", tone="bad", icon="error")
        else:
            counts = {k: len(v) for k, v in result.tables.items()}
            ui.headline("<b>The files are valid.</b> "
                        + f"{counts['projects']} projects, {counts['tasks']:,} issues, {counts['sprints']} sprints, "
                          f"{counts['risks']} risks, {counts['employees']} people"
                        + (f". {n_warn:,} warning{'s' if n_warn != 1 else ''} to review." if n_warn else "."),
                        tone="good", icon="check_circle")
        if len(result.problems):
            probs = result.problem_frame()
            show = st.segmented_control("Show", ["Errors", "Warnings", "All"],
                                        default="Errors" if n_err else "All", key="prob_filter")
            view = probs if show == "All" else probs[probs.Level == show.rstrip("s")]
            st.dataframe(view.head(2000), hide_index=True, width="stretch", height=320,
                         column_config={"Row": st.column_config.NumberColumn(format="%d"),
                                        "Problem": st.column_config.TextColumn(width="large")})
            if len(view) > 2000:
                ui.note(f"Showing the first 2,000 of {len(view):,}. Download the full list.")
            ui.csv_download(probs, "import_problems.csv", "Download problem list")

# --------------------------------------------------------------------------- step 3
with ui.card("load"):
    ui.card_header("3 · Load into the dashboard",
                   "Replaces all current data in one step. If anything fails, the old data stays.")
    ready = result is not None and result.ok
    sure = st.checkbox("I understand this replaces the data everyone sees", key="import_sure",
                       disabled=not ready)
    if st.button("Replace data and retrain model", type="primary", icon=":material/upload:",
                 disabled=not (ready and sure)):
        try:
            with st.spinner("Loading the database…"):
                counts = replace_all(engine, result.tables)
                as_of = metrics.data_as_of(prepare(result.tables))
                record_import(engine, "spreadsheet", counts, st.session_state.import_names, as_of)
        except Exception as exc:  # constraint violation the validator did not anticipate, lost connection
            st.error(f"The database rejected the load, so nothing was changed. {exc.__class__.__name__}: "
                     f"{str(exc).splitlines()[0]}", icon=":material/error:")
        else:
            for k in ("import_result", "import_digest", "import_sure", "export_books"):
                st.session_state.pop(k, None)
            state.refresh_data()
            st.session_state.import_flash = (f"Loaded {counts['tasks']:,} issues across {counts['projects']} "
                                             f"projects. Data now runs to {as_of:%d %b %Y}. The delay model "
                                             "retrains on the next page view.")
            st.rerun()
    if not ready:
        ui.note("Upload files with no errors to enable this.")

# --------------------------------------------------------------------------- history
with ui.card("history"):
    ui.card_header("Import history", "Every load, newest first")
    if log.empty:
        ui.note("Nothing logged yet.")
    else:
        hist = log.assign(
            rows=log.row_counts.map(lambda j: f"{json.loads(j).get('tasks', 0):,} issues · "
                                              f"{json.loads(j).get('projects', 0)} projects"),
            source=log.source.map({"spreadsheet": "Spreadsheets", "synthetic": "Demo generator"}))
        st.dataframe(hist[["imported_at", "source", "files", "rows", "data_as_of"]], hide_index=True,
                     width="stretch", height="content", column_config={
                         "imported_at": st.column_config.DatetimeColumn("When", format="DD MMM YYYY, HH:mm"),
                         "source": "Source", "files": "Files", "rows": "Rows",
                         "data_as_of": st.column_config.DateColumn("Data as of", format="DD MMM YYYY")})
