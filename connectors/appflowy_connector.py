import json
import os
import requests

_token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "appflowy_token.json")
_request_timeout_seconds = 15

def appflowy_enabled() -> bool:
    return os.getenv("ENABLE_APPFLOWY", "false").lower() in ["true", "1", "yes"]

def _disabled_error() -> dict:
    return {"status": "error", "tool": "appflowy", "message": "AppFlowy tool is disabled. To enable it, set ENABLE_APPFLOWY=true and configure APPFLOWY_API_HOST, APPFLOWY_EMAIL and APPFLOWY_PASSWORD in your .env file."}

def _api_url(path: str) -> str:
    return f"{os.getenv('APPFLOWY_API_HOST', '').strip().rstrip('/')}{path}"

def _read_token_data() -> dict:
    try:
        with open(_token_path) as f:
            return json.load(f)
    except Exception:
        return {}

def _write_refresh_token(email: str, refresh_token: str) -> None:
    with open(_token_path, "w") as f:
        json.dump({"email": email, "refresh_token": refresh_token}, f)

def _access_token() -> str | dict:
    """Trades the cached refresh token for an access token, falling back to an
    email/password login when there is no cached token. AppFlowy has no long
    lived API token, so the credentials in .env are the only starting point."""
    email = os.getenv("APPFLOWY_EMAIL", "").strip()
    cached = _read_token_data()
    # Ignore a token cached for another account, otherwise changing .env has no effect
    refresh_token = cached.get("refresh_token", "") if cached.get("email") == email else ""
    if refresh_token:
        response = requests.post(_api_url("/gotrue/token?grant_type=refresh_token"), json={"refresh_token": refresh_token}, timeout=_request_timeout_seconds)
        if response.ok:
            data = response.json()
            _write_refresh_token(email, data.get("refresh_token", ""))
            return data["access_token"]
    response = requests.post(
        _api_url("/gotrue/token?grant_type=password"),
        json={"email": email, "password": os.getenv("APPFLOWY_PASSWORD", "")},
        timeout=_request_timeout_seconds,
    )
    if not response.ok:
        return {"status": "error", "tool": "appflowy", "message": "AppFlowy login failed, check APPFLOWY_EMAIL and APPFLOWY_PASSWORD.", "details": response.text}
    data = response.json()
    _write_refresh_token(email, data.get("refresh_token", ""))
    return data["access_token"]

def _request(method: str, path: str, **kwargs) -> requests.Response | dict:
    token = _access_token()
    if isinstance(token, dict):
        return token
    try:
        response = requests.request(method, _api_url(path), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=_request_timeout_seconds, **kwargs)
    except requests.RequestException as e:
        return {"status": "error", "tool": "appflowy", "message": f"AppFlowy is unreachable: {e}"}
    # AppFlowy answers 200 OK with a non-zero code in the body when a call fails
    try:
        body = response.json()
    except Exception:
        return response
    if isinstance(body, dict) and body.get("code", 0) != 0:
        return {"status": "error", "tool": "appflowy", "message": f"AppFlowy rejected the request: {body.get('message', '')}"}
    return response

def _request_error(response: requests.Response) -> dict:
    try:
        details = response.json().get("message", response.text)
    except Exception:
        details = response.text
    return {"status": "error", "tool": "appflowy", "message": f"AppFlowy API request failed with status {response.status_code}.", "details": details}

def _data(response: requests.Response):
    """AppFlowy wraps every payload in {"code": 0, "message": "ok", "data": ...}."""
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else body

def _workspace_id() -> str | dict:
    configured = os.getenv("APPFLOWY_WORKSPACE_ID", "").strip()
    if configured:
        return configured
    response = _request("get", "/api/workspace")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    workspaces = _data(response) or []
    if not workspaces:
        return {"status": "error", "tool": "appflowy", "message": "No AppFlowy workspaces found for this account."}
    return workspaces[0]["workspace_id"]

def _default_database_id() -> str:
    return os.getenv("APPFLOWY_DEFAULT_DATABASE_ID", "").strip()

def _field_map(workspace_id: str, database_id: str) -> dict | list:
    """Maps field ids to human names and back, so the tools can speak field
    names like 'Title' while the API only understands field uuids."""
    response = _request("get", f"/api/workspace/{workspace_id}/database/{database_id}/fields")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return [{"id": field.get("id"), "name": field.get("name"), "type": field.get("field_type")} for field in _data(response) or []]

def _simplify_row(row: dict) -> dict:
    # AppFlowy already returns cells keyed by field name, so no field map is needed here
    return {
        "id": row.get("id"),
        "fields": row.get("cells") or {},
        "has_doc": row.get("has_doc", False),
    }

def _simplify_page(view: dict) -> dict:
    return {
        "view_id": view.get("view_id"),
        "name": view.get("name"),
        "is_space": view.get("is_space", False),
        "children": [_simplify_page(child) for child in view.get("children") or []],
    }

def list_appflowy_databases() -> list[dict] | dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    response = _request("get", f"/api/workspace/{workspace_id}/database")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    databases = _data(response) or []
    return [{"id": db.get("id"), "views": [{"view_id": v.get("view_id"), "name": v.get("name")} for v in db.get("views") or []]} for db in databases]

