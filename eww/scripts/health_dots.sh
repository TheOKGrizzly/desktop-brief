#!/usr/bin/env bash
# Emits Pango-marked colored dots representing per-source health.
# Green = fresh, yellow = aging, red = stale, gray = no data.
set -euo pipefail

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/desktop-brief"
HEALTH="$STATE_DIR/health.json"

if [[ ! -f "$HEALTH" ]]; then
    echo "<span color='#666'>● ● ● ● ● ● ●</span>"
    exit 0
fi

NOW="$(date +%s)"

dot_for() {
    local name="$1"
    local interval last_success age color
    interval="$(jq -r ".data.sources.\"$name\".interval_s // 60" "$HEALTH")"
    last_success="$(jq -r ".data.sources.\"$name\".last_success // \"\"" "$HEALTH")"
    if [[ -z "$last_success" ]]; then
        color="#666"
    else
        age=$(( NOW - $(date -d "$last_success" +%s 2>/dev/null || echo 0) ))
        if   (( age < interval * 2 )); then color="#22d3ee"
        elif (( age < interval * 5 )); then color="#facc15"
        else color="#ef4444"
        fi
    fi
    printf "<span color='%s' weight='bold'>●</span>" "$color"
}

OUT=""
for s in email calendar weather stocks hardware news_headlines grants; do
    OUT+="$(dot_for "$s") "
done
echo "$OUT"
