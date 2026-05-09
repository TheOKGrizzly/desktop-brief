# desktop-brief

A live Jarvis-style desktop briefing for Ubuntu / GNOME-on-Xorg.

A background daemon polls email, calendar, weather, stocks, news headlines,
and SBIR / DOE grant opportunities, writing each source to its own JSON state
file. Two front-ends consume that state:

- **Eww overlay** — always-on-top corner widget with live ticker, weather,
  next calendar event, mail counts, and per-source health dots.
- **Chromium kiosk briefing** — fullscreen Jarvis-themed dashboard summoned
  by `Super+J`, with clickable rows that deep-dive into Thunderbird,
  the browser, or the relevant source.

A Claude Code `SessionStart` hook reads the same state and shows a one-screen
markdown briefing whenever you open a Claude Code session.

## Architecture

```
┌─ desktop-brief-daemon (systemd --user) ──────────────────────────┐
│                                                                   │
│  asyncio supervisor                                               │
│   ├─ email_source       (Thunderbird MCP, 60s)                    │
│   ├─ calendar_source    (Thunderbird MCP, 60s, 15-min reminders)  │
│   ├─ weather            (wttr.in, 30 min)                         │
│   ├─ stocks             (Yahoo Finance, 60s mkt-hours / 15m off)  │
│   ├─ news_headlines     (Anthropic + WebSearch, 15 min)           │
│   ├─ news_hottake       (Anthropic, daily)                        │
│   └─ grants             (Anthropic + WebSearch, 6 h)              │
│                                                                   │
│  writes -> ~/.local/state/desktop-brief/{source}.json (atomic)    │
└────────────────────┬─────────────────────────────────────────────-┘
                     │
        ┌────────────┴───────────────────────────┐
        ▼                                        ▼
┌─ Eww overlay (X11) ──┐    ┌─ Chromium kiosk briefing ─┐
│ Always on top.       │    │ Summoned by Super+J.      │
│ Reads JSON via jq.   │    │ Reads JSON via fetch().   │
│ Refreshes every 5s.  │    │ Full Jarvis-themed CSS.   │
└──────────────────────┘    └───────────────────────────┘
                     │
                     ▼
         ┌─ Claude Code SessionStart hook ─┐
         │ dbrief-render --markdown        │
         │ Injected into session context.  │
         └─────────────────────────────────┘
```

## Requirements

- Ubuntu 24+ (X11 session — Eww does not work on GNOME Wayland; the install
  script will warn if you're on Wayland)
- Python ≥ 3.11
- Node ≥ 18 (for the Thunderbird MCP bridge)
- Cargo (the install script uses `cargo install eww`)
- Thunderbird with the `thunderbird-mcp` extension installed
- Anthropic API key (for news / hot-takes / grants)

## Install

```bash
git clone https://github.com/TheOKGrizzly/desktop-brief.git
cd desktop-brief
./install.sh
```

The install script handles apt deps, Eww (via cargo), the Python venv, the
systemd user service, and the GNOME `Super+J` shortcut. After it finishes,
it prints two manual follow-ups: adding the SessionStart hook to
`~/.claude/settings.json` and registering Thunderbird MCP in `~/.claude.json`
(both copy-pasteable from `docs/CLAUDE_HOOK_SETUP.md`).

## Quick reference

| `make install`      | install everything (idempotent)                 |
| `make uninstall`    | remove systemd unit + GNOME shortcut + venv     |
| `make logs`         | tail the daemon journal                         |
| `make status`       | systemd unit status                             |
| `make restart`      | restart the daemon                              |
| `make doctor`       | run `dbrief-doctor` health checks               |
| `make test`         | run unit tests                                  |

## Project layout

See `docs/ARCHITECTURE.md` for the full layout and component overview, and
`docs/DATA_CONTRACT.md` for the JSON schemas that the daemon writes.
