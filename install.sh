#!/usr/bin/env bash
# desktop-brief installer — idempotent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

c_blue()   { printf "\033[1;36m%s\033[0m\n" "$*"; }
c_yellow() { printf "\033[1;33m%s\033[0m\n" "$*"; }
c_red()    { printf "\033[1;31m%s\033[0m\n" "$*"; }
c_green()  { printf "\033[1;32m%s\033[0m\n" "$*"; }

c_blue "==> desktop-brief install"

# ---- preflight ----
if [[ "${XDG_SESSION_TYPE:-}" != "x11" ]]; then
    c_yellow "WARNING: not running an X11 session (XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-unset})."
    c_yellow "         Eww overlay needs X11 on GNOME — log out and pick 'Ubuntu on Xorg' before running the daemon."
fi

# ---- apt deps ----
APT_PKGS=(
    python3 python3-venv python3-pip
    nodejs
    jq curl
    libnotify-bin
    git
    build-essential pkg-config
    libgtk-3-dev libdbusmenu-gtk3-dev libpulse-dev libxdo-dev
    libgtk-layer-shell-dev   # eww wayland build (future-proofing)
)

NEEDED=()
for p in "${APT_PKGS[@]}"; do
    if ! dpkg -s "$p" >/dev/null 2>&1; then
        NEEDED+=("$p")
    fi
done

if (( ${#NEEDED[@]} )); then
    c_blue "==> Installing apt packages: ${NEEDED[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y "${NEEDED[@]}"
else
    c_green "✓ All apt packages already present."
fi

# ---- chromium / browser check ----
if ! command -v chromium >/dev/null 2>&1 \
   && ! command -v chromium-browser >/dev/null 2>&1 \
   && ! command -v google-chrome >/dev/null 2>&1; then
    c_yellow "No Chromium found. Recommend: sudo snap install chromium"
    c_yellow "(Firefox will be used as a fallback for the briefing window if Chromium isn't installed.)"
fi

# ---- rust + eww ----
if ! command -v eww >/dev/null 2>&1; then
    # Make sure cargo is on PATH even if user hasn't sourced rustup env yet.
    [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"
    if ! command -v cargo >/dev/null 2>&1; then
        c_blue "==> Installing rustup (cargo needed to build eww)"
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
        # shellcheck disable=SC1091
        source "$HOME/.cargo/env"
    fi
    c_blue "==> Building eww via cargo from git (this takes a few minutes the first time)"
    # Eww is not on crates.io — install directly from the upstream repo.
    # X11-only build (GNOME/Wayland needs wlr-layer-shell which Mutter lacks).
    cargo install --git https://github.com/elkowar/eww --locked --no-default-features --features x11 eww
else
    c_green "✓ eww already installed: $(command -v eww)"
fi

# ---- python venv ----
if [[ ! -d "$REPO_ROOT/.venv" ]]; then
    c_blue "==> Creating venv"
    python3 -m venv "$REPO_ROOT/.venv"
fi
c_blue "==> Installing/upgrading desktop-brief Python package"
"$REPO_ROOT/.venv/bin/pip" install -q --upgrade pip
"$REPO_ROOT/.venv/bin/pip" install -q -e "$REPO_ROOT[dev]"

# ---- .env ----
if [[ ! -f "$REPO_ROOT/.env" ]]; then
    c_blue "==> Seeding .env from .env.example (chmod 600)"
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    chmod 600 "$REPO_ROOT/.env"
    c_yellow "   ! Edit $REPO_ROOT/.env and set ANTHROPIC_API_KEY before news/grants will work."
fi

# ---- state dir ----
mkdir -p "$HOME/.local/state/desktop-brief"
chmod 700 "$HOME/.local/state/desktop-brief"

# ---- eww config link ----
mkdir -p "$HOME/.config/eww"
ln -sfn "$REPO_ROOT/eww" "$HOME/.config/eww/desktop-brief"

# ---- systemd user unit ----
mkdir -p "$HOME/.config/systemd/user"
# Substitute %h handled by systemd; copy the unit as-is.
cp -f "$REPO_ROOT/systemd/desktop-brief.service" "$HOME/.config/systemd/user/desktop-brief.service"
systemctl --user daemon-reload
systemctl --user enable --now desktop-brief.service
c_green "✓ systemd --user unit enabled + started"

# ---- gnome shortcut ----
bash "$REPO_ROOT/gnome/apply-shortcut.sh" || c_yellow "(GNOME shortcut binding skipped or failed — bind manually in Settings → Keyboard)"

# ---- app launcher (dock icon) ----
bash "$REPO_ROOT/gnome/install-launcher.sh" || c_yellow "(launcher install failed)"

# ---- xdg autostart (auto-open briefing on login) ----
mkdir -p "$HOME/.config/autostart"
sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$REPO_ROOT/gnome/desktop-brief-briefing.desktop" \
    > "$HOME/.config/autostart/desktop-brief-briefing.desktop"
c_green "✓ XDG autostart entry installed (briefing window opens 8 s after login)"

cat <<EOF

$(c_green "✓ desktop-brief installed.")

NEXT STEPS:

  1. Set ANTHROPIC_API_KEY in:
       $REPO_ROOT/.env

  2. Install the Thunderbird MCP extension (one-time, GUI step):
       Tools → Add-ons → Install from File →
       $HOME/projects/thunderbird-mcp/dist/thunderbird-mcp.xpi

  3. Open the Eww overlay now:
       eww --config $HOME/.config/eww/desktop-brief open overlay

  4. Press Super+J to open the fullscreen briefing.

  5. Wire the Claude Code SessionStart hook + Thunderbird MCP server:
       see docs/CLAUDE_HOOK_SETUP.md

  Tail the daemon log:    journalctl --user -u desktop-brief -f
  Run health check:       make doctor

EOF
