#!/usr/bin/env bash
# Reads a state JSON file and extracts a jq expression.
# Usage: read_state.sh <source-name> <jq-expr> [default-on-error]
# Examples:
#   read_state.sh weather '.data.current.temp_f'
#   read_state.sh stocks  '.data.indices[0].change_pct' '0'
set -euo pipefail

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/desktop-brief"
SOURCE="$1"
EXPR="${2:-.}"
DEFAULT="${3:-}"
FILE="$STATE_DIR/$SOURCE.json"

if [[ ! -f "$FILE" ]]; then
    echo "${DEFAULT:-—}"
    exit 0
fi

OUT="$(jq -r --arg d "$DEFAULT" "($EXPR) // \$d" "$FILE" 2>/dev/null || true)"
if [[ -z "$OUT" || "$OUT" == "null" ]]; then
    echo "${DEFAULT:-—}"
else
    echo "$OUT"
fi
