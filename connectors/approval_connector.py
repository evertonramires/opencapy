import functools
import inspect
import json
import os
from datetime import datetime, timezone

APPROVALS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "approvals.json")

# Outward facing and irreversible: once it reaches another human there is no undo.
# APPROVAL_REQUIRED_TOOLS overrides this, so putting run_shell_command or browse_url
# behind the gate later is a config edit rather than a code change.
DEFAULT_GATED_TOOLS = {"send_email", "send_sms"}


def gated_tools() -> set[str]:
    raw = os.getenv("APPROVAL_REQUIRED_TOOLS", "").strip()
    if not raw:
        return set(DEFAULT_GATED_TOOLS)
    if raw.lower() in ["none", "off", "false"]:
        return set()
    return {name.strip() for name in raw.split(",") if name.strip()}


def _expiry_hours() -> int:
    return int(os.getenv("APPROVAL_EXPIRY_HOURS", "24"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read() -> list[dict]:
    try:
        with open(APPROVALS_PATH) as f:
            return json.load(f)["approvals"]
    except Exception:
        return []


def _write(approvals: list[dict]) -> None:
    with open(APPROVALS_PATH, "w") as f:
        json.dump({"approvals": approvals}, f, indent=4)


def read_approvals() -> list[dict]:
    return _read()


def get_approval(approval_id: int) -> dict | None:
    return next((item for item in _read() if item["id"] == approval_id), None)


def delete_approval(approval_id: int) -> None:
    _write([item for item in _read() if item["id"] != approval_id])


def _update_approval(approval_id: int, **fields) -> None:
    approvals = _read()
    for item in approvals:
        if item["id"] == approval_id:
            item.update(fields)
    _write(approvals)


def requires_approval(label: str, summary):
    """Parks the call and asks the user instead of running it, for every tool named
    in gated_tools(). Both LLM paths dispatch through the functions in tools/, so
    wrapping there covers the OpenAI style tool loop and the Claude Code MCP bridge
    alike and leaves the model no way around it."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if func.__name__ not in gated_tools():
                return func(*args, **kwargs)
            # Normalised so the stored record can always be replayed with **args,
            # however the model happened to pass them
            call_args = inspect.getcallargs(func, *args, **kwargs)
            return _park(func.__name__, label, summary(**call_args), call_args)
        # Approving has to reach the real action rather than the gate again
        wrapper._undecorated = func
        return wrapper
    return decorator


def _park(tool: str, label: str, summary: str, call_args: dict) -> dict:
    from connectors.chat_connector import send_message
    approvals = _read()
    approval_id = max([item["id"] for item in approvals], default=0) + 1
    message_id = send_message(
        f"🤝 Ready to send this {label}. Want me to go ahead?\n\n{summary}",
        buttons=[
            [("✅ Send", f"/approve {approval_id}"), ("✏️ Change", f"/tweak {approval_id}")],
            [("❌ Drop", f"/reject {approval_id}")],
        ],
    )
    approvals.append({
        "id": approval_id,
        "tool": tool,
        "label": label,
        "summary": summary,
        "args": call_args,
        "created_at": _now(),
        "message_id": message_id,
        "awaiting_tweak": False,
    })
    _write(approvals)
    return {
        "status": "awaiting_approval",
        "approval_id": approval_id,
        "message": (
            f"Parked for the user to approve, nothing was sent. Tell them you are waiting on their OK "
            f"and do not claim the {label} went out. They can tap the buttons or reply /approve {approval_id}."
        ),
    }


def execute_approval(approval_id: int) -> dict:
    """Runs exactly the call that was shown to the user. No LLM in between on
    purpose: a re-draft between approving and sending would mean the thing that
    goes out is not the thing that was approved."""
    approval = get_approval(approval_id)
    if not approval:
        return {"status": "error", "message": f"Approval {approval_id} not found."}
    from connectors.llm_connector import _load_tools_from_disk
    _, handlers = _load_tools_from_disk()
    handler = handlers.get(approval["tool"])
    if handler is None:
        return {"status": "error", "message": f"The {approval['tool']} tool is not available anymore."}
    try:
        result = getattr(handler, "_undecorated", handler)(**approval["args"])
    except Exception as e:
        return {"status": "error", "message": f"Sending failed: {e}"}
    # Kept on failure so the draft is still there to retry rather than lost
    if isinstance(result, dict) and result.get("status") == "error":
        return {"status": "error", "message": result.get("message", "The tool reported an error.")}
    delete_approval(approval_id)
    return {"status": "success", "tool": approval["tool"], "label": approval["label"], "result": result}


def set_awaiting_tweak(approval_id: int) -> None:
    _update_approval(approval_id, awaiting_tweak=True, awaiting_tweak_at=_now())


def pending_tweak() -> dict | None:
    """The approval whose Change button was tapped, so the next thing the user types
    or dictates is read as the correction instead of as a new request. It lapses after
    a few minutes: tapping Change and then wandering off must not turn an unrelated
    message an hour later into an edit of a forgotten draft."""
    window = int(os.getenv("APPROVAL_TWEAK_WINDOW_MINUTES", "15")) * 60
    now = datetime.now(timezone.utc)
    for item in _read():
        if not item.get("awaiting_tweak"):
            continue
        try:
            age = (now - datetime.strptime(item["awaiting_tweak_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds()
        except Exception:
            age = 0
        if age <= window:
            return item
        _update_approval(item["id"], awaiting_tweak=False)
    return None


def expired_approvals() -> list[dict]:
    """Drops approvals older than the expiry window and returns them, so something
    approved days later never fires quietly on stale intent."""
    approvals = _read()
    cutoff = _expiry_hours() * 3600
    now = datetime.now(timezone.utc)
    expired = []
    kept = []
    for item in approvals:
        try:
            age = (now - datetime.strptime(item["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds()
        except Exception:
            age = 0
        (expired if age > cutoff else kept).append(item)
    if expired:
        _write(kept)
    return expired
