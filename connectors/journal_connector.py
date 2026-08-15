import json
import os
from datetime import datetime, timedelta, timezone

JOURNAL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "journal.json")


def journal_enabled() -> bool:
    return os.getenv("ENABLE_JOURNAL", "false").lower() in ["true", "1", "yes"]


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _tomorrow() -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


def _read_state() -> dict:
    try:
        with open(JOURNAL_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    with open(JOURNAL_PATH, "w") as f:
        json.dump(state, f, indent=4)


def _day(state: dict, date_iso: str) -> dict:
    return state.setdefault("days", {}).setdefault(date_iso, {})


def set_plan(date_iso: str, tasks: list[str], source: str) -> dict:
    """The first three things for a day. A user answer always wins over a Capy pick:
    the fallback exists so a morning never starts empty, not to overrule anyone."""
    if not journal_enabled():
        return {"status": "error", "tool": "journal", "message": "The journal is disabled. To enable it, set ENABLE_JOURNAL=true in your .env file."}
    tasks = [task.strip() for task in tasks if task.strip()][:3]
    if not tasks:
        return {"status": "error", "tool": "journal", "message": "No tasks given, nothing recorded."}
    state = _read_state()
    day = _day(state, date_iso)
    if source == "capy" and day.get("plan_source") == "user":
        return {"status": "success", "message": "The user already chose their plan for that day, keeping theirs.", "plan": day["plan"]}
    day["plan"] = tasks
    day["plan_source"] = source
    _write_state(state)
    if source == "capy":
        # Only a Capy pick names its model; the user's own choices are their own
        from connectors.llm_connector import authoring_model
        model = authoring_model()
        heading = f"Plan (chosen by Capy · {model}):" if model else "Plan (chosen by Capy):"
    else:
        heading = "Plan (chosen by the user):"
    _sync_appflowy(date_iso, [heading] + [f"• {task}" for task in tasks])
    return {"status": "success", "date": date_iso, "plan": tasks, "source": source}


def add_wins(date_iso: str, wins: list[str]) -> dict:
    """What actually got done, in the user's own words. Appended rather than replaced,
    so an evening answered in two messages still ends up whole."""
    if not journal_enabled():
        return {"status": "error", "tool": "journal", "message": "The journal is disabled. To enable it, set ENABLE_JOURNAL=true in your .env file."}
    wins = [win.strip() for win in wins if win.strip()]
    if not wins:
        return {"status": "error", "tool": "journal", "message": "No wins given, nothing recorded."}
    state = _read_state()
    day = _day(state, date_iso)
    day["wins"] = (day.get("wins") or []) + wins
    _write_state(state)
    _sync_appflowy(date_iso, ["Achieved:"] + [f"• {win}" for win in wins])
    return {"status": "success", "date": date_iso, "wins": day["wins"]}


def get_plan(date_iso: str) -> dict:
    day = (_read_state().get("days") or {}).get(date_iso) or {}
    return {"plan": day.get("plan") or [], "source": day.get("plan_source") or ""}


def read_journal(date_iso: str = "") -> dict:
    if not journal_enabled():
        return {"status": "error", "tool": "journal", "message": "The journal is disabled. To enable it, set ENABLE_JOURNAL=true in your .env file."}
    date_iso = date_iso or _today()
    day = (_read_state().get("days") or {}).get(date_iso) or {}
    return {"status": "success", "date": date_iso, "plan": day.get("plan") or [], "plan_source": day.get("plan_source") or "", "wins": day.get("wins") or []}


def evening_journal_due() -> dict | bool:
    """Once a day at JOURNAL_EVENING_HOUR (UTC, -1 disables), returns what the evening
    ask needs: today's plan to close the loop on, and the date keys to record against.
    Same gate shape as every other daily moment — at or after the hour, once, and the
    caller marks only after a successful send so failures retry."""
    evening_hour = int(os.getenv("JOURNAL_EVENING_HOUR", "-1"))
    if not journal_enabled() or evening_hour < 0:
        return False
    now = datetime.now(timezone.utc)
    if now.hour < evening_hour:
        return False
    if _read_state().get("last_evening_date") == now.date().isoformat():
        return False
    return {"today": _today(), "tomorrow": _tomorrow(), "todays_plan": get_plan(_today())["plan"]}


def mark_evening_sent() -> None:
    state = _read_state()
    state["last_evening_date"] = _today()
    _write_state(state)


def _sync_appflowy(date_iso: str, lines: list[str]) -> None:
    """Mirrors the entry into AppFlowy, one page per day under a Journal parent.
    Best effort by design: the journal's source of truth is the state file, and a
    knowledge base being down should never cost the user their evening answer."""
    try:
        from connectors.appflowy_connector import appflowy_enabled, list_appflowy_pages, add_appflowy_page, append_appflowy_text
        if not appflowy_enabled():
            return
        parent_id = os.getenv("APPFLOWY_JOURNAL_PARENT_ID", "").strip()
        found = list_appflowy_pages()
        if found.get("status") != "success":
            return
        pages = found.get("pages") or []

        def _walk(nodes):
            for node in nodes:
                yield node
                yield from _walk(node.get("children") or [])

        everything = list(_walk(pages))
        if not parent_id:
            journal = next((page for page in everything if (page.get("name") or "").strip().lower() == "journal"), None)
            if journal:
                parent_id = journal["view_id"]
            else:
                # A page needs a parent, and the first space is the closest thing
                # AppFlowy has to a root
                space = next((page for page in everything if page.get("is_space")), None)
                if not space:
                    return
                created = add_appflowy_page("Journal", space["view_id"])
                if created.get("status") != "success":
                    return
                parent_id = created.get("view_id") or created.get("page", {}).get("view_id", "")
                if not parent_id:
                    return
        day_page = next((page for page in everything if (page.get("name") or "").strip() == date_iso), None)
        if day_page:
            day_id = day_page["view_id"]
        else:
            created = add_appflowy_page(date_iso, parent_id)
            if created.get("status") != "success":
                return
            day_id = created.get("view_id") or created.get("page", {}).get("view_id", "")
            if not day_id:
                return
        append_appflowy_text(day_id, "\n".join(lines))
    except Exception as e:
        print(f"⚠️ Journal AppFlowy sync failed: {e}")
