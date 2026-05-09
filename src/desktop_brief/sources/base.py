"""Source ABC: every poller subclasses this."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Source(ABC):
    """A polling source. Subclasses implement run_once() and pick an interval."""

    name: str = "<unset>"

    def __init__(self) -> None:
        self._stopped = False

    @property
    @abstractmethod
    def interval_s(self) -> int:
        """Seconds between successive polls. Source may compute dynamically."""

    @abstractmethod
    async def run_once(self) -> None:
        """Do one poll cycle. Must write its own state JSON on success."""

    async def setup(self) -> None:
        """Optional one-time setup (e.g., spawn a subprocess)."""

    async def teardown(self) -> None:
        """Optional cleanup."""

    def stop(self) -> None:
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return self._stopped
