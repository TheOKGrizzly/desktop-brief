"""Stocks via Stooq CSV API (free, no auth, less aggressive rate limiting than Yahoo).

For each symbol we fetch:
- The live one-line CSV (latest price, today's open/high/low).
- A short daily history CSV to recover the previous trading-day close so we can
  compute change vs prev-close (the standard "% change" most people expect).

Stooq symbol mapping:
- ^DJI  -> ^DJI   (Dow Jones Industrial Average)
- ^IXIC -> ^NDQ   (Nasdaq Composite)
- ^GSPC -> ^SPX   (S&P 500)
- All US equities: append `.us` suffix.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from desktop_brief.config import INTERVALS, Config
from desktop_brief.sources.base import Source
from desktop_brief.state import write_source

logger = logging.getLogger(__name__)


_INDEX_LABELS = {
    "^DJI": "Dow",
    "^IXIC": "Nasdaq",
    "^GSPC": "S&P 500",
}

_YAHOO_TO_STOOQ_INDEX = {
    "^DJI": "^DJI",
    "^IXIC": "^NDQ",
    "^GSPC": "^SPX",
}

_CONCURRENCY = 6
_LIVE_URL = "https://stooq.com/q/l/?s={s}&f=sd2t2ohlcvn&h&e=csv"
_HIST_URL = "https://stooq.com/q/d/l/?s={s}&i=d&d1={d1}&d2={d2}"


def _stooq_symbol(yahoo_sym: str) -> str:
    if yahoo_sym in _YAHOO_TO_STOOQ_INDEX:
        return _YAHOO_TO_STOOQ_INDEX[yahoo_sym]
    if yahoo_sym.startswith("^"):
        return yahoo_sym
    return f"{yahoo_sym.lower()}.us"


def _market_state(now_et: datetime) -> str:
    if now_et.weekday() >= 5:
        return "CLOSED"
    t = now_et.time()
    if time(4, 0) <= t < time(9, 30):
        return "PRE"
    if time(9, 30) <= t < time(16, 0):
        return "REGULAR"
    if time(16, 0) <= t < time(20, 0):
        return "POST"
    return "CLOSED"


def _parse_live_csv(text: str) -> dict | None:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return None
    header, row = rows[0], rows[1]
    rec = dict(zip(header, row))
    try:
        close = float(rec.get("Close", "N/D"))
    except (ValueError, TypeError):
        return None
    if not close:
        return None

    def _maybe(field: str) -> float | None:
        v = rec.get(field, "N/D")
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    return {
        "name": rec.get("Name", "").strip(),
        "price": close,
        "open": _maybe("Open"),
        "day_high": _maybe("High"),
        "day_low": _maybe("Low"),
        "volume": _maybe("Volume"),
    }


def _parse_prev_close_from_history(text: str) -> float | None:
    """Stooq daily history is sorted ascending; the prev-trading-day close is the
    second-to-last row when the latest row is today, or the last row if today
    isn't included yet (markets still open / pre-market)."""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        return None
    data_rows = rows[1:]  # skip header
    # Try second-to-last first; fall back to last.
    for idx in (-2, -1):
        if abs(idx) > len(data_rows):
            continue
        try:
            return float(data_rows[idx][4])
        except (ValueError, IndexError, TypeError):
            continue
    return None


async def _fetch_one(client: httpx.AsyncClient, yahoo_sym: str) -> dict | None:
    sym = _stooq_symbol(yahoo_sym)
    today = datetime.now(timezone.utc).date()
    d1 = (today - timedelta(days=10)).strftime("%Y%m%d")
    d2 = today.strftime("%Y%m%d")

    try:
        live_resp, hist_resp = await asyncio.gather(
            client.get(_LIVE_URL.format(s=sym)),
            client.get(_HIST_URL.format(s=sym, d1=d1, d2=d2)),
        )
    except Exception as e:
        logger.debug("stooq fetch %s failed: %s", sym, e)
        return None

    if live_resp.status_code != 200:
        return None
    live = _parse_live_csv(live_resp.text)
    if not live:
        return None

    prev_close = None
    if hist_resp.status_code == 200:
        prev_close = _parse_prev_close_from_history(hist_resp.text)

    price = live["price"]
    if prev_close is not None and prev_close > 0:
        change = price - prev_close
        change_pct = change / prev_close * 100
    elif live.get("open"):
        # Fallback: intraday change vs today's open.
        change = price - live["open"]
        change_pct = change / live["open"] * 100
    else:
        change = None
        change_pct = None

    return {
        "symbol": yahoo_sym,
        "name": _INDEX_LABELS.get(yahoo_sym) or live["name"] or yahoo_sym,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "currency": "USD",
        "day_high": live.get("day_high"),
        "day_low": live.get("day_low"),
    }


class StocksSource(Source):
    name = "stocks"

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._symbols = cfg.all_symbols
        self._index_set = set(cfg.index_symbols)
        self._tz_market = ZoneInfo(cfg.timezone_market)
        self._client: httpx.AsyncClient | None = None

    @property
    def interval_s(self) -> int:
        now_et = datetime.now(self._tz_market)
        if _market_state(now_et) == "REGULAR":
            return INTERVALS["stocks_market_hours"]
        return INTERVALS["stocks_off_hours"]

    async def setup(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "desktop-brief/0.1"},
            follow_redirects=True,
        )

    async def teardown(self) -> None:
        if self._client:
            await self._client.aclose()

    async def run_once(self) -> None:
        assert self._client is not None
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def bounded(sym: str) -> dict | None:
            async with sem:
                return await _fetch_one(self._client, sym)

        rows = await asyncio.gather(*[bounded(s) for s in self._symbols])

        indices: list[dict] = []
        watchlist: list[dict] = []
        for row in rows:
            if not row:
                continue
            (indices if row["symbol"] in self._index_set else watchlist).append(row)

        now_et = datetime.now(self._tz_market)
        data = {
            "market_state": _market_state(now_et),
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "indices": indices,
            "watchlist": watchlist,
            "fetched_count": sum(1 for r in rows if r),
            "requested_count": len(self._symbols),
            "data_source": "stooq.com",
        }
        write_source("stocks", data)
