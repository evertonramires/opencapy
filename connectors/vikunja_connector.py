import json
import os
import requests

_no_due_date = "0001-01-01T00:00:00Z"
_seen_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "vikunja_seen.json")
_request_timeout_seconds = 15

def vikunja_enabled() -> bool:
    return os.getenv("ENABLE_VIKUNJA", "false").lower() in ["true", "1", "yes"]

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
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "description": task.get("description") or "",
        "done": task.get("done", False),
        "due_date": due_date,
        "priority": task.get("priority", 0),
        "project_id": task.get("project_id"),
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

def _read_seen_ids() -> list[int] | None:
    if not os.path.exists(_seen_path):
        return None
    try:
        with open(_seen_path) as f:
            return json.load(f)["seen_ids"]
    except Exception:
        return None

def _write_seen_ids(ids: list[int]) -> None:
    with open(_seen_path, "w") as f:
        json.dump({"seen_ids": sorted(ids)}, f)

def mark_todos_seen(todo_ids: list[int]) -> None:
    seen = set(_read_seen_ids() or [])
    if not set(todo_ids) <= seen:
        _write_seen_ids(list(seen | set(todo_ids)))

def mark_todo_seen(todo_id: int) -> None:
    mark_todos_seen([todo_id])

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
    current_ids = {task["id"] for task in tasks}
    seen = _read_seen_ids()
    if seen is None:
        _write_seen_ids(list(current_ids))
        return []
    new_tasks = [task for task in tasks if task["id"] not in seen and not task.get("done", False)]
    new_ids = {task["id"] for task in new_tasks}
    _write_seen_ids(list((set(seen) | current_ids) - new_ids))
    return [_simplify_todo(task) for task in new_tasks]

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
