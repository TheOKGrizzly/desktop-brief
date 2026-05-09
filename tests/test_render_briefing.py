"""Briefing renderer smoke tests — empty state, partial state."""
from __future__ import annotations

from desktop_brief.render.briefing import render_markdown


def test_renders_with_no_state(monkeypatch, tmp_path):
    # Force STATE_DIR to a fresh empty dir so all reads return None.
    from desktop_brief import paths, state
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "state_path", lambda name: tmp_path / f"{name}.json")
    md = render_markdown()
    assert "# Brief" in md
    assert "Inbox" in md
    assert "Calendar" in md
    assert "Markets" in md


def test_renders_with_partial_state(monkeypatch, tmp_path):
    from desktop_brief import paths, state
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "state_path", lambda name: tmp_path / f"{name}.json")
    state.write_source("weather", {
        "current": {"temp_f": 78, "condition": "Sunny", "icon": "☀", "humidity": 40, "wind_mph": 5},
        "today": {"high_f": 84, "low_f": 62, "precip_chance": 10, "sunrise": "06:00", "sunset": "20:00"},
    })
    md = render_markdown()
    assert "78°F" in md or "78" in md
    assert "Sunny" in md
