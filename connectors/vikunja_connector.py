import json
import os
import requests
import time
from datetime import datetime, timezone

_no_due_date = "0001-01-01T00:00:00Z"
_capy_notes_marker = "<h4>🔎 Capy notes</h4>"
# Comments Capy writes come back from the API authored by the user's own account,
# since that is whose token it holds. Without a marker of its own the watcher would
# read its own replies as new instructions and talk to itself forever. The header is
# visible so the thread is readable in Vikunja; the trailer survives even if someone
# edits the header away.
_capy_comment_header = "<p>🐹 <b>Capy</b></p>"
_capy_comment_marker = "<!-- capy -->"
_seen_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "vikunja_seen.json")
_request_timeout_seconds = 15
_request_retries = 1
_request_retry_delay_seconds = 2

def vikunja_enabled() -> bool:
    return os.getenv("ENABLE_VIKUNJA", "false").lower() in ["true", "1", "yes"]

def subtasks_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_VIKUNJA_SUBTASKS", "false").lower() in ["true", "1", "yes"]

def comments_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_TODO_COMMENTS", "false").lower() in ["true", "1", "yes"]

def retitle_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_TODO_RETITLE", "false").lower() in ["true", "1", "yes"]

def _disabled_error() -> dict:
    return {"status": "error", "tool": "vikunja", "message": "Vikunja to-do tool is disabled. To enable it, set ENABLE_VIKUNJA=true and configure VIKUNJA_API_HOST and VIKUNJA_API_TOKEN in your .env file."}

def _api_url(path: str) -> str:
    host = os.getenv("VIKUNJA_API_HOST", "").strip().rstrip("/")
    if not host.endswith("/api/v1"):
        host = f"{host}/api/v1"
    return f"{host}{path}"

def _headers() -> dict:
    token = os.getenv("VIKUNJA_API_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def _default_project_id() -> int:
    return int(os.getenv("VIKUNJA_DEFAULT_PROJECT_ID", "1"))

def _request(method: str, path: str, **kwargs) -> requests.Response | dict:
    """Retries once when the connection itself fails. A tailnet ingress occasionally
    answers a handshake with a TLS internal error and recovers on its own moments
    later, which is not worth interrupting the user for. Only connection level
    failures are retried, never timeouts: a timeout may mean the request arrived and
    was applied, and re-sending it would be a second write."""
    last_error = None
    for attempt in range(_request_retries + 1):
        try:
            return requests.request(method, _api_url(path), headers=_headers(), timeout=_request_timeout_seconds, **kwargs)
        except requests.ConnectionError as e:
            last_error = e
            if attempt < _request_retries:
                time.sleep(_request_retry_delay_seconds)
        except requests.RequestException as e:
            return {"status": "error", "tool": "vikunja", "message": f"Vikunja is unreachable: {e}"}
    return {"status": "error", "tool": "vikunja", "message": f"Vikunja is unreachable: {last_error}"}

def _patch_task(todo_id: int, changes: dict) -> requests.Response | dict:
    """Vikunja's task update replaces the whole task rather than merging: any field
    left out of the payload comes back blank. Posting {"done": true} on its own
    therefore erases the description, due date, priority and progress, which is how
    a to-do loses its notes the moment it gets ticked off. Everything that changes a
    task reads it first and writes it back whole."""
    response = _request("get", f"/tasks/{todo_id}")
    if isinstance(response, dict) or not response.ok:
        return response
    task = response.json()
    task.update(changes)
    return _request("post", f"/tasks/{todo_id}", json=task)

def _request_error(response: requests.Response) -> dict:
    try:
        details = response.json().get("message", response.text)
    except Exception:
        details = response.text
    return {"status": "error", "tool": "vikunja", "message": f"Vikunja API request failed with status {response.status_code}.", "details": details}

def _simplify_todo(task: dict) -> dict:
    due_date = task.get("due_date") or ""
    if due_date == _no_due_date:
        due_date = ""
    related = task.get("related_tasks") or {}
    subtasks = related.get("subtask") or []
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "description": task.get("description") or "",
        "done": task.get("done", False),
        "due_date": due_date,
        "priority": task.get("priority", 0),
        "project_id": task.get("project_id"),
        "percent_done": task.get("percent_done", 0),
        "updated": task.get("updated") or "",
        "done_at": task.get("done_at") or "",
        "is_subtask": bool(related.get("parenttask")),
        "subtasks": [{"id": s.get("id"), "title": s.get("title"), "done": s.get("done", False)} for s in subtasks],
    }

