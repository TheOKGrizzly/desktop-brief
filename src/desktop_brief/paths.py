"""XDG paths for desktop-brief runtime artifacts."""
from __future__ import annotations

import os
from pathlib import Path


def _xdg(env: str, fallback: str) -> Path:
    override = os.environ.get(env)
    if override:
        return Path(override).expanduser()
    return Path.home() / fallback


STATE_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "desktop-brief"
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "desktop-brief"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "desktop-brief"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "desktop-brief"


def state_path(name: str) -> Path:
    return STATE_DIR / f"{name}.json"


def ensure_dirs() -> None:
    """Create the runtime directories with private permissions.

    State + cache contain email subjects, calendar titles, and similar — chmod 700.
    """
    for d in (STATE_DIR, CONFIG_DIR, DATA_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o700)


LOG_PATH = STATE_DIR / "daemon.log"
HEALTH_PATH = STATE_DIR / "health.json"
CALENDAR_FIRED_PATH = STATE_DIR / "calendar_fired.json"
LLM_USAGE_PATH = STATE_DIR / "llm_usage.json"
