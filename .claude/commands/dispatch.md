# Dispatch Skill

Starts the dispatch server if needed, then loops autonomously: picks up every message from the browser chat or MCP, executes it, sends the result back.

No configuration needed. Just run `/dispatch`.

---

## What to do — step by step

### Step 1 — ensure the server is running

Run this check:

```bash
curl -sf http://localhost:8000/healthz
```

If it returns `{"status":"ok"...}` the server is already up — skip to Step 2.

If it fails, start the server in the background:

```bash
nohup python -m uvicorn src.frapp.api:app --host 0.0.0.0 --port 8000 > /tmp/dispatch_server.log 2>&1 &
echo $! > /tmp/dispatch_server.pid
sleep 2
curl -sf http://localhost:8000/healthz
```

### Step 2 — print the ready banner

Print exactly this (fill in the real local IP if possible, otherwise use localhost):

```
╔══════════════════════════════════════════════════════╗
║  Dispatch is live                                    ║
║                                                      ║
║  Open in browser → http://localhost:8000/chat        ║
║  MCP endpoint   → http://localhost:8000/mcp          ║
║                                                      ║
║  Token (copy this into the chat setup modal):        ║
║  basic-local-dev                                     ║
╚══════════════════════════════════════════════════════╝
Listening for messages… (Ctrl-C to stop)
```

### Step 3 — autonomous loop

Repeat forever with a 3-second sleep between iterations:

```bash
RESULT=$(curl -sf \
  -H "Authorization: Bearer basic-local-dev" \
  http://localhost:8000/mobile/pending)
echo "$RESULT"
```

For every command object in `$.commands`:

**a) Print what arrived:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
From : <source field>
Task : <payload field>
Type : READ   ← or WRITE if requires_confirmation is true
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**b) If `requires_confirmation` is `true` — STOP and ask:**

Print this to the terminal and wait for the user's keyboard input before doing anything:

```
⚠  WRITE command — needs your OK before it runs.
Task: <payload>

Type YES to confirm, anything else to reject:
```

- If the user types `YES` (case-insensitive): proceed to step (c).
- Anything else: set RESULT_TEXT to `❌ Rejected by desktop operator.` and jump to step (d).

**c) Execute the task using Claude Code tools**

Treat `payload` as a normal user request. Use Bash, Read, Edit, Grep, Write — whatever is needed — and collect all output as RESULT_TEXT. Keep the answer concise (fits on a phone screen). Use markdown if it helps.

**d) Send the result back:**

```bash
PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({'result': sys.argv[1], 'agent_id': 'desktop-claude'}))
" "$RESULT_TEXT")

curl -sf -X POST \
  -H "Authorization: Bearer basic-local-dev" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "http://localhost:8000/mobile/result/<command_id>"
```

Print `✓ Reply sent` after success.

**e) Sleep 3 seconds, then repeat from the top of the loop.**

---

## Defaults (never ask the user to configure these)

| Setting | Value |
|---------|-------|
| Server URL | `http://localhost:8000` |
| Token | `basic-local-dev` |
| Chat URL | `http://localhost:8000/chat` |
| MCP URL | `http://localhost:8000/mcp` |
| Poll interval | 3 seconds |

The token `basic-local-dev` starts with `basic-` so HERMES assigns L1 trust automatically. No token setup needed.

---

## Security (always enforced, no exceptions)

- WRITE commands: **always** show the confirmation prompt and wait for YES before executing. This applies even when "act autonomously" is active in the session.
- READ commands: execute immediately, no prompt.
- Never use `elevated-` or `internal-` tokens from this skill — those require manual entry at the desktop.
