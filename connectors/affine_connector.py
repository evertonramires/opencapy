import base64
import json
import os
import time
import uuid
import requests
import socketio
from pycrdt import Array, Doc, Map, Text

_session_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "affine_session.json")
_request_timeout_seconds = 15

def affine_enabled() -> bool:
    return os.getenv("ENABLE_AFFINE", "false").lower() in ["true", "1", "yes"]

def _disabled_error() -> dict:
    return {"status": "error", "tool": "affine", "message": "AFFiNE tool is disabled. To enable it, set ENABLE_AFFINE=true and configure AFFINE_API_HOST, AFFINE_EMAIL and AFFINE_PASSWORD in your .env file."}

def _api_url(path: str) -> str:
    return f"{os.getenv('AFFINE_API_HOST', '').strip().rstrip('/')}{path}"

def _read_session() -> dict:
    try:
        with open(_session_path) as f:
            return json.load(f)
    except Exception:
        return {}

def _write_session(email: str, cookie: str) -> None:
    with open(_session_path, "w") as f:
        json.dump({"email": email, "cookie": cookie}, f)

def _session_cookie() -> str | dict:
    """AFFiNE has no API token, so the credentials in .env are the only starting
    point, and the session cookie they return is cached like AppFlowy's refresh token."""
    email = os.getenv("AFFINE_EMAIL", "").strip()
    cached = _read_session()
    # Ignore a session cached for another account, otherwise changing .env has no effect
    cookie = cached.get("cookie", "") if cached.get("email") == email else ""
    if cookie:
        response = requests.get(_api_url("/api/auth/session"), headers={"Cookie": cookie}, timeout=_request_timeout_seconds)
        if response.ok and response.json().get("user"):
            return cookie
    response = requests.post(
        _api_url("/api/auth/sign-in"),
        json={"email": email, "password": os.getenv("AFFINE_PASSWORD", "")},
        timeout=_request_timeout_seconds,
    )
    if not response.ok:
        return {"status": "error", "tool": "affine", "message": "AFFiNE login failed, check AFFINE_EMAIL and AFFINE_PASSWORD.", "details": response.text}
    cookie = "; ".join(f"{name}={value}" for name, value in response.cookies.items())
    _write_session(email, cookie)
    return cookie

def _graphql(query: str, variables: dict = {}) -> dict:
    cookie = _session_cookie()
    if isinstance(cookie, dict):
        return cookie
    try:
        response = requests.post(
            _api_url("/graphql"),
            json={"query": query, "variables": variables},
            headers={"Cookie": cookie, "Content-Type": "application/json"},
            timeout=_request_timeout_seconds,
        )
    except requests.RequestException as e:
        return {"status": "error", "tool": "affine", "message": f"AFFiNE is unreachable: {e}"}
    body = response.json()
    # GraphQL answers 200 with an errors array instead of an error status
    if body.get("errors"):
        return {"status": "error", "tool": "affine", "message": f"AFFiNE rejected the request: {body['errors'][0]['message']}"}
    return body["data"]

def _workspace_id() -> str | dict:
    configured = os.getenv("AFFINE_WORKSPACE_ID", "").strip()
    if configured:
        return configured
    data = _graphql("{ workspaces { id } }")
    if data.get("status") == "error":
        return data
    workspaces = data["workspaces"]
    if not workspaces:
        return {"status": "error", "tool": "affine", "message": "No AFFiNE workspaces found for this account."}
    return workspaces[0]["id"]

def _client() -> "socketio.Client | dict":
    """AFFiNE has no API for doc content: pages are YJS documents synced over a
    socket.io channel, so reading and writing both go through this connection."""
    cookie = _session_cookie()
    if isinstance(cookie, dict):
        return cookie
    client = socketio.Client()
    try:
        client.connect(_api_url(""), headers={"Cookie": cookie}, socketio_path="/socket.io", transports=["websocket"], wait_timeout=_request_timeout_seconds)
    except Exception as e:
        return {"status": "error", "tool": "affine", "message": f"AFFiNE sync is unreachable: {e}"}
    return client

