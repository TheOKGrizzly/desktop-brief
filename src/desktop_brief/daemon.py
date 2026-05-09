"""asyncio supervisor for all polling sources."""
from __future__ import annotations

import asyncio
import logging
import signal

from desktop_brief.health import registry
from desktop_brief.sources.base import Source

logger = logging.getLogger(__name__)


async def _run_source_loop(src: Source) -> None:
    """Poll forever, with backoff on consecutive failures."""
    registry.register(src.name, src.interval_s)
    try:
        await src.setup()
    except Exception as e:
        logger.exception("setup failed for %s: %s", src.name, e)
        registry.record_failure(src.name, f"setup: {e}")
        return

    while not src.stopped:
        try:
            await src.run_once()
            registry.record_success(src.name)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("%s.run_once failed: %s", src.name, e)
            registry.record_failure(src.name, str(e))

        # Backoff: cap at 5 minutes after consecutive failures.
        wait = src.interval_s
        fails = registry.sources[src.name].consecutive_failures
        if fails > 0:
            wait = min(300, src.interval_s * (2 ** min(fails, 5)))

        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            break

    try:
        await src.teardown()
    except Exception:
        logger.exception("teardown failed for %s", src.name)


class Supervisor:
    """Owns the source list, runs them as concurrent tasks, handles SIGTERM/SIGINT."""

    def __init__(self, sources: list[Source]) -> None:
        self.sources = sources
        self._tasks: list[asyncio.Task] = []
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()
        for s in self.sources:
            s.stop()
        for t in self._tasks:
            t.cancel()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop)

        self._tasks = [asyncio.create_task(_run_source_loop(s), name=s.name) for s in self.sources]
        logger.info("supervisor started with %d sources", len(self.sources))
        await self._stopping.wait()
        logger.info("stopping supervisor")
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("supervisor stopped")