def add_todo(title: str, due_date: str = "", description: str = "", priority: int = 0, project_id: int = 0) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    payload = {"title": title, "description": description, "priority": priority}
    if due_date:
        payload["due_date"] = due_date
    response = _request("put", f"/projects/{project_id or _default_project_id()}/tasks", json=payload)
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    created = response.json()
    if created.get("id"):
        mark_todo_seen(created["id"])
    return {"status": "success", "todo": _simplify_todo(created)}

def list_todos(include_done: bool = False) -> list[dict] | dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", "/tasks", params={"per_page": 50, "sort_by": "due_date", "order_by": "asc"})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    tasks = response.json() or []
    todos = [_simplify_todo(task) for task in tasks]
    if not include_done:
        todos = [todo for todo in todos if not todo["done"]]
    return todos

def update_todo(todo_id: int, title: str = "", description: str = "", due_date: str = "", start_date: str = "", priority: int = -1) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    payload = {}
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    if due_date:
        payload["due_date"] = due_date
    if start_date:
        payload["start_date"] = start_date
    if priority >= 0:
        payload["priority"] = priority
    if not payload:
        return {"status": "error", "tool": "vikunja", "message": "Nothing to update, provide at least one field."}
    response = _patch_task(todo_id, payload)
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo": _simplify_todo(response.json())}

def get_todo(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", f"/tasks/{todo_id}")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo": _simplify_todo(response.json())}

def append_todo_description(todo_id: int, notes_html: str) -> dict:
    """Writes research findings into the to-do under a marker heading. Everything the
    user wrote lives above the marker and is never touched, and a previous Capy block
    is replaced rather than stacked, so re-running research stays idempotent."""
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", f"/tasks/{todo_id}")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    current = response.json().get("description") or ""
    user_text = current.split(_capy_notes_marker)[0].rstrip()
    updated = f"{user_text}\n{_capy_notes_marker}\n{notes_html}" if user_text else f"{_capy_notes_marker}\n{notes_html}"
    saved = _patch_task(todo_id, {"description": updated})
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    return {"status": "success", "todo": _simplify_todo(saved.json())}

def _is_capy_comment(comment: str) -> bool:
    return _capy_comment_marker in comment or _capy_comment_header in comment

def list_todo_comments(todo_id: int) -> dict:
    """The conversation held on the to-do itself, oldest first, each flagged with
    whether Capy or the user wrote it."""
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", f"/tasks/{todo_id}/comments")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    comments = response.json() or []
    return {
        "status": "success",
        "todo_id": todo_id,
        "comments": [{
            "id": comment.get("id"),
            "comment": comment.get("comment") or "",
            "created": comment.get("created") or "",
            "by_capy": _is_capy_comment(comment.get("comment") or ""),
        } for comment in sorted(comments, key=lambda c: c.get("id") or 0)],
    }

def add_todo_comment(todo_id: int, comment_html: str) -> dict:
    """Replies in the to-do's own thread, signed, so the back and forth about a task
    stays attached to the task instead of scrolling away in chat."""
    if not vikunja_enabled():
        return _disabled_error()
    body = f"{_capy_comment_header}\n{comment_html}\n{_capy_comment_marker}"
    response = _request("put", f"/tasks/{todo_id}/comments", json={"comment": body})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo_id": todo_id, "comment_id": response.json().get("id")}

def rename_todo(todo_id: int, new_title: str) -> dict:
    """Rewrites the title and remembers the original. Vikunja keeps no title history,
    and a rewrite the user doesn't recognise is worse than the clumsy title they wrote
    themselves, so undo has to be possible."""
    if not vikunja_enabled():
        return _disabled_error()
    current = get_todo(todo_id)
    if current.get("status") != "success":
        return current
    old_title = current["todo"]["title"]
    new_title = (new_title or "").strip()
    if not new_title or new_title == old_title:
        return {"status": "success", "changed": False, "title": old_title, "message": "The title was already fine, left it alone."}
    saved = _patch_task(todo_id, {"title": new_title})
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    state = _read_state()
    originals = state.get("original_titles") or {}
    # Only the first rename is the user's own wording, so never overwrite it
    originals.setdefault(str(todo_id), old_title)
    state["original_titles"] = dict(list(originals.items())[-50:])
    # Picked up by the caller after the message is composed, so the undo button can
    # ride along on the same message rather than arriving as a second notification
    state["pending_renames"] = (state.get("pending_renames") or [])[-10:] + [{"id": todo_id, "from": old_title, "to": new_title}]
    _write_state(state)
    return {"status": "success", "changed": True, "todo_id": todo_id, "from": old_title, "to": new_title}

