import json
import os
import re
import subprocess
import time
import uuid
import requests

# dsh (deepseek-harness) speaks a Typert RPC over POST /api/<namespace>/<method>.
# There is no bearer token: auth is a browser cookie minted from a per-launch token
# the dsh process prints to its journal. The cookie is signed with a persisted
# secret, so it survives dsh restarts and only expires after ~30 days — the
# bootstrap below runs roughly monthly, not per session.
_cookie_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "dsh_cookie.json")
_sessions_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "dsh_sessions.json")
_request_timeout_seconds = 20

def dsh_enabled() -> bool:
    return os.getenv("ENABLE_DSH", "false").lower() in ["true", "1", "yes"] and bool(os.getenv("DSH_URL", "").strip())

def _dsh_url() -> str:
    return os.getenv("DSH_URL", "").strip().rstrip("/")

def dsh_public_url() -> str:
    """Where the user watches sessions. The web UI has no per-session route, so the
    link is the app itself and the session's name is what makes it findable."""
    return os.getenv("DSH_PUBLIC_URL", _dsh_url()).strip().rstrip("/") + "/"

def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def _write_json(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f)

def _bootstrap_cookie() -> str:
    """Fetches a fresh auth cookie. A DSH_COOKIE from .env is used once — the manual
    escape hatch for when ssh to the dsh host isn't trusted — but never twice in a
    row: if it is the cookie that just got rejected, falling back to it again would
    loop forever, so the ssh path gets its turn. There the launch token is grepped
    out of the dsh host's own journal and exchanged for the cookie; the exchange
    must hit the same authority as DSH_URL, because the cookie is bound to the Host
    header it was minted against."""
    manual = os.getenv("DSH_COOKIE", "").strip()
    if manual and manual != _cookie():
        _write_json(_cookie_path, {"cookie": manual, "at": time.time()})
        return manual
    ssh_host = os.getenv("DSH_SSH_HOST", "").strip()
    if not ssh_host:
        return ""
    try:
        journal = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", ssh_host,
             "journalctl --user -u dsh.service --no-pager | grep -o 'token=[A-Za-z0-9_-]*' | tail -1"],
            capture_output=True, text=True, timeout=30,
        )
        token = journal.stdout.strip().removeprefix("token=")
    except Exception:
        return ""
    if not token:
        return ""
    try:
        response = requests.get(f"{_dsh_url()}/", params={"token": token}, allow_redirects=False, timeout=_request_timeout_seconds)
    except requests.RequestException:
        return ""
    set_cookie = response.headers.get("Set-Cookie", "")
    match = re.match(r"([^=]+=[^;]+)", set_cookie)
    if not match:
        return ""
    cookie = match.group(1)
    _write_json(_cookie_path, {"cookie": cookie, "at": time.time()})
    return cookie

def _cookie() -> str:
    return _read_json(_cookie_path).get("cookie") or ""

def _rpc(method: str, args: dict) -> dict:
    """One Typert call. The method name rides both in the URL and in the body and
    must match, or the gateway rejects the request outright. A 401 means the cookie
    aged out or dsh was reinstalled, so the bootstrap runs once and the call retries."""
    cookie = _cookie() or _bootstrap_cookie()
    if not cookie:
        return {"status": "error", "tool": "dsh", "message": "No dsh auth cookie and the bootstrap failed. Set DSH_COOKIE in .env or fix ssh to DSH_SSH_HOST."}
    body = {
        "type": "client-request",
        "rpcId": str(uuid.uuid4()),
        "method": method,
        "payload": {"args": args},
    }
    for attempt in range(2):
        try:
            response = requests.post(
                f"{_dsh_url()}/api/{method}",
                json=body,
                headers={"Cookie": cookie, "Content-Type": "application/json"},
                timeout=_request_timeout_seconds,
            )
        except requests.RequestException as e:
            return {"status": "error", "tool": "dsh", "message": f"dsh is unreachable: {e}"}
        if response.status_code in (401, 403) and attempt == 0:
            cookie = _bootstrap_cookie()
            if not cookie:
                return {"status": "error", "tool": "dsh", "message": "dsh rejected the auth cookie and the bootstrap failed. Set DSH_COOKIE in .env or fix ssh to DSH_SSH_HOST."}
            continue
        if not response.ok:
            return {"status": "error", "tool": "dsh", "message": f"dsh {method} failed with status {response.status_code}.", "details": response.text[:500]}
        try:
            result = response.json().get("result") or {}
        except Exception:
            return {"status": "error", "tool": "dsh", "message": f"dsh {method} returned something that isn't JSON."}
        if not result.get("ok"):
            return {"status": "error", "tool": "dsh", "message": f"dsh {method} said no.", "details": result.get("error")}
        return {"status": "success", "value": result.get("value")}
    return {"status": "error", "tool": "dsh", "message": "dsh rejected the auth cookie twice."}

