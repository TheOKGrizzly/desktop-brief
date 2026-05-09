#!/usr/bin/env bash
# Emits a one-line ticker summary for the Eww overlay.
# Format: "DJI ▲0.34% | NDX ▼0.12% | TSLA ▲1.20%"
set -euo pipefail

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/desktop-brief"
FILE="$STATE_DIR/stocks.json"

if [[ ! -f "$FILE" ]]; then
    echo "stocks loading..."
    exit 0
fi

jq -r '
  ((.data.indices // []) + ((.data.watchlist // []) | sort_by(.change_pct | (. // 0) | (. * -1) | fabs) | .[:3]))
  | map(
      (.symbol | ltrimstr("^")) as $s
      | (.change_pct // 0) as $p
      | (if $p >= 0 then "▲" else "▼" end) as $arrow
      | "\($s) \($arrow)\($p | tostring | (split(".") | .[0] + "." + (.[1] // "00")[0:2]))%"
    )
  | join("  ·  ")
' "$FILE" 2>/dev/null || echo "stocks unavailable"
