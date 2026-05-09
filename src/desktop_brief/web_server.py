"""Tiny localhost JSON server so the Chromium briefing can fetch state files.

Runs in a daemon thread so it doesn't block the asyncio event loop.
Binds 127.0.0.1 only — no external exposure.
"""
from __future__ import annotations

import http.server
import logging
import socketserver
import threading
from functools import partial

from desktop_brief.paths import STATE_DIR, ensure_dirs

logger = logging.getLogger(__name__)


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Silence default per-request stderr spam.
        return

    def end_headers(self) -> None:
        # Allow the briefing page (loaded from file://) to fetch from us.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve_in_background(host: str = "127.0.0.1", port: int = 8766) -> threading.Thread:
    ensure_dirs()
    handler_cls = partial(_SilentHandler, directory=str(STATE_DIR))
    httpd = socketserver.ThreadingTCPServer((host, port), handler_cls)
    httpd.daemon_threads = True
    t = threading.Thread(
        target=httpd.serve_forever,
        name=f"state-http-{port}",
        daemon=True,
    )
    t.start()
    logger.info("state http server bound to %s:%d", host, port)
    return t
