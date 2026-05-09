#!/usr/bin/env bash
# Claude Code SessionStart hook: emits the morning briefing as additionalContext.
# Wire it into ~/.claude/settings.json — see docs/CLAUDE_HOOK_SETUP.md.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RENDER_BIN="$REPO_ROOT/.venv/bin/dbrief-render"

if [[ -x "$RENDER_BIN" ]]; then
    exec "$RENDER_BIN" --hook-json
else
    # Fail open with a minimal payload so a missing install doesn't break sessions.
    printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"_desktop-brief: render binary not found at %s_"}}' "$RENDER_BIN"
fi
