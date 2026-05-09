"""Tiny localhost JSON server so the Chromium briefing can fetch state files.

Runs in a daemon thread so it doesn't block the asyncio event loop.
Binds 127.0.0.1 only — no external exposure.

Also exposes a small POST /launch/<app> endpoint used by the dashboard's
Claude pill (and any future quick-launch buttons) — allowed apps are an
explicit allowlist; arbitrary commands are not accepted.
"""
from __future__ import annotations

import http.server
import logging
import shlex
import shutil
import socketserver
import subprocess
import threading
from functools import partial

from desktop_brief.paths import STATE_DIR, ensure_dirs

logger = logging.getLogger(__name__)


# Allowlist of dashboard quick-launch shortcuts. Each value is a shell argv
# (no shell interpolation). Add entries here, never accept user input.
_LAUNCH_TARGETS: dict[str, list[str]] = {
    "claude": _claude_argv() if False else [],  # placeholder, set below
}


def _terminal_argv(inner_cmd: list[str]) -> list[str]:
    """Pick whichever terminal emulator is available and wrap inner_cmd."""
    for term, prefix in [
        ("gnome-terminal", ["--", *inner_cmd]),
        ("ghostty", ["-e", *inner_cmd]),
        ("kitty", [*inner_cmd]),
        ("alacritty", ["-e", *inner_cmd]),
        ("xterm", ["-e", *inner_cmd]),
    ]:
        if shutil.which(term):
            return [term, *prefix]
    return []


def _claude_argv() -> list[str]:
    if not shutil.which("claude"):
        return []
    return _terminal_argv(["claude"])


_LAUNCH_TARGETS["claude"] = _claude_argv()


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Silence default per-request stderr spam.
        return

    def end_headers(self) -> None:
        # Allow the briefing page (loaded from file://) to fetch from us.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802 — http.server convention
        # Preflight for the launch POST.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        # Only paths under /launch/<allowlisted-name> are honored.
        if not self.path.startswith("/launch/"):
            self.send_error(404)
            return
        name = self.path[len("/launch/"):].strip("/").split("?")[0]
        argv = _LAUNCH_TARGETS.get(name) or []
        if not argv:
            self.send_error(404, f"unknown launch target: {name}")
            return
        try:
            subprocess.Popen(  # noqa: S603 — argv from explicit allowlist, no shell
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            logger.info("launched %s: %s", name, shlex.join(argv))
        except Exception as e:
            logger.exception("launch %s failed", name)
            self.send_error(500, f"launch failed: {e}")


class _ReuseAddrServer(socketserver.ThreadingTCPServer):
    """Set SO_REUSEADDR so a quick systemd restart doesn't TIME_WAIT-block us."""
    allow_reuse_address = True


def serve_in_background(host: str = "127.0.0.1", port: int = 8766) -> threading.Thread:
    ensure_dirs()
    handler_cls = partial(_SilentHandler, directory=str(STATE_DIR))
    httpd = _ReuseAddrServer((host, port), handler_cls)
    httpd.daemon_threads = True
    t = threading.Thread(
        target=httpd.serve_forever,
        name=f"state-http-{port}",
        daemon=True,
    )
    t.start()
    logger.info("state http server bound to %s:%d", host, port)
    return t
