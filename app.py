"""Streamlit UI for manual ETL execution."""
from __future__ import annotations

import json
import logging
from io import StringIO

import streamlit as st

from etl import incremental_sync, initial_full_sync, load_state
from sheets import GoogleSheetsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class UILogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.stream = StringIO()

    def emit(self, record: logging.LogRecord) -> None:
        self.stream.write(self.format(record) + "\n")

    def get_logs(self) -> str:
        return self.stream.getvalue()


def render_status_panel() -> None:
    state = load_state()
    last_sync = state.get("last_sync_timestamp")

    deals_count = "N/A"
    try:
        deals_count = GoogleSheetsClient().count_deals()
    except Exception as exc:
        st.warning(f"Could not read deals count from Google Sheets: {exc}")

    c1, c2 = st.columns(2)
    c1.metric("Last sync timestamp", str(last_sync))
    c2.metric("Deals in sheet", str(deals_count))


def main() -> None:
    st.set_page_config(page_title="Bitrix24 -> Google Sheets ETL", layout="wide")
    st.title("Bitrix24 CRM Sync")
    st.caption("Manual sync mode: app catches up on updates when button is pressed.")

    render_status_panel()

    ui_handler = UILogHandler()
    ui_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(ui_handler)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Run Incremental Sync", type="primary"):
            with st.spinner("Running incremental sync..."):
                try:
                    result = incremental_sync()
                    st.success("Incremental sync completed")
                    st.json(result)
                except Exception as exc:
                    st.error(f"Incremental sync failed: {exc}")

    with col2:
        if st.button("Run Full Initial Sync"):
            with st.spinner("Running initial full sync..."):
                try:
                    result = initial_full_sync()
                    st.success("Full initial sync completed")
                    st.json(result)
                except Exception as exc:
                    st.error(f"Initial full sync failed: {exc}")

    st.subheader("Logs")
    st.code(ui_handler.get_logs() or "No logs yet.")

    st.subheader("Current state.json")
    st.code(json.dumps(load_state(), ensure_ascii=False, indent=2), language="json")


if __name__ == "__main__":
    main()
