import json
import os
from datetime import datetime, timedelta, timezone

SPRINTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "sprints.json")


def sprints_enabled() -> bool:
    return os.getenv("ENABLE_SPRINTS", "false").lower() in ["true", "1", "yes"]


def default_minutes() -> int:
    return int(os.getenv("SPRINT_MINUTES", "25"))


def _now():
    return datetime.now(timezone.utc)


def _stamp(moment) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _read() -> list[dict]:
    try:
        with open(SPRINTS_PATH) as f:
            return json.load(f)["sprints"]
    except Exception:
        return []


def _write(sprints: list[dict]) -> None:
    with open(SPRINTS_PATH, "w") as f:
        json.dump({"sprints": sprints}, f, indent=4)


def read_sprints() -> list[dict]:
    return _read()


def get_sprint(sprint_id: int) -> dict | None:
    return next((item for item in _read() if item["id"] == sprint_id), None)


def start_sprint(todo_id: int, title: str, minutes: int = 0) -> dict:
    """One sprint at a time on purpose: the whole value is having exactly one thing
    to look at, and a second running timer rebuilds the choice it removes."""
    minutes = minutes or default_minutes()
    sprints = _read()
    running = [item for item in sprints if not item.get("ended")]
    sprint_id = max([item["id"] for item in sprints], default=0) + 1
    # Superseded sprints are dropped rather than flagged, otherwise nothing ever
    # prunes them and due_sprints keeps walking a growing list of dead timers
    sprints = []
    sprints.append({
        "id": sprint_id,
        "todo_id": todo_id,
        "title": title,
        "started_at": _stamp(_now()),
        "ends_at": _stamp(_now() + timedelta(minutes=minutes)),
        "minutes": minutes,
        "extensions": 0,
        "ended": False,
        "checked_in": False,
    })
    _write(sprints)
    return {"status": "success", "sprint_id": sprint_id, "minutes": minutes, "replaced": len(running)}


def due_sprints() -> list[dict]:
    """Sprints whose time is up and that haven't been asked about yet. The caller
    must mark_checked_in after sending, so a failed send is retried."""
    if not sprints_enabled():
        return []
    now = _now()
    due = []
    for sprint in _read():
        if sprint.get("ended") or sprint.get("checked_in"):
            continue
        ends_at = _parse(sprint["ends_at"])
        if ends_at and now >= ends_at:
            due.append(sprint)
    return due


def mark_checked_in(sprint_id: int) -> None:
    sprints = _read()
    for sprint in sprints:
        if sprint["id"] == sprint_id:
            sprint["checked_in"] = True
    _write(sprints)


def extend_sprint(sprint_id: int, minutes: int = 10) -> dict | None:
    sprints = _read()
    target = None
    for sprint in sprints:
        if sprint["id"] == sprint_id:
            sprint["ends_at"] = _stamp(_now() + timedelta(minutes=minutes))
            sprint["extensions"] = sprint.get("extensions", 0) + 1
            sprint["checked_in"] = False
            sprint["ended"] = False
            target = sprint
    _write(sprints)
    return target


def end_sprint(sprint_id: int) -> dict | None:
    # A finished sprint is not history worth keeping, and leaving them would grow the
    # file forever, so it is dropped outright
    sprints = _read()
    target = next((item for item in sprints if item["id"] == sprint_id), None)
    _write([item for item in sprints if item["id"] != sprint_id])
    return target