def _join(client, workspace_id: str) -> dict:
    # The server rejects the channel when the client version is too far from its own
    answer = client.call("space:join", {"spaceType": "workspace", "spaceId": workspace_id, "clientVersion": os.getenv("AFFINE_CLIENT_VERSION", "0.27.3")}, timeout=_request_timeout_seconds)
    if "error" in answer:
        return {"status": "error", "tool": "affine", "message": f"AFFiNE refused the sync channel: {answer['error'].get('message', '')}"}
    return {}

def _load_doc(client, workspace_id: str, doc_id: str) -> "Doc | dict":
    answer = client.call("space:load-doc", {"spaceType": "workspace", "spaceId": workspace_id, "docId": doc_id}, timeout=_request_timeout_seconds)
    if "error" in answer:
        return {"status": "error", "tool": "affine", "message": f"AFFiNE has no doc {doc_id}: {answer['error'].get('message', '')}"}
    doc = Doc()
    doc.apply_update(base64.b64decode(answer["data"]["missing"]))
    return doc

def _push_doc(client, workspace_id: str, doc_id: str, update: bytes) -> dict:
    answer = client.call("space:push-doc-update", {"spaceType": "workspace", "spaceId": workspace_id, "docId": doc_id, "update": base64.b64encode(update).decode()}, timeout=_request_timeout_seconds)
    if "error" in answer:
        return {"status": "error", "tool": "affine", "message": f"AFFiNE rejected the change: {answer['error'].get('message', '')}"}
    return {}

def _paragraph(text: str) -> tuple[str, Map]:
    """One AFFiNE paragraph block. Markdown prefixes are mapped to the block type
    AFFiNE uses natively, so headings and lists stay real blocks instead of literal text."""
    block_id = str(uuid.uuid4())
    flavour, block_type = "affine:paragraph", "text"
    for prefix, name in [("###### ", "h6"), ("##### ", "h5"), ("#### ", "h4"), ("### ", "h3"), ("## ", "h2"), ("# ", "h1"), ("> ", "quote")]:
        if text.startswith(prefix):
            text, block_type = text[len(prefix):], name
            break
    else:
        for prefix in ["- ", "* ", "+ "]:
            if text.startswith(prefix):
                text, flavour, block_type = text[len(prefix):], "affine:list", "bulleted"
                break
    return block_id, Map({"sys:id": block_id, "sys:flavour": flavour, "sys:version": 1, "sys:children": Array([]), "prop:type": block_type, "prop:text": Text(text)})

def _render_doc(blocks: Map) -> str:
    """Walks the block tree from the page block. Map order is insertion order, not
    document order, so the children lists are the only reliable way to read a page."""
    prefixes = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### ", "quote": "> ", "bulleted": "- ", "numbered": "1. ", "todo": "- [ ] "}
    lines = []

    def walk(block_id: str) -> None:
        block = dict(blocks[block_id])
        flavour = block.get("sys:flavour", "")
        if flavour == "affine:divider":
            lines.append("---")
        elif flavour == "affine:code":
            lines.append(f"```{block.get('prop:language') or ''}\n{block.get('prop:text', '')}\n```")
        elif "prop:text" in block and flavour != "affine:page":
            lines.append(prefixes.get(block.get("prop:type", ""), "") + str(block["prop:text"]))
        for child_id in block.get("sys:children", []):
            if child_id in blocks:
                walk(child_id)

    page_id = next((bid for bid, b in blocks.items() if dict(b).get("sys:flavour") == "affine:page"), "")
    if page_id:
        walk(page_id)
    return "\n".join(lines)

def list_affine_docs() -> list[dict] | dict:
    if not affine_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    client = _client()
    if isinstance(client, dict):
        return client
    try:
        error = _join(client, workspace_id)
        if error:
            return error
        # The doc list lives in the workspace's own root doc, GraphQL only knows the ids
        root = _load_doc(client, workspace_id, workspace_id)
        if isinstance(root, dict):
            return root
        pages = root.get("meta", type=Map)["pages"]
        return [{"doc_id": page["id"], "title": page.get("title", ""), "created_at": page.get("createDate", 0)} for page in [dict(p) for p in pages]]
    finally:
        client.disconnect()