def _session_prompt(todo_id: int, title: str, description: str, thread: list, extra: str) -> str:
    comments = "\n".join(
        f"- {'capy' if c.get('by_capy') else 'user'}: {c.get('comment', '')[:500]}"
        for c in (thread or [])[-10:]
    ) or "(none)"
    extra_line = f'\nThe user added alongside the /start command: "{extra}"' if extra else ""
    return (
        f'You are working on Vikunja task #{todo_id}: "{title}".\n'
        f"Description (HTML): {description or '(empty)'}\n"
        f"Recent comments, oldest first:\n{comments}{extra_line}\n\n"
        f"Use your vikunja MCP tools (mcp__vikunja__get_task, get_comments, add_comment, update_task, set_labels) on task {todo_id}.\n"
        "For web research use mcp__searxng__web_search (self-hosted metasearch; then web_fetch promising URLs to read "
        "them). mcp__searxng__web_search_private routes through Tor and takes 30-60s — only when the search itself "
        "must be private.\n"
        "- Post your progress, findings and any question you need answered as comments with add_comment. "
        "If you are blocked on information only the user has, ask in a comment and keep going on what you can.\n"
        "- Between major steps, call get_comments again: comments marked as written by the user (not by a bot) that "
        "arrived after you started are steering — follow them.\n"
        "- When you are done, post a final summary comment saying what you did and what, if anything, is left for the user."
    )

def read_sessions() -> dict:
    return _read_json(_sessions_path)

def session_for(todo_id: int) -> dict:
    return read_sessions().get(str(todo_id)) or {}

def start_task_session(todo_id: int, title: str, description: str = "", thread: list = [], extra: str = "") -> dict:
    """Creates a dsh session for the task, names it after the task so the user can
    find it in the sidebar, and hands it the work as its first prompt. One session
    per task: /start on a task that already has one steers it instead of spawning a
    twin, so a repeated /start after a flaky pass is safe."""
    if not dsh_enabled():
        return {"status": "error", "tool": "dsh", "message": "The dsh agent is disabled. Set ENABLE_DSH=true and DSH_URL in your .env file."}
    existing = session_for(todo_id)
    if existing:
        steered = _rpc("session/prompt", {"request": {
            "requestId": str(uuid.uuid4()),
            "sessionId": existing["sessionId"],
            "mode": "queue",
            "content": [{"type": "text", "text": f"The user commented /start again on task #{todo_id}. {extra or 'Continue the work and post a status comment on the task.'}"}],
        }})
        if steered.get("status") != "success":
            # The tracked session is gone on the dsh side; forget it and start fresh
            sessions = read_sessions()
            sessions.pop(str(todo_id), None)
            _write_json(_sessions_path, sessions)
        else:
            return {"status": "success", "existing": True, "name": existing["name"], "link": dsh_public_url()}
    created = _rpc("session/create", {"request": {
        "cwd": os.getenv("DSH_CWD", "").strip() or None,
        "agentPreset": os.getenv("DSH_AGENT_PRESET", "").strip() or None,
    }})
    if created.get("status") != "success":
        return created
    session_id = (created.get("value") or {}).get("sessionId")
    if not session_id:
        return {"status": "error", "tool": "dsh", "message": "dsh created a session but didn't say which.", "details": created.get("value")}
    name = f"#{todo_id} {title}"[:60]
    _rpc("session/rename", {"request": {"sessionId": session_id, "title": name}})
    model = os.getenv("DSH_MODEL", "").strip()
    if model:
        _rpc("session/selectModel", {"request": {
            "sessionId": session_id,
            "provider": os.getenv("DSH_MODEL_PROVIDER", "terra-think").strip(),
            "model": model,
        }})
    prompted = _rpc("session/prompt", {"request": {
        "requestId": str(uuid.uuid4()),
        "sessionId": session_id,
        "mode": "queue",
        "content": [{"type": "text", "text": _session_prompt(todo_id, title, description, thread, extra)}],
    }})
    if prompted.get("status") != "success":
        return prompted
    sessions = read_sessions()
    sessions[str(todo_id)] = {"sessionId": session_id, "name": name, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _write_json(_sessions_path, sessions)
    return {"status": "success", "existing": False, "name": name, "link": dsh_public_url()}

def steer_task_session(todo_id: int, text: str) -> dict:
    """Forwards a plain comment on a task with a live session into that session, so
    the user can steer the agent from the task thread without opening dsh."""
    existing = session_for(todo_id)
    if not dsh_enabled() or not existing:
        return {"status": "none"}
    steered = _rpc("session/prompt", {"request": {
        "requestId": str(uuid.uuid4()),
        "sessionId": existing["sessionId"],
        "mode": "queue",
        "content": [{"type": "text", "text": f"New comment from the user on task #{todo_id}, follow it: {text}"}],
    }})
    if steered.get("status") != "success":
        return steered
    return {"status": "success", "name": existing["name"], "link": dsh_public_url()}

def stop_task_session(todo_id: int) -> dict:
    """Cancels the task's session, if one is tracked. The mapping is dropped either
    way: a cancel that fails because the session is already gone shouldn't leave a
    ghost that swallows every later /start."""
    existing = session_for(todo_id)
    if not existing:
        return {"status": "none"}
    cancelled = _rpc("session/cancel", {"request": {"sessionId": existing["sessionId"]}})
    sessions = read_sessions()
    sessions.pop(str(todo_id), None)
    _write_json(_sessions_path, sessions)
    if cancelled.get("status") != "success":
        return cancelled
    return {"status": "success", "name": existing["name"]}
