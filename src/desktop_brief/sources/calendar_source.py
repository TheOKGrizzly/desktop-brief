"""Calendar source: today + tomorrow events with 15-min reminder dedup."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from desktop_brief.config import INTERVALS, Config
from desktop_brief.mcp.thunderbird_client import ThunderbirdMCPClient, ThunderbirdMCPError
from desktop_brief.notify import notify
from desktop_brief.paths import CALENDAR_FIRED_PATH
from desktop_brief.sources.base import Source
from desktop_brief.state import atomic_write_json, write_source

logger = logging.getLogger(__name__)

_REMINDER_LEAD_MIN = 15
_FIRED_RETENTION_HOURS = 24


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Handle 'Z' suffix as UTC.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _summarize_event(e: dict[str, Any]) -> dict[str, Any]:
    start = e.get("startDate") or e.get("start") or e.get("startISO")
    end = e.get("endDate") or e.get("end") or e.get("endISO")
    return {
        "id": e.get("id") or e.get("eventId"),
        "calendar_id": e.get("calendarId") or e.get("calendar"),
        "calendar": e.get("calendarName") or e.get("calendar"),
        "title": e.get("title") or e.get("summary") or "(no title)",
        "start": start,
        "end": end,
        "location": e.get("location"),
        "description": (e.get("description") or "")[:500],
        "all_day": bool(e.get("allDay")),
        "status": e.get("status"),
    }


def _coerce_events(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("events", []) or []
    return []


class CalendarSource(Source):
    name = "calendar"

    def __init__(self, cfg: Config, tb_client: ThunderbirdMCPClient | None) -> None:
        super().__init__()
        self._client = tb_client
        self._tz = ZoneInfo(cfg.timezone_local)
        self._fired = self._load_fired()

    @property
    def interval_s(self) -> int:
        return INTERVALS["calendar"]

    # ---- reminder dedup state ---------------------------------------------

    def _load_fired(self) -> dict[str, str]:
        try:
            with open(CALENDAR_FIRED_PATH, encoding="utf-8") as f:
                doc = json.load(f)
                return doc.get("data", {}).get("fired", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _persist_fired(self) -> None:
        atomic_write_json(
            CALENDAR_FIRED_PATH,
            {
                "schema_version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": "calendar_fired",
                "data": {"fired": self._fired},
            },
        )

    def _prune_fired(self, now_utc: datetime) -> None:
        cutoff = now_utc - timedelta(hours=_FIRED_RETENTION_HOURS)
        keep = {}
        for eid, fired_at in self._fired.items():
            ts = _parse_iso(fired_at)
            if ts and ts >= cutoff:
                keep[eid] = fired_at
        if len(keep) != len(self._fired):
            self._fired = keep
            self._persist_fired()

    # ---- main poll --------------------------------------------------------

    async def run_once(self) -> None:
        if self._client is None:
            write_source("calendar", {"available": False, "reason": "thunderbird-mcp client not initialized"})
            return

        now_local = datetime.now(self._tz)
        start = now_local
        end = (now_local + timedelta(days=2)).replace(hour=23, minute=59, second=59)

        try:
            raw = await self._client.call_tool(
                "listEvents",
                {
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "maxResults": 200,
                },
            )
        except ThunderbirdMCPError as e:
            logger.warning("calendar fetch failed: %s", e)
            write_source("calendar", {"available": False, "reason": str(e)[:300]})
            return

        events = [_summarize_event(e) for e in _coerce_events(raw)]
        events.sort(key=lambda e: e["start"] or "")

        today_iso = now_local.date().isoformat()
        tomorrow_iso = (now_local + timedelta(days=1)).date().isoformat()
        today, tomorrow = [], []
        for ev in events:
            d = (ev["start"] or "")[:10]
            if d == today_iso:
                today.append(ev)
            elif d == tomorrow_iso:
                tomorrow.append(ev)

        # Next event = the next start >= now_local, today or tomorrow.
        next_event = None
        minutes_until_next: int | None = None
        for ev in today + tomorrow:
            ts = _parse_iso(ev["start"])
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=self._tz)
            delta = ts - now_local
            if delta.total_seconds() >= -300:  # include things just starting
                next_event = ev
                minutes_until_next = max(0, int(delta.total_seconds() // 60))
                break

        # Fire 15-minute reminders.
        await self._fire_reminders(today + tomorrow, now_local)

        data = {
            "available": True,
            "today": today,
            "tomorrow": tomorrow,
            "next_event": next_event,
            "minutes_until_next": minutes_until_next,
        }
        write_source("calendar", data)

    async def _fire_reminders(self, upcoming: list[dict], now_local: datetime) -> None:
        self._prune_fired(now_local.astimezone(timezone.utc))
        for ev in upcoming:
            ts = _parse_iso(ev["start"])
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=self._tz)
            delta_min = (ts - now_local).total_seconds() / 60
            if 0 <= delta_min <= _REMINDER_LEAD_MIN and ev["id"] not in self._fired:
                title = f"⏰ Starting in {int(round(delta_min))} min"
                body = ev["title"]
                if ev.get("location"):
                    body += f"\n📍 {ev['location']}"
                await notify(title, body, urgency="critical", icon="appointment-soon")
                self._fired[ev["id"]] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self._persist_fired()
