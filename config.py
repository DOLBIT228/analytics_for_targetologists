"""Конфігурація застосунку для ETL Bitrix24 -> Google Sheets."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import streamlit as st


def _read_streamlit_secret(key: str, default: Any = "") -> Any:
    """Повертає значення з Streamlit secrets за ключем, підтримує вкладені шляхи через крапку."""
    try:
        current: Any = st.secrets
        for part in key.split("."):
            if part not in current:
                return default
            current = current[part]
        return current
    except Exception:
        return default


def read_secret(key: str, env_name: str | None = None, default: Any = "") -> Any:
    """Читає значення спочатку з Streamlit secrets, потім з env (fallback)."""
    value = _read_streamlit_secret(key, None)
    if value not in (None, ""):
        return value
    env_key = env_name or key.upper().replace(".", "_")
    return os.getenv(env_key, default)


def extract_spreadsheet_id(url_or_id: str) -> str:
    """Приймає URL Google Sheets або чистий ID та повертає spreadsheet_id."""
    if not url_or_id:
        return ""
    value = url_or_id.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)
    return value


BITRIX_WEBHOOK_URL = read_secret("bitrix.webhook_url", "BITRIX_WEBHOOK_URL", "")

# Обрані ID воронок/категорій
PIPELINES = [57, 47, 61, 63, 65, 41]

# Налаштування Google Sheets
GOOGLE_SHEETS_URL = read_secret("google.url", "GOOGLE_SHEETS_URL", "")
GOOGLE_SPREADSHEET_ID_RAW = read_secret("google.spreadsheet_id", "GOOGLE_SPREADSHEET_ID", "")
GOOGLE_SPREADSHEET_ID = extract_spreadsheet_id(GOOGLE_SHEETS_URL or GOOGLE_SPREADSHEET_ID_RAW)
GOOGLE_WEB_APP_URL = read_secret("google.web_app_url", "GOOGLE_WEB_APP_URL", "")
GOOGLE_WEB_APP_TOKEN = read_secret("google.web_app_token", "GOOGLE_WEB_APP_TOKEN", "")
GOOGLE_SERVICE_ACCOUNT_FILE = read_secret("google.service_account_file", "GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
GOOGLE_SERVICE_ACCOUNT_INFO_RAW = read_secret("google.service_account_info", "GOOGLE_SERVICE_ACCOUNT_INFO", "")
MASTER_SHEET_NAME = "crm_master"

# service_account_info може бути dict або JSON-рядок
if isinstance(GOOGLE_SERVICE_ACCOUNT_INFO_RAW, dict):
    GOOGLE_SERVICE_ACCOUNT_INFO = GOOGLE_SERVICE_ACCOUNT_INFO_RAW
elif isinstance(GOOGLE_SERVICE_ACCOUNT_INFO_RAW, str) and GOOGLE_SERVICE_ACCOUNT_INFO_RAW.strip():
    try:
        GOOGLE_SERVICE_ACCOUNT_INFO = json.loads(GOOGLE_SERVICE_ACCOUNT_INFO_RAW)
    except json.JSONDecodeError:
        GOOGLE_SERVICE_ACCOUNT_INFO = None
else:
    GOOGLE_SERVICE_ACCOUNT_INFO = None

# Локальний файл стану, в якому зберігається timestamp останньої синхронізації
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))

# Поведінка запитів/повторів
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("RETRY_DELAY_SECONDS", "1.5"))

# Схема вихідних даних (порядок колонок у Google Sheets)
MASTER_COLUMNS = [
    "deal_id",
    "pipeline_name",
    "stage_name",
    "date_create",
    "date_modify",
    "amount",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
]
