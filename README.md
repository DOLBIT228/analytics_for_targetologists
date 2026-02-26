# Bitrix24 → Google Sheets ETL (Streamlit)

Production-oriented ETL service for syncing Bitrix24 deals into Google Sheets for marketing analytics.

## Features

- Full one-time sync by selected pipelines (`initial_full_sync`)
- Incremental sync by `DATE_MODIFY` (`incremental_sync`)
- UTM guard: exports only deals with at least one non-empty UTM field
- Upsert by `deal_id` (no duplicates)
- Updates latest pipeline/stage values when deal moves
- Manual trigger from Streamlit UI (safe for sleeping apps)

## Project structure

- `app.py` — Streamlit user interface
- `etl.py` — sync orchestration and state management
- `bitrix.py` — Bitrix webhook API client with retries and pagination
- `sheets.py` — Google Sheets read/append/update helpers
- `mapping.py` — pipeline and stage mapping dictionaries
- `config.py` — environment and constants
- `state.json` — last sync timestamp storage

## Setup

1. Create and activate Python 3.11 virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set environment variables:
   ```bash
   export BITRIX_WEBHOOK_URL="https://YOUR_DOMAIN.bitrix24.eu/rest/WEBHOOK_ID"
   export GOOGLE_SPREADSHEET_ID="YOUR_SPREADSHEET_ID"
   export GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service_account.json"
   ```
4. Share target spreadsheet with your service account email.
5. Ensure a worksheet named `crm_master` exists (or create it).

## Run Streamlit

```bash
streamlit run app.py
```

Use buttons:
- **Run Full Initial Sync** for initial population
- **Run Incremental Sync** for regular updates and wake-up catch-up

## Required Google Sheet columns

The code enforces this exact order:

`deal_id, pipeline_name, stage_name, date_create, date_modify, amount, utm_source, utm_medium, utm_campaign, utm_content, utm_term`

## Notes

- Stage fallback: if stage code is missing in `STAGE_MAP`, raw `STAGE_ID` is used.
- Initial sync deduplicates `deal_id` before upsert.
- Incremental sync reads `state.json` and updates it after each run.
