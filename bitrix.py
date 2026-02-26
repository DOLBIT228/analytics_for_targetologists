"""Bitrix24 API client for reading CRM deals."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from config import BITRIX_WEBHOOK_URL, MAX_RETRIES, REQUEST_TIMEOUT, RETRY_DELAY_SECONDS

logger = logging.getLogger(__name__)


class BitrixClient:
    """Client wrapper over Bitrix webhook API."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = (webhook_url or BITRIX_WEBHOOK_URL).rstrip("/")
        if not self.webhook_url:
            raise ValueError("BITRIX_WEBHOOK_URL is not configured")

    def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.webhook_url}/{method}.json"
        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    raise RuntimeError(f"Bitrix API error: {data['error']} - {data.get('error_description')}")
                return data
            except Exception as exc:  # network / transient API failures
                last_err = exc
                logger.warning("Bitrix request failed (%s/%s): %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
        raise RuntimeError(f"Bitrix request failed after retries: {last_err}")

    def list_deals(self, *, category_id: int | None = None, date_modify_gt: str | None = None) -> list[dict[str, Any]]:
        """Return all deals with pagination for a given pipeline or modified-after filter."""
        deals: list[dict[str, Any]] = []
        start = 0

        while True:
            flt: dict[str, Any] = {}
            if category_id is not None:
                flt["CATEGORY_ID"] = category_id
            if date_modify_gt:
                flt[">DATE_MODIFY"] = date_modify_gt

            payload = {
                "filter": flt,
                "select": [
                    "ID",
                    "CATEGORY_ID",
                    "STAGE_ID",
                    "DATE_CREATE",
                    "DATE_MODIFY",
                    "OPPORTUNITY",
                    "UTM_SOURCE",
                    "UTM_MEDIUM",
                    "UTM_CAMPAIGN",
                    "UTM_CONTENT",
                    "UTM_TERM",
                ],
                "start": start,
            }

            data = self._request("crm.deal.list", payload)
            page_items = data.get("result", [])
            deals.extend(page_items)

            next_start = data.get("next")
            if next_start is None:
                break
            start = int(next_start)

        return deals
