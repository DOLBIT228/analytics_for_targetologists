"""Core ETL logic: initial and incremental sync."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from bitrix import BitrixClient
from config import PIPELINES, STATE_FILE
from mapping import PIPELINE_MAP, STAGE_MAP
from sheets import GoogleSheetsClient

logger = logging.getLogger(__name__)

UTM_FIELDS = ["UTM_SOURCE", "UTM_MEDIUM", "UTM_CAMPAIGN", "UTM_TERM", "UTM_CONTENT"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def has_any_utm(deal: dict[str, Any]) -> bool:
    return any(str(deal.get(field, "")).strip() for field in UTM_FIELDS)


def _normalize_deal(deal: dict[str, Any]) -> dict[str, Any]:
    category_id = int(deal.get("CATEGORY_ID") or 0)
    stage_id = str(deal.get("STAGE_ID") or "")
    return {
        "deal_id": str(deal.get("ID", "")),
        "pipeline_name": PIPELINE_MAP.get(category_id, str(category_id)),
        "stage_name": STAGE_MAP.get(stage_id, stage_id),
        "date_create": deal.get("DATE_CREATE", ""),
        "date_modify": deal.get("DATE_MODIFY", ""),
        "amount": deal.get("OPPORTUNITY", ""),
        "utm_source": deal.get("UTM_SOURCE", ""),
        "utm_medium": deal.get("UTM_MEDIUM", ""),
        "utm_campaign": deal.get("UTM_CAMPAIGN", ""),
        "utm_content": deal.get("UTM_CONTENT", ""),
        "utm_term": deal.get("UTM_TERM", ""),
    }


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"last_sync_timestamp": None}
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(last_sync_timestamp: str) -> None:
    with STATE_FILE.open("w", encoding="utf-8") as fh:
        json.dump({"last_sync_timestamp": last_sync_timestamp}, fh, ensure_ascii=False, indent=2)


def _upsert_rows(sheet_client: GoogleSheetsClient, normalized_deals: list[dict[str, Any]]) -> dict[str, int]:
    _, index = sheet_client.load_sheet_data()
    to_append: list[dict[str, Any]] = []
    updated = 0

    for row in normalized_deals:
        deal_id = row["deal_id"]
        existing_row_num = index.get(deal_id)
        if existing_row_num:
            sheet_client.update_row_by_deal_id(existing_row_num, row)
            updated += 1
        else:
            to_append.append(row)

    if to_append:
        sheet_client.append_rows(to_append)

    return {"appended": len(to_append), "updated": updated}


def initial_full_sync(
    bitrix_client: BitrixClient | None = None,
    sheet_client: GoogleSheetsClient | None = None,
) -> dict[str, Any]:
    bitrix_client = bitrix_client or BitrixClient()
    sheet_client = sheet_client or GoogleSheetsClient()

    fetched = 0
    filtered = 0
    normalized: list[dict[str, Any]] = []

    for pipeline_id in PIPELINES:
        deals = bitrix_client.list_deals(category_id=pipeline_id)
        fetched += len(deals)
        for deal in deals:
            if has_any_utm(deal):
                filtered += 1
                normalized.append(_normalize_deal(deal))

    # Deduplicate input by deal_id with latest observed row (last write wins).
    dedup: dict[str, dict[str, Any]] = {row["deal_id"]: row for row in normalized if row.get("deal_id")}
    upsert_stats = _upsert_rows(sheet_client, list(dedup.values()))
    save_state(now_iso())

    result = {
        "mode": "initial_full_sync",
        "fetched": fetched,
        "matched_utm": filtered,
        "unique_deals": len(dedup),
        **upsert_stats,
        "last_sync_timestamp": load_state().get("last_sync_timestamp"),
    }
    logger.info("Initial sync completed: %s", result)
    return result


def incremental_sync(
    bitrix_client: BitrixClient | None = None,
    sheet_client: GoogleSheetsClient | None = None,
) -> dict[str, Any]:
    bitrix_client = bitrix_client or BitrixClient()
    sheet_client = sheet_client or GoogleSheetsClient()

    state = load_state()
    last_sync = state.get("last_sync_timestamp")

    deals = bitrix_client.list_deals(date_modify_gt=last_sync) if last_sync else []
    fetched = len(deals)

    normalized = [_normalize_deal(d) for d in deals if has_any_utm(d)]
    dedup: dict[str, dict[str, Any]] = {row["deal_id"]: row for row in normalized if row.get("deal_id")}
    upsert_stats = _upsert_rows(sheet_client, list(dedup.values())) if dedup else {"appended": 0, "updated": 0}

    save_state(now_iso())
    result = {
        "mode": "incremental_sync",
        "from_timestamp": last_sync,
        "fetched": fetched,
        "matched_utm": len(normalized),
        "unique_deals": len(dedup),
        **upsert_stats,
        "last_sync_timestamp": load_state().get("last_sync_timestamp"),
    }
    logger.info("Incremental sync completed: %s", result)
    return result
