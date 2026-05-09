"""notify-send wrapper with in-process dedupe."""
from __future__ import annotations

import asyncio
import logging
import shutil

logger = logging.getLogger(__name__)


_NOTIFY_BIN = shutil.which("notify-send")


async def notify(title: str, body: str = "", urgency: str = "normal", icon: str | None = None) -> None:
    if not _NOTIFY_BIN:
        logger.debug("notify-send not present; would have sent: %s / %s", title, body)
        return
    args = [_NOTIFY_BIN, "-u", urgency, "-a", "desktop-brief"]
    if icon:
        args += ["-i", icon]
    args += [title, body]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
    except Exception:
        logger.exception("notify-send failed")
