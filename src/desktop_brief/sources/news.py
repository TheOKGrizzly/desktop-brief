"""News headlines (15-min poll) + daily hot-take synthesis."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from desktop_brief.config import INTERVALS, Config
from desktop_brief.llm.client import LLMCapExceeded, LLMClient
from desktop_brief.llm.prompts import NEWS_HEADLINES_SYSTEM, NEWS_HOTTAKE_SYSTEM
from desktop_brief.sources.base import Source
from desktop_brief.state import read_source, write_source

logger = logging.getLogger(__name__)


class NewsHeadlinesSource(Source):
    name = "news_headlines"

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg
        self._llm = LLMClient(cfg)

    @property
    def interval_s(self) -> int:
        return INTERVALS["news_headlines"]

    async def run_once(self) -> None:
        today = date.today().isoformat()
        user = (
            f"Find today's most important headlines (today is {today}). "
            "Cover: world, US politics, technology, markets, and Oklahoma local if anything notable. "
            "Return JSON per the schema."
        )
        try:
            payload = await self._llm.call_json(
                system_prompt=NEWS_HEADLINES_SYSTEM,
                user_message=user,
                source_label="news_headlines",
                daily_cap=self._cfg.llm_daily_cap_news,
                use_web_search=True,
                max_tokens=2048,
                max_tool_uses=5,
            )
        except LLMCapExceeded as e:
            logger.warning("%s", e)
            return

        headlines: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            for h in payload.get("headlines", []) or []:
                if not isinstance(h, dict):
                    continue
                headlines.append({
                    "title": h.get("title", ""),
                    "source": h.get("source", ""),
                    "url": h.get("url", ""),
                    "published": h.get("published", ""),
                    "category": h.get("category", "world"),
                })

        write_source("news_headlines", {"headlines": headlines})


class NewsHotTakeSource(Source):
    name = "news_hottake"

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg
        self._llm = LLMClient(cfg)

    @property
    def interval_s(self) -> int:
        return INTERVALS["news_hottake"]

    async def run_once(self) -> None:
        # Use the latest headlines as the input.
        headlines_doc = read_source("news_headlines")
        if not headlines_doc:
            logger.info("no headlines yet; skipping hot-take")
            return
        headlines = headlines_doc.get("data", {}).get("headlines", [])
        if not headlines:
            return

        compact = "\n".join(
            f"- [{h.get('category','?')}] {h.get('title','')} ({h.get('source','')})"
            for h in headlines[:18]
        )
        user = f"Today's headlines:\n\n{compact}\n\nWrite the hot-take section."

        try:
            text = await self._llm.call(
                system_prompt=NEWS_HOTTAKE_SYSTEM,
                user_message=user,
                source_label="news_hottake",
                daily_cap=self._cfg.llm_daily_cap_hottake,
                use_web_search=False,
                max_tokens=1500,
            )
        except LLMCapExceeded as e:
            logger.warning("%s", e)
            return

        now = datetime.now(timezone.utc)
        valid_until = now.replace(hour=12, minute=0, second=0, microsecond=0)  # ~next midday UTC ≈ next morning CT
        write_source("news_hottake", {
            "summary_markdown": text,
            "generated_at": now.isoformat(timespec="seconds"),
            "valid_until": valid_until.isoformat(timespec="seconds"),
        })
