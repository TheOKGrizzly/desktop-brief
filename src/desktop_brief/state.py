"""Atomic JSON state writer/reader."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from desktop_brief.config import SCHEMA_VERSION
from desktop_brief.paths import STATE_DIR, ensure_dirs, state_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def envelope(source: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "source": source,
        "data": data,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically via tmpfile + os.replace.

    Readers never see a half-written file. The temp file is created in the
    same directory so the rename stays on one filesystem.
    """
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        path.chmod(0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def write_source(source: str, data: dict[str, Any]) -> Path:
    """Wrap data in the standard envelope and write atomically."""
    path = state_path(source)
    atomic_write_json(path, envelope(source, data))
    return path


def read_source(source: str) -> dict[str, Any] | None:
    """Read a source state file, or None if it doesn't exist."""
    path = state_path(source)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_sources() -> list[str]:
    """Return all source names that currently have state files."""
    if not STATE_DIR.exists():
        return []
    return sorted(p.stem for p in STATE_DIR.glob("*.json") if p.stem not in {"health", "calendar_fired", "llm_usage"})
