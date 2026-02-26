"""Application configuration for Bitrix24 -> Google Sheets ETL."""
from __future__ import annotations

import os
from pathlib import Path

BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL", "")

# Selected pipeline/category IDs
PIPELINES = [57, 47, 61, 63, 65, 41]

# Google Sheets settings
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")
MASTER_SHEET_NAME = "crm_master"

# Local state file that stores last incremental sync timestamp
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))

# Request / retry behavior
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("RETRY_DELAY_SECONDS", "1.5"))

# Output schema (column order in Google Sheets)
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
