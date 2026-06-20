# Mobile Dispatch Skill

Listen for commands sent from a mobile phone and execute them as Claude Code tasks on the desktop.

## What this skill does

1. Connects to the FraPP mobile-dispatch API.
2. Polls (or holds a WebSocket connection) for incoming commands from mobile clients.
3. Executes each command as a Claude Code task in the current project.
4. Posts the result back so the mobile client can read it.

## Usage

```
/mobile-dispatch [--server <URL>] [--token <bearer-token>] [--once]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--server` | `http://localhost:8000` | Base URL of the FraPP server |
| `--token` | `$MOBILE_DISPATCH_TOKEN` | Bearer token (L1+ trust) |
| `--once` | off | Process one pending command, then exit (useful for CI/cron) |

## How it works

```
Mobile phone
  → POST /mobile/dispatch  {"payload": "run tests", "user_id": "alice"}
      ↓
  FraPP / HERMES (auth + rate-limit + audit)
      ↓
  DispatchBridge queue
      ↓
Desktop Claude (this skill)
  → picks up command
  → executes it (Bash / Edit / Read / etc.)
  → POST /mobile/result/{command_id}  {"result": "✓ 42 tests passed"}
      ↓
Mobile phone
  → GET /mobile/result/{command_id}  → reads the result
```

## Steps performed by this skill

1. **Authenticate** — read token from `--token` or `$MOBILE_DISPATCH_TOKEN`.
2. **Poll** — `GET /mobile/pending` (Authorization: Bearer <token>).
3. **Execute** — for each pending command, interpret `payload` as a natural-language task and carry it out using available Claude Code tools.
4. **Return result** — `POST /mobile/result/{command_id}` with the outcome.
5. **Loop** — repeat from step 2 unless `--once` was passed.

## Execution instructions

When invoked, perform the following steps exactly:

```python
import os, json, time, subprocess, urllib.request

SERVER  = "$ARGUMENTS_server" or "http://localhost:8000"
TOKEN   = "$ARGUMENTS_token"  or os.environ.get("MOBILE_DISPATCH_TOKEN", "")
ONCE    = "$ARGUMENTS_once"   == "true"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def http(method, path, body=None):
    url  = SERVER.rstrip("/") + path
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

while True:
    resp = http("GET", "/mobile/pending")
    for cmd in resp.get("commands", []):
        cid     = cmd["command_id"]
        payload = cmd["payload"]
        # --- hand payload to Claude Code tools for execution ---
        # result is collected from tool outputs
        result = f"Executed: {payload}"   # Claude Code replaces this with real output
        http("POST", f"/mobile/result/{cid}", {"result": result, "agent_id": "desktop-claude"})
    if ONCE:
        break
    time.sleep(5)
```

> **Note:** Claude Code will replace the placeholder result line with the actual output of the tools it runs in response to `payload`.

## Security notes

- The bearer token controls trust level: prefix `basic-` (L1), `elevated-` (L2), `internal-` (L3).
- All dispatched commands and results are recorded in MNEMOSYNE (immutable audit log).
- Commands expire after their `ttl_seconds` (default 300 s / 5 min).
- Use `elevated-` or `internal-` tokens only on trusted networks.