def pop_pending_renames() -> list[dict]:
    state = _read_state()
    renames = state.get("pending_renames") or []
    if renames:
        state["pending_renames"] = []
        _write_state(state)
    return renames

def undo_title_buttons() -> list[list[tuple[str, str]]] | None:
    """Undo offers for whatever was renamed while composing the message being sent.
    Called on every path that could have triggered a rename, so the offer always sits
    on the message that announced the change instead of drifting onto a later one."""
    return [
        [(f"↩️ Undo: {rename['from'][:22]}", f"/undotitle {rename['id']}")]
        for rename in pop_pending_renames()[-3:]
    ] or None

def restore_todo_title(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    state = _read_state()
    originals = state.get("original_titles") or {}
    old_title = originals.get(str(todo_id))
    if not old_title:
        return {"status": "error", "tool": "vikunja", "message": f"I don't have the original title for to-do {todo_id} anymore."}
    saved = _patch_task(todo_id, {"title": old_title})
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    originals.pop(str(todo_id), None)
    state["original_titles"] = originals
    _write_state(state)
    return {"status": "success", "todo_id": todo_id, "title": old_title}

def add_subtasks(parent_todo_id: int, titles: list[str]) -> dict:
    """Creates the subtasks in the parent's project, prefixing each title with
    the parent's name and step number (e.g. '[ change car tyres - 1 ] lift car')
    so every step stays visibly connected to the original to-do in the list."""
    if not subtasks_enabled():
        return {"status": "error", "tool": "vikunja", "message": "Subtask splitting is disabled. To enable it, set ENABLE_VIKUNJA_SUBTASKS=true in your .env file."}
    parent_response = _request("get", f"/tasks/{parent_todo_id}")
    if isinstance(parent_response, dict):
        return parent_response
    if not parent_response.ok:
        return _request_error(parent_response)
    parent = parent_response.json()
    project_id = parent.get("project_id") or _default_project_id()
    parent_title = parent.get("title") or f"To-do {parent_todo_id}"
    step = len((parent.get("related_tasks") or {}).get("subtask") or []) + 1
    created = []
    for title in titles:
        response = _request("put", f"/projects/{project_id}/tasks", json={"title": f"[ {parent_title} - {step} ] {title}"})
        if isinstance(response, dict) or not response.ok:
            error = response if isinstance(response, dict) else _request_error(response)
            error["created_so_far"] = created
            return error
        subtask = response.json()
        mark_todo_seen(subtask["id"])
        relation = _request("put", f"/tasks/{parent_todo_id}/relations", json={"other_task_id": subtask["id"], "relation_kind": "subtask"})
        if isinstance(relation, dict) or not relation.ok:
            error = relation if isinstance(relation, dict) else _request_error(relation)
            error["created_so_far"] = created
            return error
        created.append(_simplify_todo(subtask))
        step += 1
    return {"status": "success", "parent_todo_id": parent_todo_id, "subtasks": created}

def complete_todo(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _patch_task(todo_id, {"done": True})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    mark_todos_done([todo_id])
    return {"status": "success", "todo": _simplify_todo(response.json())}

def delete_todo(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("delete", f"/tasks/{todo_id}")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "message": f"To-do {todo_id} deleted."}

def _read_state() -> dict:
    try:
        with open(_seen_path) as f:
            return json.load(f)
    except Exception:
        return {}

def _write_state(state: dict) -> None:
    with open(_seen_path, "w") as f:
        json.dump(state, f)

def _read_seen_ids() -> list[int] | None:
    return _read_state().get("seen_ids")

def _write_seen_ids(ids: list[int]) -> None:
    state = _read_state()
    state["seen_ids"] = sorted(ids)
    _write_state(state)

def mark_todos_seen(todo_ids: list[int]) -> None:
    seen = set(_read_seen_ids() or [])
    if not set(todo_ids) <= seen:
        _write_seen_ids(list(seen | set(todo_ids)))

def mark_todo_seen(todo_id: int) -> None:
    mark_todos_seen([todo_id])

def _sync_subtask_progress(tasks: list[dict]) -> None:
    """Keeps each parent task's percent_done bar in sync with how many of its
    subtasks are done, so completing subtasks anywhere fills the progress bar."""
    for task in tasks:
        subtasks = (task.get("related_tasks") or {}).get("subtask") or []
        if not subtasks or task.get("done"):
            continue
        progress = round(sum(1 for s in subtasks if s.get("done", False)) / len(subtasks), 2)
        if abs(task.get("percent_done", 0) - progress) >= 0.01:
            _patch_task(task["id"], {"percent_done": progress})

def check_todo_updates() -> dict:
    """Returns {"status": "success", "new": [...], "completed": [...]} with to-dos
    created outside the bot and to-dos completed since the last check, without
    marking them handled — the caller must mark_todos_seen / mark_todos_done after
    successfully notifying the user, so a failed notification is retried on the
    next check. First run seeds the state without reporting anything."""
    if not vikunja_enabled():
        return {"status": "success", "new": [], "completed": []}
    response = _request("get", "/tasks", params={"per_page": 50, "sort_by": "id", "order_by": "desc"})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    tasks = response.json() or []
    _sync_subtask_progress(tasks)
    current_ids = {task["id"] for task in tasks}
    current_done_ids = {task["id"] for task in tasks if task.get("done", False)}
    state = _read_state()
    seen = state.get("seen_ids")
    done = state.get("done_ids")
    new_tasks = []
    completed_tasks = []
    if seen is None:
        state["seen_ids"] = sorted(current_ids)
    else:
        new_tasks = [task for task in tasks if task["id"] not in seen and not task.get("done", False)]
        new_ids = {task["id"] for task in new_tasks}
        state["seen_ids"] = sorted((set(seen) | current_ids) - new_ids)
    if done is None:
        state["done_ids"] = sorted(current_done_ids)
    else:
        completed_tasks = [task for task in tasks if task["id"] in current_done_ids and task["id"] not in done]
        state["done_ids"] = sorted(set(done) & current_done_ids)
    _write_state(state)
    return {
        "status": "success",
        "new": [_simplify_todo(task) for task in new_tasks],
        "completed": [_simplify_todo(task) for task in completed_tasks],
    }

def mark_todos_done(todo_ids: list[int]) -> None:
    state = _read_state()
    done = set(state.get("done_ids") or [])
    if not set(todo_ids) <= done:
        state["done_ids"] = sorted(done | set(todo_ids))
        _write_state(state)

def check_todo_comments() -> dict:
    """Returns {"status": "success", "threads": [...]} for comments the user has
    written on their to-dos since the last check, so a task can be steered from
    inside Vikunja instead of only through chat.

    Posting a comment bumps the task's own updated timestamp, which is what makes
    this affordable: only tasks that actually changed get their thread fetched, so
    a quiet list costs exactly one request. State is kept per task, so a thread that
    fails to deliver is retried on its own without holding up or swallowing the rest.
    The caller must mark_comments_seen once the user has actually been told."""
    if not comments_enabled():
        return {"status": "success", "threads": []}
    response = _request("get", "/tasks", params={"per_page": 50, "sort_by": "id", "order_by": "desc"})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    tasks = response.json() or []
    state = _read_state()
    # Absent on the very first run only: existing threads are history, not instructions
    seeding = "comment_state" not in state
    comment_state = state.get("comment_state") or {}
    fresh_state = {}
    threads = []
    for task in tasks:
        key = str(task["id"])
        known = comment_state.get(key) or {}
        # Done tasks keep their watermark rather than being pruned, so reopening one
        # doesn't replay its whole thread as if it were new
        if task.get("done", False):
            if known:
                fresh_state[key] = known
            continue
        # The changed check is only a way to avoid pointless requests, never the thing
        # that decides what counts as new. Vikunja's updated stamp has one second
        # resolution, so a comment landing in the same second as a scan would look like
        # no change at all: once a task has a thread it is always read, and only tasks
        # nobody has ever commented on are skipped on the cheap.
        if known.get("updated") == (task.get("updated") or "") and not known.get("has_comments"):
            fresh_state[key] = known
            continue
        found = list_todo_comments(task["id"])
        if found.get("status") != "success":
            # Leave this one exactly as it was so the next pass tries again
            if known:
                fresh_state[key] = known
            continue
        comments = found["comments"]
        watermark = known.get("watermark", 0)
        scanned = {
            "updated": task.get("updated") or "",
            "watermark": max([c["id"] for c in comments] + [watermark]),
            "has_comments": bool(comments),
        }
        new_comments = [c for c in comments if c["id"] > watermark and not c["by_capy"]]
        if seeding or not new_comments:
            fresh_state[key] = scanned
            continue
        # Held back until delivered, so a failed message doesn't lose the comment
        fresh_state[key] = known
        threads.append({
            "todo": _simplify_todo(task),
            "thread": comments,
            "new_comments": [c["comment"] for c in new_comments],
            "seen": scanned,
        })
    state["comment_state"] = fresh_state
    _write_state(state)
    return {"status": "success", "threads": threads}

def mark_comments_seen(todo_id: int, seen: dict) -> None:
    state = _read_state()
    comment_state = state.get("comment_state") or {}
    comment_state[str(todo_id)] = seen
    state["comment_state"] = comment_state
    _write_state(state)

def daily_focus_todos() -> list[dict] | dict | bool:
    """Once a day at VIKUNJA_DAILY_FOCUS_HOUR (UTC, -1 disables), returns the
    pending to-dos for the morning focus message. Returns False when it's not
    time yet or already sent today — the caller must mark_focus_sent after
    successfully sending, so a failure is retried on the next heartbeat."""
    focus_hour = int(os.getenv("VIKUNJA_DAILY_FOCUS_HOUR", "-1"))
    if not vikunja_enabled() or focus_hour < 0:
        return False
    now = datetime.now(timezone.utc)
    if now.hour < focus_hour:
        return False
    if _read_state().get("last_focus_date") == now.date().isoformat():
        return False
    return list_todos()

def mark_focus_sent() -> None:
    state = _read_state()
    state["last_focus_date"] = datetime.now(timezone.utc).date().isoformat()
    _write_state(state)

def daily_dateless_todos() -> list[dict] | dict | bool:
    """Once a day at VIKUNJA_DATE_NUDGE_HOUR (UTC, -1 disables), returns the pending
    top-level to-dos missing a due date, so the agent can ask the user for dates.
    Returns False when it's not time yet or already sent today — the caller must
    mark_date_nudge_sent after successfully sending."""
    nudge_hour = int(os.getenv("VIKUNJA_DATE_NUDGE_HOUR", "-1"))
    if not vikunja_enabled() or nudge_hour < 0:
        return False
    now = datetime.now(timezone.utc)
    if now.hour < nudge_hour:
        return False
    if _read_state().get("last_date_nudge_date") == now.date().isoformat():
        return False
    todos = list_todos()
    if isinstance(todos, dict):
        return todos
    return [todo for todo in todos if not todo["due_date"] and not todo["is_subtask"]]

def mark_date_nudge_sent() -> None:
    state = _read_state()
    state["last_date_nudge_date"] = datetime.now(timezone.utc).date().isoformat()
    _write_state(state)

def _parse_timestamp(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None

def _weekly_slot(state_key: str) -> str | bool:
    """Shared gate for the once-a-week moments. Returns the week key to store when it
    is time, or False otherwise, mirroring how the daily ones work."""
    review_day = int(os.getenv("WEEKLY_REVIEW_DAY", "-1"))
    if not vikunja_enabled() or review_day < 0:
        return False
    now = datetime.now(timezone.utc)
    if now.weekday() != review_day or now.hour < int(os.getenv("WEEKLY_REVIEW_HOUR", "9")):
        return False
    week = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    if _read_state().get(state_key) == week:
        return False
    return week

def weekly_stale_todos() -> list[dict] | dict | bool:
    """Up to 3 to-dos nobody has touched in STALE_TODO_DAYS. Capped deliberately:
    the point is to make the list trustworthy again, and a wall of forgotten tasks
    does the opposite. The caller must mark_stale_sweep_sent after sending."""
    if not _weekly_slot("last_stale_sweep_week"):
        return False
    todos = list_todos()
    if isinstance(todos, dict):
        return todos
    cutoff = int(os.getenv("STALE_TODO_DAYS", "21"))
    now = datetime.now(timezone.utc)
    stale = []
    for todo in todos:
        updated = _parse_timestamp(todo["updated"])
        if todo["is_subtask"] or not updated:
            continue
        if (now - updated).days >= cutoff:
            stale.append(todo)
    return stale[:3]

def mark_stale_sweep_sent() -> None:
    now = datetime.now(timezone.utc)
    state = _read_state()
    state["last_stale_sweep_week"] = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    _write_state(state)

def weekly_wins() -> list[dict] | dict | bool:
    """What actually got finished in the last 7 days. ADHD memory badly undercounts
    wins, so this exists to be evidence. Caller must mark_digest_sent after sending."""
    if not _weekly_slot("last_digest_week"):
        return False
    todos = list_todos(include_done=True)
    if isinstance(todos, dict):
        return todos
    now = datetime.now(timezone.utc)
    wins = []
    for todo in todos:
        if not todo["done"]:
            continue
        done_at = _parse_timestamp(todo["done_at"])
        if done_at and (now - done_at).days < 7:
            wins.append(todo)
    return wins

def mark_digest_sent() -> None:
    now = datetime.now(timezone.utc)
    state = _read_state()
    state["last_digest_week"] = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    _write_state(state)

def list_todo_projects() -> list[dict] | dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", "/projects", params={"per_page": 50})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    projects = response.json() or []
    return [{"id": p.get("id"), "title": p.get("title")} for p in projects]