def list_appflowy_rows(database_id: str = "", limit: int = 25) -> list[dict] | dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    database_id = database_id or _default_database_id()
    if not database_id:
        return {"status": "error", "tool": "appflowy", "message": "No database given and APPFLOWY_DEFAULT_DATABASE_ID is not set. Use list_appflowy_databases to find one."}
    ids_response = _request("get", f"/api/workspace/{workspace_id}/database/{database_id}/row")
    if isinstance(ids_response, dict):
        return ids_response
    if not ids_response.ok:
        return _request_error(ids_response)
    row_ids = [row.get("id") for row in _data(ids_response) or []][:limit]
    if not row_ids:
        return []
    detail_response = _request("get", f"/api/workspace/{workspace_id}/database/{database_id}/row/detail", params={"ids": ",".join(row_ids)})
    if isinstance(detail_response, dict):
        return detail_response
    if not detail_response.ok:
        return _request_error(detail_response)
    return [_simplify_row(row) for row in _data(detail_response) or []]

def add_appflowy_row(fields: dict, database_id: str = "") -> dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    database_id = database_id or _default_database_id()
    if not database_id:
        return {"status": "error", "tool": "appflowy", "message": "No database given and APPFLOWY_DEFAULT_DATABASE_ID is not set. Use list_appflowy_databases to find one."}
    field_list = _field_map(workspace_id, database_id)
    if isinstance(field_list, dict):
        return field_list
    ids = {field["name"]: field["id"] for field in field_list}
    unknown = [name for name in fields if name not in ids]
    if unknown:
        return {"status": "error", "tool": "appflowy", "message": f"Unknown field names {unknown}. This database has: {sorted(ids)}."}
    response = _request("post", f"/api/workspace/{workspace_id}/database/{database_id}/row", json={"cells": {ids[name]: value for name, value in fields.items()}})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "row_id": _data(response)}

def update_appflowy_row(row_key: str, fields: dict, database_id: str = "") -> dict:
    """AppFlowy has no update-by-row-id, only an upsert keyed by a pre hash, so
    this can only change rows created through this same key."""
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    database_id = database_id or _default_database_id()
    if not database_id:
        return {"status": "error", "tool": "appflowy", "message": "No database given and APPFLOWY_DEFAULT_DATABASE_ID is not set. Use list_appflowy_databases to find one."}
    field_list = _field_map(workspace_id, database_id)
    if isinstance(field_list, dict):
        return field_list
    ids = {field["name"]: field["id"] for field in field_list}
    unknown = [name for name in fields if name not in ids]
    if unknown:
        return {"status": "error", "tool": "appflowy", "message": f"Unknown field names {unknown}. This database has: {sorted(ids)}."}
    response = _request("put", f"/api/workspace/{workspace_id}/database/{database_id}/row", json={"pre_hash": row_key, "cells": {ids[name]: value for name, value in fields.items()}})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "row_id": _data(response)}

def list_appflowy_pages() -> dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    response = _request("get", f"/api/workspace/{workspace_id}/folder", params={"depth": 4})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "pages": _simplify_page(_data(response) or {})}

def _block_text(block: dict, text_map: dict) -> str:
    raw = text_map.get(block.get("external_id") or "", "")
    if not raw:
        return ""
    try:
        delta = json.loads(raw)
    except Exception:
        return raw
    if isinstance(delta, list):
        return "".join(op.get("insert", "") for op in delta if isinstance(op, dict))
    return raw

def _block_prefix(block_type: str, data: dict) -> str:
    if block_type == "heading":
        return "#" * int(data.get("level", 1)) + " "
    if block_type == "todo_list":
        return "- [x] " if data.get("checked") else "- [ ] "
    if block_type == "bulleted_list":
        return "- "
    if block_type == "numbered_list":
        return "1. "
    if block_type == "quote":
        return "> "
    return ""

def _render_document(document: dict) -> str:
    """Walks the block tree AppFlowy returns and renders it as markdown-ish text.
    Blocks hold their text in meta.text_map keyed by external_id, and their order
    in meta.children_map keyed by the block's children id."""
    blocks = document.get("blocks") or {}
    meta = document.get("meta") or {}
    children_map = meta.get("children_map") or {}
    text_map = meta.get("text_map") or {}
    lines = []

    def walk(block_id: str, depth: int) -> None:
        block = blocks.get(block_id) or {}
        block_type = block.get("ty", "")
        try:
            data = json.loads(block.get("data") or "{}")
        except Exception:
            data = {}
        if block_type == "divider":
            lines.append("---")
        elif block_type != "page":
            text = _block_text(block, text_map)
            if text:
                lines.append("  " * max(depth - 1, 0) + _block_prefix(block_type, data) + text)
        for child_id in children_map.get(block.get("children") or "", []):
            walk(child_id, depth + 1)

    walk(document.get("page_id") or "", 0)
    return "\n".join(lines)

def read_appflowy_page(view_id: str) -> dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    response = _request("get", f"/api/workspace/v1/{workspace_id}/collab/{view_id}/json", params={"collab_type": 0})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    document = ((_data(response) or {}).get("collab") or {}).get("document") or {}
    return {"status": "success", "view_id": view_id, "text": _render_document(document)}

def delete_appflowy_page(view_id: str) -> dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    response = _request("post", f"/api/workspace/{workspace_id}/page-view/{view_id}/move-to-trash")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "message": f"Page {view_id} moved to trash."}

def add_appflowy_page(title: str, parent_view_id: str) -> dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    # layout 0 is a document page, the only kind this tool creates
    response = _request("post", f"/api/workspace/{workspace_id}/page-view", json={"parent_view_id": parent_view_id, "layout": 0, "name": title})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "page": _data(response)}

def append_appflowy_text(view_id: str, text: str) -> dict:
    if not appflowy_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    blocks = [{"type": "paragraph", "data": {"delta": [{"insert": line}]}} for line in text.split("\n")]
    response = _request("post", f"/api/workspace/{workspace_id}/page-view/{view_id}/append-block", json={"blocks": blocks})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "message": f"Appended {len(blocks)} block(s) to page {view_id}."}
