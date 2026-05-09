"""Email source: unread last 24h + starred via Thunderbird MCP."""
from __future__ import annotations

import logging
from typing import Any

from desktop_brief.config import INTERVALS, Config
from desktop_brief.mcp.thunderbird_client import ThunderbirdMCPClient, ThunderbirdMCPError
from desktop_brief.sources.base import Source
from desktop_brief.state import write_source

logger = logging.getLogger(__name__)


def _summarize_message(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.get("id") or m.get("messageId"),
        "folder": m.get("folderPath") or m.get("folder"),
        "from": m.get("author") or m.get("from") or "",
        "subject": m.get("subject", ""),
        "date": m.get("date"),
        "preview": (m.get("preview") or "")[:200],
        "account_id": m.get("accountId"),
    }


def _coerce_list(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("messages", []) or []
    return []


def _dedupe(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Thunderbird returns the same message twice when a copy lives in multiple
    folders (e.g. an account Inbox + Local Folders, or the same address received
    on multiple accounts). The MCP `id` is folder-internal — copies of the same
    message get *different* ids — so we dedupe by an (author, subject, date)
    fingerprint instead."""
    seen: set[tuple[str, str, str]] = set()
    out = []
    for m in messages:
        fp = (
            str(m.get("author") or m.get("from") or "").strip().lower(),
            str(m.get("subject") or "").strip().lower(),
            str(m.get("date") or "")[:19],  # truncate to second precision
        )
        if fp in seen:
            continue
        seen.add(fp)
        out.append(m)
    return out


class EmailSource(Source):
    name = "email"

    def __init__(self, cfg: Config, tb_client: ThunderbirdMCPClient | None) -> None:
        super().__init__()
        self._client = tb_client

    @property
    def interval_s(self) -> int:
        return INTERVALS["email"]

    async def run_once(self) -> None:
        if self._client is None:
            write_source("email", {"available": False, "reason": "thunderbird-mcp client not initialized"})
            return

        try:
            unread_raw = await self._client.call_tool(
                "getRecentMessages",
                {"daysBack": 1, "unreadOnly": True, "maxResults": 50},
            )
            starred_raw = await self._client.call_tool(
                "getRecentMessages",
                {"daysBack": 365, "flaggedOnly": True, "maxResults": 30},
            )
        except ThunderbirdMCPError as e:
            logger.warning("email fetch failed: %s", e)
            write_source("email", {"available": False, "reason": str(e)[:300]})
            return

        unread = _dedupe(_coerce_list(unread_raw))
        starred = _dedupe(_coerce_list(starred_raw))

        top_unread = [_summarize_message(m) for m in unread[:20]]
        starred_top = [_summarize_message(m) for m in starred[:20]]

        # Per-account counts: bucket whatever we have on the unread list.
        by_account: dict[str, int] = {}
        for m in unread:
            acct = m.get("accountId") or m.get("folderPath") or "unknown"
            by_account[acct] = by_account.get(acct, 0) + 1

        data = {
            "available": True,
            "unread_24h_count": len(unread),
            "starred_count": len(starred),
            "by_account": [{"account": k, "unread_24h": v} for k, v in sorted(by_account.items(), key=lambda x: -x[1])],
            "top_unread": top_unread,
            "starred": starred_top,
        }
        write_source("email", data)
