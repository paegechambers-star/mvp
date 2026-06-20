"""
Chat UI — browser-accessible front-end for mobile-to-desktop dispatch.

Serves a single-page chat interface at GET /chat.
Users type messages in the browser; results come back from desktop Claude.
No build step, no framework — plain HTML/CSS/JS embedded here.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["chat-ui"])

_CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Desktop Chat</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2e3147;
    --accent: #7c6af7;
    --accent-hover: #9585f9;
    --text: #e8eaf0;
    --muted: #6b7280;
    --user-bubble: #2a2d4a;
    --claude-bubble: #1e2035;
    --danger: #ef4444;
    --radius: 12px;
    --font: system-ui, -apple-system, sans-serif;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    height: 100dvh;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  header h1 { font-size: 15px; font-weight: 600; }
  #status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--muted); flex-shrink: 0;
    transition: background 0.3s;
  }
  #status-dot.online  { background: #22c55e; }
  #status-dot.pending { background: #f59e0b; }
  header .spacer { flex: 1; }
  #settings-btn {
    background: none; border: none; color: var(--muted);
    cursor: pointer; font-size: 18px; line-height: 1;
    padding: 4px; border-radius: 6px;
  }
  #settings-btn:hover { color: var(--text); background: var(--border); }

  /* ── Messages ── */
  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    scroll-behavior: smooth;
  }
  .msg {
    max-width: min(80%, 640px);
    padding: 10px 14px;
    border-radius: var(--radius);
    line-height: 1.55;
    font-size: 14px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg.user {
    align-self: flex-end;
    background: var(--user-bubble);
    border-bottom-right-radius: 3px;
  }
  .msg.claude {
    align-self: flex-start;
    background: var(--claude-bubble);
    border-bottom-left-radius: 3px;
    border: 1px solid var(--border);
  }
  .msg.error {
    align-self: flex-start;
    background: #2d1515;
    border: 1px solid var(--danger);
    color: #fca5a5;
  }
  .msg .meta {
    font-size: 11px;
    color: var(--muted);
    margin-top: 6px;
  }

  /* ── Thinking indicator ── */
  .thinking {
    display: flex;
    gap: 5px;
    align-items: center;
    align-self: flex-start;
    padding: 12px 16px;
    background: var(--claude-bubble);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    border-bottom-left-radius: 3px;
  }
  .thinking span {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--muted);
    animation: bounce 1.2s infinite ease-in-out;
  }
  .thinking span:nth-child(2) { animation-delay: 0.2s; }
  .thinking span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce {
    0%, 80%, 100% { transform: scale(0.7); opacity: 0.5; }
    40%           { transform: scale(1);   opacity: 1;   }
  }

  /* ── Input bar ── */
  #input-bar {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    background: var(--surface);
    border-top: 1px solid var(--border);
    flex-shrink: 0;
  }
  #input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    padding: 10px 14px;
    resize: none;
    min-height: 42px;
    max-height: 160px;
    overflow-y: auto;
    outline: none;
    transition: border-color 0.2s;
  }
  #input:focus { border-color: var(--accent); }
  #input::placeholder { color: var(--muted); }
  #send-btn {
    background: var(--accent);
    border: none;
    border-radius: var(--radius);
    color: #fff;
    cursor: pointer;
    font-size: 18px;
    width: 42px;
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.2s;
    align-self: flex-end;
  }
  #send-btn:hover:not(:disabled) { background: var(--accent-hover); }
  #send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── Setup modal ── */
  #modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  #modal-backdrop.hidden { display: none; }
  #modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    width: min(90vw, 400px);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  #modal h2 { font-size: 16px; }
  #modal p  { font-size: 13px; color: var(--muted); line-height: 1.5; }
  #modal label { font-size: 13px; color: var(--muted); }
  #modal input[type=text], #modal input[type=url] {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 13px;
    padding: 8px 12px;
    outline: none;
    margin-top: 4px;
  }
  #modal input:focus { border-color: var(--accent); }
  #modal-save {
    background: var(--accent);
    border: none;
    border-radius: 8px;
    color: #fff;
    cursor: pointer;
    font-size: 14px;
    padding: 10px;
    font-weight: 600;
    transition: background 0.2s;
  }
  #modal-save:hover { background: var(--accent-hover); }
  #modal-error { font-size: 12px; color: #fca5a5; min-height: 16px; }
</style>
</head>
<body>

<!-- Setup modal (shown on first visit or when token is missing) -->
<div id="modal-backdrop">
  <div id="modal">
    <h2>Connect to Desktop Claude</h2>
    <p>Enter the server address and a bearer token to start chatting with your desktop Claude instance.</p>
    <div>
      <label>Server URL
        <input id="cfg-server" type="url" value="http://localhost:8000" autocomplete="off" spellcheck="false">
      </label>
    </div>
    <div>
      <label>Bearer token
        <input id="cfg-token" type="text" placeholder="basic-my-secret-token" autocomplete="off" spellcheck="false">
      </label>
    </div>
    <div id="modal-error"></div>
    <button id="modal-save">Connect</button>
  </div>
</div>

<!-- Main chat -->
<header>
  <div id="status-dot"></div>
  <h1>Desktop Claude</h1>
  <span class="spacer"></span>
  <button id="settings-btn" title="Settings">⚙</button>
</header>

<div id="messages">
  <div class="msg claude">
    Hello! I'm Claude running on your desktop. Type a message and I'll get to work.
    <div class="meta">Desktop agent</div>
  </div>
</div>

<div id="input-bar">
  <textarea id="input" placeholder="Message Claude…" rows="1"></textarea>
  <button id="send-btn" title="Send (Enter)">&#9650;</button>
</div>

<script>
// ── Config ──────────────────────────────────────────────────────────────────
const LS_SERVER = 'dispatch_server';
const LS_TOKEN  = 'dispatch_token';

function cfg() {
  // URL params take precedence over localStorage
  const p = new URLSearchParams(location.search);
  return {
    server: p.get('server') || localStorage.getItem(LS_SERVER) || '',
    token:  p.get('token')  || localStorage.getItem(LS_TOKEN)  || '',
  };
}

function saveCfg(server, token) {
  localStorage.setItem(LS_SERVER, server);
  localStorage.setItem(LS_TOKEN,  token);
}

// ── Modal ───────────────────────────────────────────────────────────────────
const backdrop  = document.getElementById('modal-backdrop');
const modalErr  = document.getElementById('modal-error');
const cfgServer = document.getElementById('cfg-server');
const cfgToken  = document.getElementById('cfg-token');

function showModal() {
  const c = cfg();
  cfgServer.value = c.server || 'http://localhost:8000';
  cfgToken.value  = c.token  || '';
  backdrop.classList.remove('hidden');
  cfgToken.focus();
}

function hideModal() { backdrop.classList.add('hidden'); }

document.getElementById('modal-save').addEventListener('click', () => {
  const server = cfgServer.value.trim().replace(/\/$/, '');
  const token  = cfgToken.value.trim();
  if (!token) { modalErr.textContent = 'Token is required.'; return; }
  if (!server) { modalErr.textContent = 'Server URL is required.'; return; }
  modalErr.textContent = '';
  saveCfg(server, token);
  hideModal();
  setStatus('pending');
});

document.getElementById('settings-btn').addEventListener('click', showModal);

// ── Status dot ──────────────────────────────────────────────────────────────
const dot = document.getElementById('status-dot');
function setStatus(s) { dot.className = s; }  // 'online' | 'pending' | ''

// ── Messages ─────────────────────────────────────────────────────────────────
const feed = document.getElementById('messages');

function addMsg(text, role, meta) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  if (meta) {
    const m = document.createElement('div');
    m.className = 'meta';
    m.textContent = meta;
    div.appendChild(m);
  }
  feed.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return div;
}

function addThinking() {
  const div = document.createElement('div');
  div.className = 'thinking';
  div.innerHTML = '<span></span><span></span><span></span>';
  feed.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return div;
}

// ── Send & poll ──────────────────────────────────────────────────────────────
const input   = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');

let busy = false;

async function send() {
  const text = input.value.trim();
  if (!text || busy) return;
  const { server, token } = cfg();
  if (!token) { showModal(); return; }

  addMsg(text, 'user');
  input.value = '';
  autoResize();
  busy = true;
  sendBtn.disabled = true;
  setStatus('pending');

  const thinking = addThinking();

  try {
    // 1. Enqueue command
    const dispatchRes = await fetch(server + '/mobile/dispatch', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
      },
      body: JSON.stringify({ user_id: 'chat-user', payload: text }),
    });

    if (!dispatchRes.ok) {
      const err = await dispatchRes.json().catch(() => ({}));
      throw new Error(err.detail || 'Dispatch failed (' + dispatchRes.status + ')');
    }

    const { command_id } = await dispatchRes.json();

    // 2. Poll for result
    const result = await pollResult(server, token, command_id);
    thinking.remove();
    addMsg(result, 'claude', 'Desktop Claude');
    setStatus('online');

  } catch (err) {
    thinking.remove();
    addMsg(err.message, 'error', 'Error');
    setStatus('');
  } finally {
    busy = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

async function pollResult(server, token, commandId, maxMs = 120_000, intervalMs = 2_000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    await sleep(intervalMs);
    const res = await fetch(server + '/mobile/result/' + commandId, {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    if (res.status === 404) continue;  // not completed yet
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Poll failed (' + res.status + ')');
    }
    const data = await res.json();
    if (data.completed) return data.result || '(no result)';
  }
  throw new Error('Timed out waiting for desktop Claude (120 s)');
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── Input auto-resize + keyboard shortcuts ───────────────────────────────────
function autoResize() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 160) + 'px';
}

input.addEventListener('input', autoResize);
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
document.getElementById('send-btn').addEventListener('click', send);

// ── Init ──────────────────────────────────────────────────────────────────────
(function init() {
  const { token } = cfg();
  if (!token) {
    showModal();
  } else {
    hideModal();
    setStatus('online');
  }

  // Respect prefers-color-scheme if system is light (rare for this dark UI)
  input.focus();
})();
</script>
</body>
</html>
"""


@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_ui():
    """Serve the browser chat page."""
    return HTMLResponse(content=_CHAT_HTML)
