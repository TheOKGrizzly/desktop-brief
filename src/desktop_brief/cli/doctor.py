"""Health-check CLI: `dbrief-doctor`."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from desktop_brief.config import load_config
from desktop_brief.paths import HEALTH_PATH, STATE_DIR, ensure_dirs

GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
DIM = "\033[2m"
RESET = "\033[0m"

_FAILURES = 0
_WARNINGS = 0


def _ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def _warn(msg: str) -> None:
    global _WARNINGS
    _WARNINGS += 1
    print(f"  {YELLOW}!{RESET} {msg}")


def _fail(msg: str) -> None:
    global _FAILURES
    _FAILURES += 1
    print(f"  {RED}✗{RESET} {msg}")


def _section(title: str) -> None:
    print(f"\n{DIM}── {title} ──{RESET}")


def _check_session() -> None:
    _section("Session")
    sess = os.environ.get("XDG_SESSION_TYPE", "(unset)")
    if sess == "x11":
        _ok(f"XDG_SESSION_TYPE={sess}")
    else:
        _warn(f"XDG_SESSION_TYPE={sess} — eww overlay needs X11 on GNOME (log out, pick 'Ubuntu on Xorg')")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "(unset)")
    _ok(f"XDG_CURRENT_DESKTOP={desktop}")


def _check_binaries() -> None:
    _section("Binaries")
    for binname, hard in [("python3", True), ("node", True), ("jq", True),
                          ("notify-send", True), ("eww", False), ("git", False),
                          ("chromium", False), ("chromium-browser", False),
                          ("google-chrome", False), ("firefox", False),
                          ("nvidia-smi", False), ("gsettings", False)]:
        path = shutil.which(binname)
        if path:
            _ok(f"{binname}: {path}")
        elif hard:
            _fail(f"{binname}: NOT FOUND (required)")
        else:
            _warn(f"{binname}: not found (optional)")


def _check_paths() -> None:
    _section("Paths")
    cfg = load_config()
    if cfg.thunderbird_bridge_path.exists():
        _ok(f"thunderbird-mcp bridge: {cfg.thunderbird_bridge_path}")
    else:
        _fail(f"thunderbird-mcp bridge missing: {cfg.thunderbird_bridge_path}")

    ensure_dirs()
    _ok(f"state dir: {STATE_DIR}")


def _check_env() -> None:
    _section("Environment")
    cfg = load_config()
    if cfg.anthropic_api_key and cfg.anthropic_api_key.startswith("sk-"):
        masked = cfg.anthropic_api_key[:8] + "…" + cfg.anthropic_api_key[-4:]
        _ok(f"ANTHROPIC_API_KEY set ({masked})")
    elif cfg.anthropic_api_key:
        _warn("ANTHROPIC_API_KEY set but doesn't look like a real key")
    else:
        _warn("ANTHROPIC_API_KEY not set — news + grants + hot-take disabled")
    _ok(f"claude model: {cfg.claude_model}")
    _ok(f"weather query: {cfg.weather_query}")
    _ok(f"timezones: local={cfg.timezone_local} market={cfg.timezone_market}")


def _check_systemd() -> None:
    _section("systemd --user")
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", "desktop-brief.service"],
            capture_output=True, text=True, timeout=5,
        )
        state = out.stdout.strip()
        if state == "active":
            _ok(f"desktop-brief.service: {state}")
        else:
            _warn(f"desktop-brief.service: {state}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        _warn("systemctl --user not available")


def _check_state() -> None:
    _section("State files")
    now_utc = datetime.now(timezone.utc)
    state_files = {
        "email": 120, "calendar": 120, "weather": 3600, "stocks": 1800,
        "hardware": 30, "news_headlines": 1800, "news_hottake": 86400 * 2, "grants": 86400,
    }
    for name, max_age in state_files.items():
        path = STATE_DIR / f"{name}.json"
        if not path.exists():
            _warn(f"{name}.json: missing (daemon not run yet?)")
            continue
        try:
            doc = json.loads(path.read_text())
            ts = doc.get("generated_at", "")
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age = (now_utc - ts_dt).total_seconds()
            if age <= max_age:
                _ok(f"{name}.json: fresh ({int(age)}s old)")
            else:
                _warn(f"{name}.json: stale ({int(age)}s > {max_age}s)")
        except Exception as e:
            _warn(f"{name}.json: parse error: {e}")

    if HEALTH_PATH.exists():
        try:
            doc = json.loads(HEALTH_PATH.read_text())
            sources = doc.get("data", {}).get("sources", {})
            for name, h in sources.items():
                cf = h.get("consecutive_failures", 0)
                if cf > 0:
                    _warn(f"{name}: {cf} consecutive failures (last: {(h.get('last_error') or '')[:80]})")
        except Exception:
            pass


async def _check_thunderbird_mcp() -> None:
    _section("Thunderbird MCP bridge")
    cfg = load_config()
    if not cfg.thunderbird_bridge_path.exists():
        _fail("bridge file missing — skipping connection test")
        return
    from desktop_brief.mcp.thunderbird_client import ThunderbirdMCPClient, ThunderbirdMCPError
    client = ThunderbirdMCPClient(cfg.thunderbird_bridge_path, request_timeout=5.0)
    try:
        await client.start()
        accounts = await client.list_accounts()
        _ok(f"bridge OK; listAccounts returned: {str(accounts)[:120]}")
    except ThunderbirdMCPError as e:
        _warn(f"bridge spawned but tool call failed: {e} (is Thunderbird running with the extension?)")
    except Exception as e:
        _fail(f"bridge spawn failed: {e}")
    finally:
        try:
            await client.stop()
        except Exception:
            pass


def main() -> int:
    print(f"{DIM}desktop-brief doctor{RESET}\n")
    _check_session()
    _check_binaries()
    _check_paths()
    _check_env()
    _check_systemd()
    _check_state()
    try:
        asyncio.run(_check_thunderbird_mcp())
    except Exception as e:
        _warn(f"thunderbird-mcp check crashed: {e}")

    print()
    if _FAILURES:
        print(f"{RED}{_FAILURES} failure(s){RESET}, {YELLOW}{_WARNINGS} warning(s){RESET}")
        return 1
    if _WARNINGS:
        print(f"{YELLOW}{_WARNINGS} warning(s){RESET} — review above.")
        return 0
    print(f"{GREEN}All checks passed.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
