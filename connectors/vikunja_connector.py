import os
import requests

_no_due_date = "0001-01-01T00:00:00Z"

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
    response = requests.put(
        _api_url(f"/projects/{project_id or _default_project_id()}/tasks"),
        headers=_headers(),
        json=payload,
    )
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo": _simplify_todo(response.json())}

def list_todos(include_done: bool = False) -> list[dict] | dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = requests.get(
        _api_url("/tasks/all"),
        headers=_headers(),
        params={"per_page": 50, "sort_by": "due_date", "order_by": "asc"},
    )
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
    response = requests.post(
        _api_url(f"/tasks/{todo_id}"),
        headers=_headers(),
        json={"done": True},
    )
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo": _simplify_todo(response.json())}

def delete_todo(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = requests.delete(_api_url(f"/tasks/{todo_id}"), headers=_headers())
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "message": f"To-do {todo_id} deleted."}

def list_todo_projects() -> list[dict] | dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = requests.get(_api_url("/projects"), headers=_headers(), params={"per_page": 50})
    if not response.ok:
        return _request_error(response)
    projects = response.json() or []
    return [{"id": p.get("id"), "title": p.get("title")} for p in projects]
