"""Market-state classification (regular/pre/post/closed)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from desktop_brief.sources.stocks import _market_state

ET = ZoneInfo("America/New_York")


def test_regular_session_weekday():
    # Wednesday 11:00 ET is regular.
    assert _market_state(datetime(2026, 5, 13, 11, 0, tzinfo=ET)) == "REGULAR"


def test_pre_market():
    # Wednesday 06:00 ET is pre.
    assert _market_state(datetime(2026, 5, 13, 6, 0, tzinfo=ET)) == "PRE"


def test_post_market():
    # Wednesday 17:00 ET is post.
    assert _market_state(datetime(2026, 5, 13, 17, 0, tzinfo=ET)) == "POST"


def test_closed_before_pre():
    assert _market_state(datetime(2026, 5, 13, 3, 30, tzinfo=ET)) == "CLOSED"


def test_closed_after_post():
    assert _market_state(datetime(2026, 5, 13, 21, 0, tzinfo=ET)) == "CLOSED"


def test_weekend_closed():
    # Saturday afternoon.
    assert _market_state(datetime(2026, 5, 16, 14, 0, tzinfo=ET)) == "CLOSED"
    # Sunday morning.
    assert _market_state(datetime(2026, 5, 17, 10, 0, tzinfo=ET)) == "CLOSED"
