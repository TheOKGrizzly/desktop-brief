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
        if self.path == "/chat" or self.path.startswith("/chat?"):
            return self._handle_chat()
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

    def _handle_chat(self) -> None:
        """Proxy a chat turn to Anthropic API. Body: {messages: [...]}.

        Run the async LLMClient.call inside a fresh event loop on this
        request thread (the http.server is threaded, so this is safe).
        """
        try:
            length = int(self.headers.get("Content-Length") or "0")
            body_raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            import json as _json
            body = _json.loads(body_raw or "{}")
            messages = body.get("messages") or []
            if not isinstance(messages, list) or not messages:
                self.send_error(400, "missing 'messages'")
                return

            from desktop_brief.config import load_config
            from desktop_brief.llm.client import LLMClient

            cfg = load_config()
            if not cfg.anthropic_api_key:
                self.send_error(503, "ANTHROPIC_API_KEY not set on the daemon")
                return

            client = LLMClient(cfg)

            # Convert message history to a single user prompt + system, since
            # the existing call() helper takes one user message. For multi-turn
            # we synthesize a transcript-style prompt the model is comfortable
            # with: previous turns as context, latest user message as the ask.
            *prior, last_user = messages
            transcript = "\n\n".join(
                f"[{m.get('role','?').upper()}]\n{m.get('content','')}".strip()
                for m in prior
            )
            user_msg = (
                last_user.get("content", "") if isinstance(last_user, dict) else ""
            )
            if transcript:
                user_msg = f"Conversation so far:\n{transcript}\n\n[USER]\n{user_msg}"

            system_prompt = (
                "You are Claude, a helpful AI assistant embedded in Travis's "
                "desktop-brief Jarvis dashboard. Keep responses concise and "
                "conversational — typically 1-4 sentences unless the question "
                "explicitly asks for detail. The user can pop out a full Claude "
                "Code terminal session via the CLAUDE pill in the footer if they "
                "need file access, code editing, or shell execution."
            )

            import asyncio as _asyncio
            text = _asyncio.run(client.call(
                system_prompt=system_prompt,
                user_message=user_msg,
                source_label="dashboard_chat",
                daily_cap=cfg.llm_daily_cap_news * 2,  # generous cap; chat is bursty
                use_web_search=False,
                max_tokens=1024,
            ))

            payload = _json.dumps({"text": text}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            logger.exception("/chat failed")
            try:
                self.send_error(500, f"chat error: {e}")
            except Exception:
                pass


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
