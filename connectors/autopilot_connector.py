import json
import os
from datetime import datetime, timezone

AUTOPILOT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "autopilot.json")

# A job that keeps blowing up must not wedge the queue behind it, matching the
# "if you tried and failed 3 different times, abort" rule in SYSTEM_PROMPT.md
MAX_ATTEMPTS = 3


def autopilot_enabled() -> bool:
    return os.getenv("ENABLE_AUTOPILOT", "false").lower() in ["true", "1", "yes"]


def max_per_day() -> int:
    return int(os.getenv("AUTOPILOT_MAX_PER_DAY", "5"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_state() -> dict:
    try:
        with open(AUTOPILOT_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    with open(AUTOPILOT_PATH, "w") as f:
        json.dump(state, f, indent=4)


def _roll_day(state: dict) -> dict:
    if state.get("day") != _today():
        state["day"] = _today()
        state["done_today"] = 0
    return state


def queue_work(todo_id: int, goal: str) -> dict:
    """Records that the agent thinks it can move this to-do forward on its own. The
    heartbeat drains the queue later, so the acknowledgement the user is waiting on
    is never held up behind a slow web search."""
    if not autopilot_enabled():
        return {"status": "error", "tool": "autopilot", "message": "Autopilot is disabled. To enable it, set ENABLE_AUTOPILOT=true in your .env file."}
    state = _read_state()
    queue = state.get("queue", [])
    if any(job["todo_id"] == todo_id for job in queue):
        return {"status": "success", "message": f"To-do {todo_id} is already queued, nothing to do."}
    state["next_id"] = state.get("next_id", 0) + 1
    queue.append({
        "id": state["next_id"],
        "todo_id": todo_id,
        "goal": goal,
        "queued_at": _now(),
        "attempts": 0,
    })
    state["queue"] = queue
    _write_state(state)
    return {"status": "success", "message": f"Queued to work on to-do {todo_id} shortly.", "queued": len(queue)}


def read_queue() -> list[dict]:
    return _read_state().get("queue", [])


def next_job() -> dict | None:
    """The next job to run, or None when disabled, empty, or the daily cap is spent.
    The cap protects both the Claude usage window and the user's attention."""
    if not autopilot_enabled():
        return None
    state = _roll_day(_read_state())
    _write_state(state)
    if state.get("done_today", 0) >= max_per_day():
        return None
    queue = state.get("queue", [])
    return queue[0] if queue else None


def finish_job(job_id: int) -> None:
    state = _roll_day(_read_state())
    state["queue"] = [job for job in state.get("queue", []) if job["id"] != job_id]
    state["done_today"] = state.get("done_today", 0) + 1
    _write_state(state)


def fail_job(job_id: int) -> bool:
    """Counts a failed attempt. Returns True when the job was dropped for good, so
    the caller can say so instead of the user waiting forever on silent retries."""
    state = _read_state()
    queue = state.get("queue", [])
    dropped = False
    for job in queue:
        if job["id"] == job_id:
            job["attempts"] = job.get("attempts", 0) + 1
            dropped = job["attempts"] >= MAX_ATTEMPTS
    if dropped:
        queue = [job for job in queue if job["id"] != job_id]
    state["queue"] = queue
    _write_state(state)
    return dropped


def remaining_today() -> int:
    state = _roll_day(_read_state())
    return max(0, max_per_day() - state.get("done_today", 0))
