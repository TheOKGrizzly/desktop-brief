"""Entry point for `desktop-brief-daemon`."""
from __future__ import annotations

import asyncio
import logging
import sys

from desktop_brief.config import load_config
from desktop_brief.daemon import Supervisor
from desktop_brief.mcp.thunderbird_client import ThunderbirdMCPClient, ThunderbirdMCPError
from desktop_brief.paths import LOG_PATH, ensure_dirs
from desktop_brief.web_server import serve_in_background


def _setup_logging() -> None:
    ensure_dirs()
    fmt = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(LOG_PATH)],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _main_async() -> int:
    log = logging.getLogger("desktop_brief")
    cfg = load_config()

    # Localhost JSON server so the Chromium briefing can fetch state files.
    try:
        serve_in_background()
    except OSError as e:
        log.warning("state http server failed to start: %s (briefing window will not load data)", e)

    # Spawn the shared Thunderbird MCP client (used by email + calendar sources).
    tb_client: ThunderbirdMCPClient | None = ThunderbirdMCPClient(cfg.thunderbird_bridge_path)
    try:
        await tb_client.start()
        log.info("thunderbird-mcp bridge started")
    except (ThunderbirdMCPError, FileNotFoundError, OSError) as e:
        log.warning("thunderbird-mcp unavailable; email + calendar will be degraded: %s", e)
        try:
            await tb_client.stop()
        except Exception:
            pass
        tb_client = None

    # Late imports so a missing optional dep doesn't crash boot.
    from desktop_brief.sources.calendar_source import CalendarSource
    from desktop_brief.sources.email_source import EmailSource
    from desktop_brief.sources.hardware import HardwareSource
    from desktop_brief.sources.stocks import StocksSource
    from desktop_brief.sources.weather import WeatherSource

    sources = [
        WeatherSource(cfg),
        StocksSource(cfg),
        HardwareSource(cfg),
        EmailSource(cfg, tb_client),
        CalendarSource(cfg, tb_client),
    ]

    if cfg.anthropic_api_key:
        from desktop_brief.sources.grants import GrantsSource
        from desktop_brief.sources.news import NewsHeadlinesSource, NewsHotTakeSource

        sources += [NewsHeadlinesSource(cfg), NewsHotTakeSource(cfg), GrantsSource(cfg)]
    else:
        log.warning("ANTHROPIC_API_KEY not set; news + grants sources disabled.")

    sup = Supervisor(sources)
    try:
        await sup.run()
    finally:
        if tb_client is not None:
            try:
                await tb_client.stop()
            except Exception:
                log.exception("thunderbird-mcp shutdown failed")

    return 0


def main() -> int:
    _setup_logging()
    try:
        return asyncio.run(_main_async())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
