# Mobile Dispatch Skill

Listen for messages sent from the browser chat (or any mobile client) and reply as Claude Code running on the desktop.

## What this skill does

Runs a conversation loop: waits for messages from `/chat` (or any HTTP client), executes each one using Claude Code tools, and sends the result back so it appears in the chat UI.

## Usage

```
/mobile-dispatch [--server <URL>] [--token <token>] [--once]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--server` | `http://localhost:8000` | Base URL of the FraPP server |
| `--token` | `$MOBILE_DISPATCH_TOKEN` | Bearer token sent with every request |
| `--once` | off | Handle one pending message then exit |

If `$MOBILE_DISPATCH_TOKEN` is not set, use any string prefixed with `basic-` (e.g. `basic-dev`).

## Execution steps

When this skill is invoked, run the following loop **using Bash**:

### 1. Read config

```bash
SERVER="${ARGUMENTS_server:-${MOBILE_DISPATCH_SERVER:-http://localhost:8000}}"
TOKEN="${ARGUMENTS_token:-${MOBILE_DISPATCH_TOKEN:-basic-dev}}"
ONCE="${ARGUMENTS_once:-false}"
```

### 2. Announce readiness

Print to the terminal so the user knows the agent is live:

```
╔══════════════════════════════════════════╗
║  Desktop Claude — Dispatch Listener      ║
║  Server : <SERVER>                       ║
║  Token  : <TOKEN prefix>****             ║
║  Chat   : <SERVER>/chat                  ║
╚══════════════════════════════════════════╝
Waiting for messages from chat…
```

### 3. Poll and respond

Repeat forever (or once if `--once`):

```bash
# Fetch pending commands
PENDING=$(curl -sf -H "Authorization: Bearer $TOKEN" "$SERVER/mobile/pending")

# For each command (iterate with jq or python -c):
#   command_id = .commands[].command_id
#   payload    = .commands[].payload
#   user_id    = .commands[].user_id

# For each pending command:
echo "──────────────────────────────────────"
echo "From : $user_id"
echo "Msg  : $payload"
echo "ID   : $command_id"
echo "──────────────────────────────────────"

# Execute the payload as a Claude Code task using the appropriate tools
# (Read files, Bash, Edit, Grep, etc.), then collect the output as RESULT.

# Post the result back
curl -sf -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"result\": \"$RESULT\", \"agent_id\": \"desktop-claude\"}" \
  "$SERVER/mobile/result/$command_id"

echo "✓ Reply sent"

sleep 3   # poll interval
```

### 4. Handle `--once`

If `--once` is set, exit after processing the first batch (even if the queue is empty).

## Important: executing payloads

The `payload` field is a natural-language task from the chat user. Treat it exactly as you would treat a user message in normal chat: use your tools (Bash, Read, Edit, Grep, Write, etc.) to complete the task, collect the output, and use that as `RESULT`.

Keep the result concise (fits comfortably on a phone screen). Use markdown if it helps readability.

## Security notes

- Token prefix controls trust: `basic-` (L1), `elevated-` (L2), `internal-` (L3).
- All messages and results are recorded in MNEMOSYNE (immutable audit log).
- Messages expire after `ttl_seconds` (default 5 min) if the desktop agent is offline.
- Open `<SERVER>/chat` in any browser to start chatting.
