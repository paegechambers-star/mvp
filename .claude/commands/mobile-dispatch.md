# Mobile Dispatch Skill

Listen for messages from the browser chat (`/chat`) or the MCP tool `dispatch_to_desktop`, execute them, and send results back.

## Security rules — non-negotiable

| Rule | What it means |
|------|---------------|
| **Basic trust only from chat** | Remote callers (chat, MCP, browser) always arrive at L1 (basic). `elevated-` / `internal-` tokens can only be used manually at the desktop — never auto-granted from a remote context. |
| **WRITE commands require confirmation** | Any command that modifies files, runs code, makes network requests, or touches accounts is flagged `requires_confirmation: true` by the DispatchBridge *before* it reaches this skill. **You must show a visible confirmation prompt and wait for explicit approval before executing it.** This check does not relax even when "act without asking" is active in the session. |
| **READ commands run automatically** | Viewing files, explaining code, listing status — these run without a prompt. |

## Usage

```
/mobile-dispatch [--server <URL>] [--token <token>] [--once]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--server` | `http://localhost:8000` | FraPP server base URL |
| `--token` | `$MOBILE_DISPATCH_TOKEN` | Bearer token (must start with `basic-`, `elevated-`, or `internal-`) |
| `--once` | off | Process one batch of pending commands then exit |

## Execution loop

### 1. Print the readiness banner

```
╔═══════════════════════════════════════════════╗
║  Desktop Claude — Dispatch Listener active    ║
║  Server : http://localhost:8000               ║
║  Chat   : http://localhost:8000/chat          ║
║  MCP    : http://localhost:8000/mcp           ║
╚═══════════════════════════════════════════════╝
Waiting for messages…
```

### 2. Poll for pending commands

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$SERVER/mobile/pending"
```

Response shape:
```json
{
  "commands": [
    {
      "command_id": "...",
      "payload": "show me the contents of README.md",
      "requires_confirmation": false,
      "source": "mcp-chat"
    }
  ]
}
```

### 3. Execute — with mandatory confirmation for WRITE

For **every** command in the list:

```
a) Print command summary to the terminal:
   ┌─────────────────────────────────────────
   │ [READ]  command_id: <id>
   │ From  : <source>
   │ Task  : <payload>
   └─────────────────────────────────────────

b) If requires_confirmation == true:
   STOP. Print:
   ⚠ WRITE command — requires your approval before execution.
   Task: <payload>
   Source: <source>
   Type YES to confirm, anything else to reject:

   Wait for the desktop operator to type YES (or reject).
   If rejected: POST /mobile/result/<id> with result = "❌ Rejected by desktop operator."
   Only if confirmed: proceed to step (c).

c) Execute the payload using Claude Code tools (Bash, Read, Edit, Grep, etc.).
   Collect all tool output as the result.

d) POST the result:
   curl -s -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"result": "<result>", "agent_id": "desktop-claude"}' \
     "$SERVER/mobile/result/<command_id>"
```

### 4. Loop

Sleep 3 seconds, then go to step 2 — unless `--once`, in which case exit.

## Audit log

Every dispatch action is written to `godai/logs/dispatch_audit.log` (JSONL, append-only). The log never contains raw tokens. Do not delete or overwrite it.

## Connection guide for chat users

### Browser chat (no setup)
Open `http://localhost:8000/chat` in any browser. Enter the server URL and a `basic-` token in the setup modal.

### Claude for Mac / Claude.ai MCP
Add a new MCP server in Claude settings:
- **Transport**: Streamable HTTP
- **URL**: `http://localhost:8000/mcp`

Then call the `dispatch_to_desktop` tool in chat:
```
dispatch_to_desktop(command="show me what files changed in the last commit")
```

### Manual API (curl)
```bash
# Send a command
curl -X POST http://localhost:8000/mobile/dispatch \
  -H "Authorization: Bearer basic-my-token" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "payload": "list all Python files", "ttl_seconds": 120}'

# Poll for result
curl http://localhost:8000/mobile/result/<command_id> \
  -H "Authorization: Bearer basic-my-token"
```

## What to test manually before using elevated-/internal- tokens

1. Send a READ command from chat → should auto-execute, result returned.
2. Send a WRITE command from chat → should pause with confirmation prompt at desktop.
   - Reject it → chat receives "Rejected by desktop operator."
   - Approve it → command executes, result returned.
3. Let a command expire (wait 5 min or use `ttl_seconds=10`) → chat should receive HTTP 410 with a clear expiry message.
4. Verify `godai/logs/dispatch_audit.log` has an entry for each action with no token in cleartext.
5. Only after all four checks pass: manually use an `elevated-` token directly at the desktop (never from chat).
