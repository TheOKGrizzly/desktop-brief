#!/usr/bin/env bash
# Opens the fullscreen briefing window in Chromium kiosk mode.
# Bound to Super+J via the GNOME custom shortcut installed by install.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
URL="file://$REPO_ROOT/briefing/index.html"

# Prefer chromium; fall back to google-chrome or firefox.
for browser in chromium chromium-browser google-chrome firefox; do
    if command -v "$browser" >/dev/null 2>&1; then
        case "$browser" in
            firefox)
                exec "$browser" --kiosk "$URL"
                ;;
            *)
                exec "$browser" --new-window --app="$URL" --start-fullscreen
                ;;
        esac
    fi
done

notify-send -u critical "desktop-brief" "No browser found (chromium / google-chrome / firefox)"
exit 1
