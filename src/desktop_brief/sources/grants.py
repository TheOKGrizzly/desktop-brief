"""Critical-minerals SBIR / DOE FOA poll (every 6h)."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from desktop_brief.config import INTERVALS, Config
from desktop_brief.llm.client import LLMCapExceeded, LLMClient
from desktop_brief.llm.prompts import GRANTS_SYSTEM
from desktop_brief.sources.base import Source
from desktop_brief.state import write_source

logger = logging.getLogger(__name__)


def _days_until(deadline: str) -> int | None:
    try:
        d = date.fromisoformat(deadline[:10])
    except (ValueError, TypeError):
        return None
    return (d - date.today()).days


class GrantsSource(Source):
    name = "grants"

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg
        self._llm = LLMClient(cfg)

    @property
    def interval_s(self) -> int:
        return INTERVALS["grants"]

    async def run_once(self) -> None:
        today = date.today().isoformat()
        user = (
            f"Today is {today}. Find currently OPEN federal funding opportunities for "
            "critical minerals, rare earth elements, advanced materials processing, "
            "mineral recycling, and geothermal lithium extraction. Return JSON per the schema."
        )
        try:
            payload = await self._llm.call_json(
                system_prompt=GRANTS_SYSTEM,
                user_message=user,
                source_label="grants",
                daily_cap=self._cfg.llm_daily_cap_grants,
                use_web_search=True,
                max_tokens=3000,
                max_tool_uses=8,
            )
        except LLMCapExceeded as e:
            logger.warning("%s", e)
            return

        opps: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            for o in payload.get("opportunities", []) or []:
                if not isinstance(o, dict):
                    continue
                deadline = (o.get("deadline") or "").strip()
                days = _days_until(deadline)
                if days is None or days < 0:
                    # Skip past-deadline or unparseable items.
                    continue
                opps.append({
                    "agency": o.get("agency", ""),
                    "program": o.get("program", ""),
                    "topic": o.get("topic", ""),
                    "topic_number": o.get("topic_number", ""),
                    "deadline": deadline,
                    "days_until_deadline": days,
                    "url": o.get("url", ""),
                    "summary": o.get("summary", ""),
                    "phase": o.get("phase", ""),
                    "max_award_usd": o.get("max_award_usd"),
                })

        opps.sort(key=lambda x: x["days_until_deadline"])
        write_source("grants", {"opportunities": opps})
