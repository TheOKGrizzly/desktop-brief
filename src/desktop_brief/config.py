"""Configuration: env vars, ticker list, source intervals."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    """Load .env from the repo root if present, then from the user's home."""
    repo_env = REPO_ROOT / ".env"
    if repo_env.exists():
        load_dotenv(repo_env)
    home_env = Path.home() / ".config" / "desktop-brief" / ".env"
    if home_env.exists():
        load_dotenv(home_env, override=False)


_load_env()


# Tickers to track. Indices first; everything else is "watchlist."
INDEX_SYMBOLS = ["^DJI", "^IXIC", "^GSPC"]
WATCHLIST_SYMBOLS = [
    # tech / mega
    "TSLA", "NVDA", "AAPL", "MSFT", "GOOGL", "META",
    # robotics / autonomy
    "ABB", "ISRG", "IRBT",
    # space / rockets
    "RKLB", "ASTS", "LMT", "BA",
    # critical minerals / REE
    "MP", "LAC", "ALB", "UUUU", "USAR",
]
ALL_TICKERS = INDEX_SYMBOLS + WATCHLIST_SYMBOLS


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None
    claude_model: str
    thunderbird_bridge_path: Path
    weather_query: str
    timezone_local: str
    timezone_market: str
    llm_daily_cap_news: int
    llm_daily_cap_grants: int
    llm_daily_cap_hottake: int
    index_symbols: list[str] = field(default_factory=lambda: list(INDEX_SYMBOLS))
    watchlist_symbols: list[str] = field(default_factory=lambda: list(WATCHLIST_SYMBOLS))

    @property
    def all_symbols(self) -> list[str]:
        return self.index_symbols + self.watchlist_symbols


def load_config() -> Config:
    bridge = os.environ.get(
        "THUNDERBIRD_MCP_BRIDGE",
        str(Path.home() / "projects" / "thunderbird-mcp" / "mcp-bridge.cjs"),
    )
    return Config(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        thunderbird_bridge_path=Path(bridge),
        weather_query=os.environ.get("WEATHER_QUERY", "Norman,OK"),
        timezone_local=os.environ.get("TZ_LOCAL", "America/Chicago"),
        timezone_market=os.environ.get("TZ_MARKET", "America/New_York"),
        llm_daily_cap_news=int(os.environ.get("LLM_DAILY_CALL_CAP_NEWS", "120")),
        llm_daily_cap_grants=int(os.environ.get("LLM_DAILY_CALL_CAP_GRANTS", "8")),
        llm_daily_cap_hottake=int(os.environ.get("LLM_DAILY_CALL_CAP_HOTTAKE", "3")),
    )


# Source poll intervals (seconds). Source-specific overrides may apply.
INTERVALS = {
    "email": 60,
    "calendar": 60,
    "weather": 1800,           # 30 min
    "stocks_market_hours": 60,
    "stocks_off_hours": 900,   # 15 min
    "news_headlines": 900,     # 15 min
    "news_hottake": 86400,     # daily
    "grants": 21600,           # 6 h
    "hardware": 2,
}

SCHEMA_VERSION = 1
