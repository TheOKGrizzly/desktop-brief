"""Entry point for `dbrief-render` — prints the briefing to stdout."""
from __future__ import annotations

import argparse
import json
import sys

from desktop_brief.render.briefing import render_markdown


def main() -> int:
    p = argparse.ArgumentParser(description="Render the desktop-brief morning briefing.")
    p.add_argument("--markdown", action="store_true", help="Plain markdown to stdout (default).")
    p.add_argument(
        "--hook-json",
        action="store_true",
        help="Emit Claude Code SessionStart hook JSON wrapping the markdown in additionalContext.",
    )
    args = p.parse_args()

    md = render_markdown()
    if args.hook_json:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": md,
                }
            },
            sys.stdout,
        )
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
