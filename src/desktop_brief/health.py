"""Per-source health tracking, written to health.json after every poll."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from desktop_brief.paths import HEALTH_PATH
from desktop_brief.state import atomic_write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SourceHealth:
    name: str
    interval_s: int
    last_success: str | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    total_polls: int = 0
    total_failures: int = 0


@dataclass
class HealthRegistry:
    """In-memory health for all running sources, flushed to disk after each update."""
    sources: dict[str, SourceHealth] = field(default_factory=dict)
    started_at: str = field(default_factory=_now)
    pid: int = field(default_factory=os.getpid)

    def register(self, name: str, interval_s: int) -> None:
        self.sources[name] = SourceHealth(name=name, interval_s=interval_s)
        self._flush()

    def record_success(self, name: str) -> None:
        s = self.sources.setdefault(name, SourceHealth(name=name, interval_s=0))
        s.last_success = _now()
        s.last_error = None
        s.consecutive_failures = 0
        s.total_polls += 1
        self._flush()

    def record_failure(self, name: str, err: str) -> None:
        s = self.sources.setdefault(name, SourceHealth(name=name, interval_s=0))
        s.last_error = err[:500]
        s.consecutive_failures += 1
        s.total_polls += 1
        s.total_failures += 1
        self._flush()

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": _now(),
            "source": "health",
            "data": {
                "daemon_pid": self.pid,
                "started_at": self.started_at,
                "sources": {
                    name: {
                        "interval_s": s.interval_s,
                        "last_success": s.last_success,
                        "last_error": s.last_error,
                        "consecutive_failures": s.consecutive_failures,
                        "total_polls": s.total_polls,
                        "total_failures": s.total_failures,
                    }
                    for name, s in self.sources.items()
                },
            },
        }

    def _flush(self) -> None:
        atomic_write_json(HEALTH_PATH, self.to_payload())


registry = HealthRegistry()
