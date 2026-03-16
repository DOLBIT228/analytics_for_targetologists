"""Операції з Google Sheets для аркуша crm_master."""
from __future__ import annotations

import logging
import time
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_INFO,
    GOOGLE_SPREADSHEET_ID,
    GOOGLE_WEB_APP_TOKEN,
    GOOGLE_WEB_APP_URL,
    MASTER_COLUMNS,
    MASTER_SHEET_NAME,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    RETRY_DELAY_SECONDS,
    WEB_APP_APPEND_BATCH_SIZE,
    WEB_APP_APPEND_TIMEOUT,
)

logger = logging.getLogger(__name__)


WEB_APP_ACTION_ALIASES: dict[str, list[str]] = {
    "clear_data": ["clear_all_data", "clear_sheet", "clear", "truncate_data"],
    "load_sheet_data": ["get_sheet_data", "load_data", "list_rows"],
    "count_deals": ["count_rows", "get_count", "count"],
    "update_row": ["update_row_by_number", "update"],
    "delete_rows": ["remove_rows", "delete", "deleteRows", "remove", "delete_row"],
    "append_rows": ["append", "append_data", "insert_rows"],
    "ensure_header": ["init_header", "ensure_columns", "set_header"],
}


class GoogleSheetsClient:
    def __init__(self, spreadsheet_id: str | None = None, credentials_file: str | None = None) -> None:
        self.spreadsheet_id = spreadsheet_id or GOOGLE_SPREADSHEET_ID
        self.credentials_file = credentials_file or GOOGLE_SERVICE_ACCOUNT_FILE
        self.web_app_url = GOOGLE_WEB_APP_URL
        self.web_app_token = GOOGLE_WEB_APP_TOKEN

        if not self.spreadsheet_id:
            raise ValueError("GOOGLE_SPREADSHEET_ID не налаштований")

        self.mode = "web_app" if self.web_app_url else "service_account"

        if self.mode == "service_account":
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            if GOOGLE_SERVICE_ACCOUNT_INFO:
                creds = Credentials.from_service_account_info(GOOGLE_SERVICE_ACCOUNT_INFO, scopes=scopes)
            else:
                creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)

            self.gc = gspread.authorize(creds)
            self.sheet = self.gc.open_by_key(self.spreadsheet_id).worksheet(MASTER_SHEET_NAME)

        self.ensure_header()

    def _web_app_request(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        actions_to_try = [action, *WEB_APP_ACTION_ALIASES.get(action, [])]
        last_data: dict[str, Any] | None = None

        for current_action in actions_to_try:
            body = {
                "action": current_action,
                "token": self.web_app_token,
                "spreadsheet_id": self.spreadsheet_id,
                "sheet_name": MASTER_SHEET_NAME,
                "columns": MASTER_COLUMNS,
                **(payload or {}),
            }
            data = self._web_app_post_with_retries(current_action, body)
            if data.get("ok"):
                if current_action != action:
                    logger.warning("Web App action '%s' is not supported, used fallback '%s'", action, current_action)
                return data

            last_data = data
            if data.get("error") != "unknown_action":
                break

        raise RuntimeError(f"Apps Script Web App error for action '{action}' (tried: {actions_to_try}): {last_data}")

    def _web_app_post_with_retries(self, action: str, body: dict[str, Any]) -> dict[str, Any]:
        """Виконує POST до Apps Script Web App з повторними спробами при тимчасових збоях."""
        last_err: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                timeout = WEB_APP_APPEND_TIMEOUT if action == "append_rows" else REQUEST_TIMEOUT
                response = requests.post(self.web_app_url, json=body, timeout=timeout)
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    raise RuntimeError(
                        f"Apps Script Web App returned non-JSON response for action '{action}': {response.text[:500]}"
                    ) from exc
            except Exception as exc:
                last_err = exc
                logger.warning("Web App request failed for action '%s' (%s/%s): %s", action, attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError(f"Apps Script Web App request failed for action '{action}' after retries: {last_err}")

    def ensure_header(self) -> None:
        if self.mode == "web_app":
            self._web_app_request("ensure_header")
            return

        current_header = self.sheet.row_values(1)
        if current_header != MASTER_COLUMNS:
            self.sheet.update("A1", [MASTER_COLUMNS])

    def load_sheet_data(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Завантажує всі рядки + будує індекс deal_id -> номер рядка."""
        if self.mode == "web_app":
            data = self._web_app_request("load_sheet_data")
            rows = data.get("rows", [])
            index = {str(k): int(v) for k, v in data.get("index", {}).items()}
            return rows, index

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

        if self.mode == "web_app":
            batch_size = max(1, WEB_APP_APPEND_BATCH_SIZE)
            self._append_rows_web_app_in_batches(rows, batch_size)
            return

        values = [[r.get(col, "") for col in MASTER_COLUMNS] for r in rows]
        self.sheet.append_rows(values, value_input_option="USER_ENTERED")

    def _append_rows_web_app_in_batches(self, rows: list[dict[str, Any]], batch_size: int) -> None:
        total_batches = (len(rows) + batch_size - 1) // batch_size
        for batch_number, batch_start in enumerate(range(0, len(rows), batch_size), start=1):
            batch = rows[batch_start : batch_start + batch_size]
            logger.info("Appending rows batch %s/%s (%s rows)", batch_number, total_batches, len(batch))
            self._append_rows_web_app_adaptive(batch)

    def _append_rows_web_app_adaptive(self, rows: list[dict[str, Any]]) -> None:
        """Намагається додати рядки, автоматично зменшуючи батч при timeout помилках."""
        if not rows:
            return

        try:
            self._web_app_request("append_rows", {"rows": rows})
        except RuntimeError as exc:
            err_text = str(exc).lower()
            is_timeout = "timed out" in err_text or "timeout" in err_text
            if not is_timeout or len(rows) == 1:
                raise

            mid = len(rows) // 2
            left = rows[:mid]
            right = rows[mid:]
            logger.warning(
                "append_rows timeout for %s rows; retrying with smaller chunks (%s + %s)",
                len(rows),
                len(left),
                len(right),
            )
            self._append_rows_web_app_adaptive(left)
            self._append_rows_web_app_adaptive(right)

    def update_row_by_deal_id(self, row_number: int, row_data: dict[str, Any]) -> None:
        if self.mode == "web_app":
            self._web_app_request("update_row", {"row_number": row_number, "row_data": row_data})
            return

        values = [row_data.get(col, "") for col in MASTER_COLUMNS]
        start_col = "A"
        end_col = chr(ord("A") + len(MASTER_COLUMNS) - 1)
        self.sheet.update(f"{start_col}{row_number}:{end_col}{row_number}", [values])

    def delete_rows(self, row_numbers: list[int]) -> int:
        """Видаляє рядки за номерами (2..N), повертає кількість видалених."""
        if not row_numbers:
            return 0

        unique_desc = sorted(set(int(r) for r in row_numbers if int(r) >= 2), reverse=True)
        if not unique_desc:
            return 0

        if self.mode == "web_app":
            self._web_app_request("delete_rows", {"row_numbers": unique_desc})
            return len(unique_desc)

        sheet_id = self.sheet.id
        requests_body = [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_num - 1,
                        "endIndex": row_num,
                    }
                }
            }
            for row_num in unique_desc
        ]
        self.sheet.spreadsheet.batch_update({"requests": requests_body})
        return len(unique_desc)

    def clear_all_data(self) -> None:
        """Очищає всі дані окрім заголовка."""
        if self.mode == "web_app":
            self._web_app_request("clear_data")
            return

        last_row = self.sheet.row_count
        if last_row > 1:
            self.sheet.batch_clear([f"A2:{chr(ord('A') + len(MASTER_COLUMNS) - 1)}{last_row}"])

    def count_deals(self) -> int:
        if self.mode == "web_app":
            data = self._web_app_request("count_deals")
            return int(data.get("count", 0))

        records = self.sheet.col_values(1)
        return max(len(records) - 1, 0)
