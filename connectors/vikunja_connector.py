import json
import os
import requests
from datetime import datetime, timezone

_no_due_date = "0001-01-01T00:00:00Z"
_seen_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "vikunja_seen.json")
_request_timeout_seconds = 15

def vikunja_enabled() -> bool:
    return os.getenv("ENABLE_VIKUNJA", "false").lower() in ["true", "1", "yes"]

def subtasks_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_VIKUNJA_SUBTASKS", "false").lower() in ["true", "1", "yes"]

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
    try:
        return requests.request(method, _api_url(path), headers=_headers(), timeout=_request_timeout_seconds, **kwargs)
    except requests.RequestException as e:
        return {"status": "error", "tool": "vikunja", "message": f"Vikunja is unreachable: {e}"}

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
    response = _request("post", f"/tasks/{todo_id}", json=payload)
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo": _simplify_todo(response.json())}

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
    response = _request("post", f"/tasks/{todo_id}", json={"done": True})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
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
            _request("post", f"/tasks/{task['id']}", json={"percent_done": progress})

def check_new_todos() -> list[dict] | dict:
    """Returns to-dos created outside the bot since the last check, without marking
    them seen — the caller must mark_todos_seen after successfully notifying the
    user, so a failed notification is retried on the next check.
    First run seeds the seen file without reporting anything."""
    if not vikunja_enabled():
        return []
    response = _request("get", "/tasks", params={"per_page": 50, "sort_by": "id", "order_by": "desc"})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    tasks = response.json() or []
    _sync_subtask_progress(tasks)
    current_ids = {task["id"] for task in tasks}
    seen = _read_seen_ids()
    if seen is None:
        _write_seen_ids(list(current_ids))
        return []
    new_tasks = [task for task in tasks if task["id"] not in seen and not task.get("done", False)]
    new_ids = {task["id"] for task in new_tasks}
    _write_seen_ids(list((set(seen) | current_ids) - new_ids))
    return [_simplify_todo(task) for task in new_tasks]

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
