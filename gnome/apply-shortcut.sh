#!/usr/bin/env bash
# Bind Super+J to open the desktop-brief Chromium kiosk briefing.
# Idempotent — safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="$REPO_ROOT/eww/scripts/open_briefing.sh"
NAME="desktop-brief Briefing"
BINDING="<Super>j"
ID_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/desktop-brief/"
KB_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
TOP_SCHEMA="org.gnome.settings-daemon.plugins.media-keys"

if ! command -v gsettings >/dev/null 2>&1; then
    echo "gsettings not found — skipping GNOME shortcut binding."
    exit 0
fi

# Append our id to the custom-keybindings list if not already present.
existing="$(gsettings get "$TOP_SCHEMA" custom-keybindings 2>/dev/null || echo "@as []")"
if [[ "$existing" == "@as []" ]]; then
    new="['$ID_PATH']"
elif [[ "$existing" == *"$ID_PATH"* ]]; then
    new="$existing"
else
    # Strip leading [ and append.
    inner="${existing#[}"
    inner="${inner%]}"
    if [[ -z "$inner" ]]; then
        new="['$ID_PATH']"
    else
        new="[${inner}, '$ID_PATH']"
    fi
fi

gsettings set "$TOP_SCHEMA" custom-keybindings "$new"
gsettings set "${KB_SCHEMA}:${ID_PATH}" name "$NAME"
gsettings set "${KB_SCHEMA}:${ID_PATH}" command "$COMMAND"
gsettings set "${KB_SCHEMA}:${ID_PATH}" binding "$BINDING"

echo "✓ Bound Super+J → $COMMAND"
