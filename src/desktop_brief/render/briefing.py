"""Render the state JSON files as a one-screen markdown briefing."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from desktop_brief.config import load_config
from desktop_brief.state import read_source


def _local_now(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def _staleness_str(generated_at: str | None, now_utc: datetime) -> str:
    if not generated_at:
        return "no data"
    try:
        ts = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return "no data"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (now_utc - ts).total_seconds()
    if age < 90:
        return "live"
    if age < 3600:
        return f"{int(age / 60)}m old"
    if age < 86400:
        return f"{int(age / 3600)}h old"
    return "stale"


def _section_email(doc: dict[str, Any] | None) -> list[str]:
    out = ["## Inbox"]
    if not doc or not doc.get("data", {}).get("available", True):
        reason = doc.get("data", {}).get("reason", "unavailable") if doc else "no data"
        out.append(f"_unavailable: {reason}_")
        return out
    d = doc["data"]
    out.append(f"**{d.get('unread_24h_count', 0)} unread (24h)** · {d.get('starred_count', 0)} starred")
    for m in (d.get("top_unread") or [])[:6]:
        sender = (m.get("from") or "").split("<")[0].strip() or "(unknown)"
        out.append(f"- **{sender[:30]}** — {m.get('subject', '(no subject)')[:80]}")
    return out


def _section_calendar(doc: dict[str, Any] | None, tz: str) -> list[str]:
    out = ["## Calendar"]
    if not doc or not doc.get("data", {}).get("available", True):
        reason = doc.get("data", {}).get("reason", "unavailable") if doc else "no data"
        out.append(f"_unavailable: {reason}_")
        return out
    d = doc["data"]
    nxt = d.get("next_event")
    if nxt:
        mins = d.get("minutes_until_next")
        when = ""
        if mins is not None:
            if mins < 60:
                when = f" (in {mins}m)"
            else:
                when = f" (in {mins // 60}h {mins % 60}m)"
        out.append(f"**Next:** {nxt.get('title', '?')}{when}")
    today = d.get("today") or []
    if today:
        out.append(f"_Today_ ({len(today)}):")
        for ev in today[:5]:
            t = (ev.get("start") or "")[11:16]
            out.append(f"- {t} {ev.get('title', '?')}")
    if d.get("tomorrow"):
        out.append(f"_Tomorrow:_ {len(d['tomorrow'])} events")
    return out


def _section_weather(doc: dict[str, Any] | None) -> list[str]:
    out = ["## Weather"]
    if not doc:
        out.append("_no data_")
        return out
    d = doc["data"]
    cur = d.get("current", {})
    today = d.get("today", {})
    icon = cur.get("icon", "")
    out.append(
        f"{icon} **{cur.get('temp_f','?')}°F** {cur.get('condition','')} · "
        f"hi {today.get('high_f','?')} / lo {today.get('low_f','?')} · "
        f"{today.get('precip_chance', 0)}% precip"
    )
    return out


def _section_stocks(doc: dict[str, Any] | None) -> list[str]:
    out = ["## Markets"]
    if not doc:
        out.append("_no data_")
        return out
    d = doc["data"]
    state = d.get("market_state", "?")
    out.append(f"_{state}_")

    def _row(q: dict[str, Any]) -> str:
        sym = q.get("symbol", "?")
        pct = q.get("change_pct")
        if pct is None:
            return f"`{sym}` n/a"
        arrow = "▲" if pct >= 0 else "▼"
        return f"`{sym:<6}` {arrow} {pct:+.2f}%"

    indices = d.get("indices") or []
    if indices:
        out.append(" · ".join(_row(i) for i in indices))
    watch = d.get("watchlist") or []
    if watch:
        # show top 6 movers (abs change_pct)
        movers = sorted(watch, key=lambda x: -abs((x.get("change_pct") or 0)))[:6]
        out.append(" · ".join(_row(i) for i in movers))
    return out


def _section_hardware(doc: dict[str, Any] | None) -> list[str]:
    out = ["## System"]
    if not doc:
        out.append("_no data_")
        return out
    d = doc["data"]
    cpu = d.get("cpu", {})
    mem = d.get("memory", {})
    disk = d.get("disk", {})
    bits = [
        f"CPU {cpu.get('overall_pct', '?')}%",
        f"RAM {mem.get('pct', '?')}% ({mem.get('used_gb', '?')}/{mem.get('total_gb', '?')} GB)",
        f"Disk {disk.get('pct', '?')}%",
    ]
    if cpu.get("temp_c") is not None:
        bits.append(f"{cpu['temp_c']}°C")
    if d.get("gpu"):
        g = d["gpu"][0]
        bits.append(f"GPU {g.get('util_pct', '?')}%")
    out.append(" · ".join(bits))
    return out


def _section_news(headlines_doc: dict | None, hottake_doc: dict | None) -> list[str]:
    out = ["## News"]
    if hottake_doc:
        out.append(hottake_doc["data"].get("summary_markdown", "").strip())
    elif headlines_doc:
        h = (headlines_doc.get("data", {}).get("headlines") or [])[:5]
        for item in h:
            out.append(f"- [{item.get('category','?')}] {item.get('title','?')} — {item.get('source','?')}")
    else:
        out.append("_no data_")
    return out


def _section_grants(doc: dict[str, Any] | None) -> list[str]:
    out = ["## Open Grants"]
    if not doc:
        out.append("_no data_")
        return out
    opps = doc["data"].get("opportunities") or []
    if not opps:
        out.append("_none currently open_")
        return out
    for o in opps[:5]:
        out.append(
            f"- **{o.get('agency', '?')} · {o.get('topic', '?')}** "
            f"— due {o.get('deadline', '?')} ({o.get('days_until_deadline', '?')}d)"
        )
    return out


def render_markdown() -> str:
    cfg = load_config()
    now_local = _local_now(cfg.timezone_local)
    now_utc = datetime.now(timezone.utc)
    header = f"# Brief — {now_local.strftime('%a %Y-%m-%d %H:%M %Z')}"

    docs = {name: read_source(name) for name in [
        "email", "calendar", "weather", "stocks", "hardware",
        "news_headlines", "news_hottake", "grants",
    ]}

    parts: list[str] = [header, ""]
    parts += _section_email(docs["email"]); parts.append("")
    parts += _section_calendar(docs["calendar"], cfg.timezone_local); parts.append("")
    parts += _section_weather(docs["weather"]); parts.append("")
    parts += _section_stocks(docs["stocks"]); parts.append("")
    parts += _section_hardware(docs["hardware"]); parts.append("")
    parts += _section_news(docs["news_headlines"], docs["news_hottake"]); parts.append("")
    parts += _section_grants(docs["grants"]); parts.append("")

    # Health line at the bottom: source ages.
    ages = ", ".join(
        f"{n}={_staleness_str((docs.get(n) or {}).get('generated_at'), now_utc)}"
        for n in ["email", "calendar", "weather", "stocks", "hardware", "news_headlines", "grants"]
    )
    parts.append(f"_health: {ages}_")

    return "\n".join(parts).rstrip() + "\n"
