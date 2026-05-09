#!/usr/bin/env bash
# Install the desktop-brief app launcher: copy icon into the hicolor theme,
# materialize the .desktop file, pin to the GNOME favorites bar.
# Idempotent — safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="desktop-brief.desktop"

mkdir -p "$ICON_DIR" "$APP_DIR"

# Install the icon (referenced by name in the .desktop, no extension).
cp -f "$REPO_ROOT/assets/logo.svg" "$ICON_DIR/desktop-brief.svg"

# Materialize the .desktop with absolute path.
sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$REPO_ROOT/gnome/$DESKTOP_FILE" \
    > "$APP_DIR/$DESKTOP_FILE"
chmod +x "$APP_DIR/$DESKTOP_FILE" 2>/dev/null || true

# Refresh the icon cache so GNOME picks up the new SVG immediately.
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q "$APP_DIR" 2>/dev/null || true
fi

# Pin to GNOME favorites bar (the left-side dock) — idempotent append.
if command -v gsettings >/dev/null 2>&1; then
    current="$(gsettings get org.gnome.shell favorite-apps 2>/dev/null || echo "@as []")"
    if [[ "$current" == *"$DESKTOP_FILE"* ]]; then
        echo "✓ already pinned to GNOME favorites"
    else
        if [[ "$current" == "@as []" || "$current" == "[]" ]]; then
            new="['$DESKTOP_FILE']"
        else
            inner="${current#[}"; inner="${inner%]}"
            new="[${inner}, '$DESKTOP_FILE']"
        fi
        gsettings set org.gnome.shell favorite-apps "$new"
        echo "✓ pinned $DESKTOP_FILE to GNOME favorites bar"
    fi
fi

echo "✓ launcher installed: $APP_DIR/$DESKTOP_FILE"
echo "  icon: $ICON_DIR/desktop-brief.svg"
