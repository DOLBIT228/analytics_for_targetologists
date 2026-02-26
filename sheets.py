"""Google Sheets operations for crm_master sheet."""
from __future__ import annotations

import logging
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SPREADSHEET_ID, MASTER_COLUMNS, MASTER_SHEET_NAME

logger = logging.getLogger(__name__)


class GoogleSheetsClient:
    def __init__(self, spreadsheet_id: str | None = None, credentials_file: str | None = None) -> None:
        self.spreadsheet_id = spreadsheet_id or GOOGLE_SPREADSHEET_ID
        self.credentials_file = credentials_file or GOOGLE_SERVICE_ACCOUNT_FILE
        if not self.spreadsheet_id:
            raise ValueError("GOOGLE_SPREADSHEET_ID is not configured")

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(self.spreadsheet_id).worksheet(MASTER_SHEET_NAME)
        self.ensure_header()

    def ensure_header(self) -> None:
        current_header = self.sheet.row_values(1)
        if current_header != MASTER_COLUMNS:
            self.sheet.update("A1", [MASTER_COLUMNS])

    def load_sheet_data(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Load all rows + build deal_id -> row_number index."""
        rows = self.sheet.get_all_records(expected_headers=MASTER_COLUMNS)
        index: dict[str, int] = {}
        for row_idx, row in enumerate(rows, start=2):
            deal_id = str(row.get("deal_id", "")).strip()
            if deal_id:
                index[deal_id] = row_idx
        return rows, index

    def append_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        values = [[r.get(col, "") for col in MASTER_COLUMNS] for r in rows]
        self.sheet.append_rows(values, value_input_option="USER_ENTERED")

    def update_row_by_deal_id(self, row_number: int, row_data: dict[str, Any]) -> None:
        values = [row_data.get(col, "") for col in MASTER_COLUMNS]
        start_col = "A"
        end_col = chr(ord("A") + len(MASTER_COLUMNS) - 1)
        self.sheet.update(f"{start_col}{row_number}:{end_col}{row_number}", [values])

    def count_deals(self) -> int:
        records = self.sheet.col_values(1)
        return max(len(records) - 1, 0)