def search_affine_docs(keyword: str, limit: int = 10) -> list[dict] | dict:
    if not affine_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    query = "query($id: String!, $keyword: String!, $limit: Int!) { workspace(id: $id) { searchDocs(input: {keyword: $keyword, limit: $limit}) { docId title highlight updatedAt } } }"
    data = _graphql(query, {"id": workspace_id, "keyword": keyword, "limit": limit})
    if data.get("status") == "error":
        return data
    return data["workspace"]["searchDocs"]

def read_affine_doc(doc_id: str) -> dict:
    if not affine_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    client = _client()
    if isinstance(client, dict):
        return client
    try:
        error = _join(client, workspace_id)
        if error:
            return error
        doc = _load_doc(client, workspace_id, doc_id)
        if isinstance(doc, dict):
            return doc
        blocks = doc.get("blocks", type=Map)
        title = next((str(dict(b)["prop:title"]) for b in blocks.values() if dict(b).get("sys:flavour") == "affine:page"), "")
        return {"status": "success", "doc_id": doc_id, "title": title, "content": _render_doc(blocks)}
    finally:
        client.disconnect()

def add_affine_doc(title: str, content: str = "") -> dict:
    if not affine_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    client = _client()
    if isinstance(client, dict):
        return client
    try:
        error = _join(client, workspace_id)
        if error:
            return error
        doc_id, page_id, note_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        page = Doc()
        blocks = Map()
        page["blocks"] = blocks
        children = Array()
        blocks[page_id] = Map({"sys:id": page_id, "sys:flavour": "affine:page", "sys:version": 2, "sys:children": Array([note_id]), "prop:title": Text(title)})
        blocks[note_id] = Map({"sys:id": note_id, "sys:flavour": "affine:note", "sys:version": 1, "sys:children": children,
                               "prop:xywh": "[0,0,800,95]", "prop:background": "--affine-note-background-blue",
                               "prop:index": "a0", "prop:hidden": False, "prop:displayMode": "both"})
        for line in content.split("\n"):
            block_id, block = _paragraph(line)
            blocks[block_id] = block
            children.append(block_id)
        error = _push_doc(client, workspace_id, doc_id, page.get_update())
        if error:
            return error
        # A page only shows up in AFFiNE once it is registered in the workspace root doc
        root = _load_doc(client, workspace_id, workspace_id)
        if isinstance(root, dict):
            return root
        before = root.get_state()
        root.get("meta", type=Map)["pages"].append(Map({"id": doc_id, "title": title, "createDate": int(time.time() * 1000), "tags": Array()}))
        error = _push_doc(client, workspace_id, workspace_id, root.get_update(before))
        if error:
            return error
        return {"status": "success", "doc_id": doc_id, "title": title}
    finally:
        client.disconnect()

def append_affine_text(doc_id: str, text: str) -> dict:
    if not affine_enabled():
        return _disabled_error()
    workspace_id = _workspace_id()
    if isinstance(workspace_id, dict):
        return workspace_id
    client = _client()
    if isinstance(client, dict):
        return client
    try:
        error = _join(client, workspace_id)
        if error:
            return error
        doc = _load_doc(client, workspace_id, doc_id)
        if isinstance(doc, dict):
            return doc
        blocks = doc.get("blocks", type=Map)
        note_id = next((bid for bid, b in blocks.items() if dict(b).get("sys:flavour") == "affine:note"), "")
        if not note_id:
            return {"status": "error", "tool": "affine", "message": f"Doc {doc_id} has no note block to append to."}
        before = doc.get_state()
        children = dict(blocks[note_id])["sys:children"]
        for line in text.split("\n"):
            block_id, block = _paragraph(line)
            blocks[block_id] = block
            children.append(block_id)
        error = _push_doc(client, workspace_id, doc_id, doc.get_update(before))
        if error:
            return error
        return {"status": "success", "doc_id": doc_id, "appended": text}
    finally:
        client.disconnect()
