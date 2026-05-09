"""Atomic write tests."""
from __future__ import annotations

import json
import threading

from desktop_brief import state


def test_write_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "state_path", lambda name: tmp_path / f"{name}.json")
    state.write_source("weather", {"temp_f": 78})
    out = state.read_source("weather")
    assert out is not None
    assert out["source"] == "weather"
    assert out["data"]["temp_f"] == 78
    assert out["schema_version"] == 1
    assert "generated_at" in out


def test_read_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "state_path", lambda name: tmp_path / f"{name}.json")
    assert state.read_source("nope") is None


def test_concurrent_writes_dont_corrupt(tmp_path, monkeypatch):
    """Many threads writing the same file: every read produces valid JSON."""
    monkeypatch.setattr(state, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "state_path", lambda name: tmp_path / f"{name}.json")

    errors = []

    def writer(i: int) -> None:
        try:
            for _ in range(50):
                state.write_source("weather", {"counter": i})
        except Exception as e:
            errors.append(e)

    def reader() -> None:
        try:
            for _ in range(50):
                v = state.read_source("weather")
                if v is not None:
                    json.dumps(v)  # ensure round-trippable
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
