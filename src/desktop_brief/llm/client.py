"""Anthropic client wrapper with prompt caching, daily caps, and JSON-mode helpers."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from anthropic import AsyncAnthropic

from desktop_brief.config import Config
from desktop_brief.paths import LLM_USAGE_PATH
from desktop_brief.state import atomic_write_json

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMCapExceeded(RuntimeError):
    pass


def _read_usage() -> dict[str, dict[str, int]]:
    try:
        with open(LLM_USAGE_PATH, encoding="utf-8") as f:
            return json.load(f).get("data", {}).get("usage", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_usage(usage: dict[str, dict[str, int]]) -> None:
    atomic_write_json(
        LLM_USAGE_PATH,
        {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "llm_usage",
            "data": {"usage": usage},
        },
    )


def _today_key() -> str:
    return date.today().isoformat()


def increment_usage(source_label: str) -> int:
    """Bump today's call count for a source; return new count."""
    usage = _read_usage()
    today = _today_key()
    bucket = usage.setdefault(today, {})
    bucket[source_label] = bucket.get(source_label, 0) + 1
    # Prune anything older than 14 days.
    keep = {k: v for k, v in usage.items() if k >= (datetime.now().date().isoformat()[:8] + "01")}
    keep[today] = bucket
    _write_usage(keep)
    return bucket[source_label]


def usage_today(source_label: str) -> int:
    return _read_usage().get(_today_key(), {}).get(source_label, 0)


def _parse_json_from_text(text: str) -> Any:
    """Be forgiving: strip code fences if present."""
    text = text.strip()
    m = _JSON_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


class LLMClient:
    """Thin wrapper around AsyncAnthropic with prompt caching + JSON parsing."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        if not cfg.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self._client = AsyncAnthropic(api_key=cfg.anthropic_api_key)

    async def call(
        self,
        *,
        system_prompt: str,
        user_message: str,
        source_label: str,
        daily_cap: int,
        use_web_search: bool = False,
        max_tokens: int = 2048,
        max_tool_uses: int = 5,
    ) -> str:
        """Run one Claude call. Enforces daily cap. Returns the assistant text."""
        if usage_today(source_label) >= daily_cap:
            raise LLMCapExceeded(f"daily cap of {daily_cap} reached for {source_label}")

        kwargs: dict[str, Any] = {
            "model": self._cfg.claude_model,
            "max_tokens": max_tokens,
            "system": [
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": user_message}],
        }
        if use_web_search:
            kwargs["tools"] = [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": max_tool_uses}
            ]

        resp = await self._client.messages.create(**kwargs)
        increment_usage(source_label)

        # Concatenate all final text blocks (skip tool_use / server_tool_use blocks).
        chunks: list[str] = []
        for block in resp.content:
            t = getattr(block, "type", None)
            if t == "text":
                chunks.append(getattr(block, "text", ""))
        return "\n".join(chunks).strip()

    async def call_json(
        self,
        *,
        system_prompt: str,
        user_message: str,
        source_label: str,
        daily_cap: int,
        use_web_search: bool = False,
        max_tokens: int = 2048,
        max_tool_uses: int = 5,
    ) -> Any:
        text = await self.call(
            system_prompt=system_prompt,
            user_message=user_message,
            source_label=source_label,
            daily_cap=daily_cap,
            use_web_search=use_web_search,
            max_tokens=max_tokens,
            max_tool_uses=max_tool_uses,
        )
        try:
            return _parse_json_from_text(text)
        except json.JSONDecodeError as e:
            logger.warning("LLM JSON parse failed for %s: %s; raw=%r", source_label, e, text[:300])
            raise
