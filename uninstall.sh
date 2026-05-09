#!/usr/bin/env bash
# desktop-brief uninstaller — safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Stopping + disabling systemd unit"
systemctl --user disable --now desktop-brief.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/desktop-brief.service"
systemctl --user daemon-reload

echo "==> Closing eww overlay"
eww close overlay 2>/dev/null || true
rm -f "$HOME/.config/eww/desktop-brief"

echo "==> Removing XDG autostart entry"
rm -f "$HOME/.config/autostart/desktop-brief-briefing.desktop"

echo "==> Removing app launcher + dock pin"
rm -f "$HOME/.local/share/applications/desktop-brief.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/desktop-brief.svg"
if command -v gsettings >/dev/null 2>&1; then
    current="$(gsettings get org.gnome.shell favorite-apps 2>/dev/null || echo "@as []")"
    if [[ "$current" == *"desktop-brief.desktop"* ]]; then
        cleaned="${current//\'desktop-brief.desktop\', /}"
        cleaned="${cleaned//, \'desktop-brief.desktop\'/}"
        cleaned="${cleaned//\[\'desktop-brief.desktop\'\]/[]}"
        gsettings set org.gnome.shell favorite-apps "$cleaned"
    fi
fi

echo "==> Removing GNOME shortcut"
ID_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/desktop-brief/"
if command -v gsettings >/dev/null 2>&1; then
    existing="$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "@as []")"
    if [[ "$existing" == *"$ID_PATH"* ]]; then
        cleaned="${existing//\'$ID_PATH\', /}"
        cleaned="${cleaned//, \'$ID_PATH\'/}"
        cleaned="${cleaned//\[\'$ID_PATH\'\]/[]}"
        gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$cleaned"
    fi
    gsettings reset-recursively org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$ID_PATH" 2>/dev/null || true
fi

echo "==> Removing venv + caches (state files left in ~/.local/state/desktop-brief/)"
rm -rf "$REPO_ROOT/.venv" "$REPO_ROOT"/src/*.egg-info "$REPO_ROOT"/*.egg-info
find "$REPO_ROOT" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

cat <<EOF

✓ Uninstall complete.

Manual cleanup if you want a clean slate:
  rm -rf $HOME/.local/state/desktop-brief    # state + logs + LLM usage cache
  rm -f  $REPO_ROOT/.env                      # API key

apt packages (jq, eww deps, etc.) and the eww binary at ~/.cargo/bin/eww
were left in place; remove them manually if desired.

EOF
