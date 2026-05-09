# Wiring desktop-brief into Claude Code

Two manual edits to your Claude Code config — install.sh deliberately doesn't
touch these because your settings file may have hand-tuned hooks/permissions.

## 1. SessionStart hook → morning briefing every session

Add this `hooks` block to **`~/.claude/settings.json`** (merge with whatever
you already have):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/home/travis-turner/projects/desktop-brief/hooks/session_start.sh"
          }
        ]
      }
    ]
  }
}
```

The hook runs `dbrief-render --hook-json`, which reads the daemon's state
files and injects a one-screen markdown briefing into `additionalContext`.
If the daemon hasn't run yet (or the venv is missing) the hook fails open
with a placeholder message instead of breaking your session.

## 2. Thunderbird MCP server → so Claude Code can also talk to your mail

Add this to **`~/.claude.json`** under top-level `mcpServers` (create the key
if it doesn't exist):

```json
{
  "mcpServers": {
    "thunderbird-mail": {
      "command": "node",
      "args": ["/home/travis-turner/projects/thunderbird-mcp/mcp-bridge.cjs"]
    }
  }
}
```

Note: the desktop-brief daemon spawns its **own** instance of the bridge
internally — registering it here is only so that *interactive* Claude Code
sessions can call Thunderbird tools too (e.g. you ask Claude to draft a
reply to an unread email). The two instances coexist fine.

## Test

After editing, in a new Claude Code session you should see the briefing
appear at the top of context. To eyeball the rendered briefing without
opening Claude Code:

```bash
cd ~/projects/desktop-brief
./.venv/bin/dbrief-render --markdown
```
