import json
import os
import time
from datetime import datetime
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from connectors.calendar_connector import create_calendar_oauth_session, complete_calendar_oauth, calendar_enabled, list_calendar_events
from connectors.human_connector import read_human_tasks
from connectors.approval_connector import read_approvals
from connectors.coder_connector import coder_enabled, read_coding_work
from connectors.journal_connector import journal_enabled, read_journal
from connectors.usage_connector import claude_usage, buffer_threshold_percent
from connectors.buffer_connector import read_buffered
from connectors.claude_code_connector import claude_code_enabled, claude_settings

app = FastAPI()
base_dir = Path(__file__).resolve().parent
app.mount("/assets", StaticFiles(directory=base_dir / "assets"), name="assets")

incoming_queue: list[str] = []  # messages from client to bot
outgoing_queue: list[str] = []  # messages from bot to client
notification_queue: list[str] = []  # popup notifications from bot to client, outside the transcript

class MessageRequest(BaseModel):
    message: str
    
@app.get("/")
def index():
    return FileResponse(base_dir / "index.html")

# Client sends a message to the bot
@app.post("/inbox")
def client_send(body: MessageRequest):
    incoming_queue.append(body.message)
    return {"ok": True}

# Bot polls for messages sent by the client
@app.get("/inbox")
def bot_read():
    messages = list(incoming_queue)
    incoming_queue.clear()
    return {"messages": messages}

# Bot sends a response to the client
@app.post("/outbox")
def bot_send(body: MessageRequest):
    outgoing_queue.append(body.message)
    return {"ok": True}

# Client polls for bot responses
@app.get("/outbox")
def client_read():
    messages = list(outgoing_queue)
    outgoing_queue.clear()
    return {"messages": messages}

# Bot pushes a popup notification; it renders as a toast (and a browser
# notification when the tab is hidden) rather than a chat bubble
@app.post("/notify")
def bot_notify(body: MessageRequest):
    notification_queue.append(body.message)
    return {"ok": True}

# Client polls for pending popup notifications
@app.get("/notifications")
def client_notifications():
    notifications = list(notification_queue)
    notification_queue.clear()
    return {"notifications": notifications}

@app.get("/memory")
def get_memory():
    memory_path = base_dir.parent / "hood" / "memory.json"
    return json.loads(memory_path.read_text())

def _panel_calendar() -> list[dict]:
    if not calendar_enabled():
        return []
    # Anchor at local midnight so events that already ended still render (dimmed)
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    events = list_calendar_events(days_ahead=1, max_results=20, time_min=midnight)
    if not isinstance(events, list):
        return []
    now = datetime.now().astimezone()
    today = now.date()
    rows = []
    for event in events:
        try:
            start = datetime.fromisoformat(event["start"]).astimezone()
            end = datetime.fromisoformat(event["end"]).astimezone()
        except (ValueError, TypeError):
            continue
        if start.date() != today:
            continue
        rows.append({
            "time": start.strftime("%H:%M"),
            "what": event.get("summary") or "(no title)",
            "past": end < now,
        })
    return rows


def _panel_when(value: str) -> str:
    try:
        when_dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError, AttributeError):
        return ""
    if when_dt.date() == datetime.now().astimezone().date():
        return when_dt.strftime("%H:%M")
    return when_dt.strftime("%b %d %H:%M")


def _panel_approvals() -> list[dict]:
    rows = []
    for approval in read_approvals():
        summary_lines = (approval.get("summary") or "").strip().split("\n")
        rows.append({
            "kind": approval.get("label", "draft"),
            "when": _panel_when(approval.get("created_at", "")),
            "title": summary_lines[0][:80],
            "excerpt": " ".join(summary_lines[1:]).strip()[:140],
            "actions": [
                ["Send", f"/approve {approval['id']}", "primary"],
                ["Change", f"/tweak {approval['id']}", "secondary"],
                ["Drop", f"/reject {approval['id']}", "ghost"],
            ],
        })
    if coder_enabled():
        work = read_coding_work()
        vikunja_host = os.getenv("VIKUNJA_API_HOST", "").strip().rstrip("/")
        for offer in work["offers"]:
            rows.append({
                "kind": "coding agent",
                "when": _panel_when(offer.get("offered_at", "")),
                "title": offer["goal"][:80],
                "excerpt": f"Offered — runs Claude Code on this machine · {work['done_today']} of {work['max_per_day']} today",
                "link": f"{vikunja_host}/tasks/{offer['todo_id']}" if vikunja_host else "",
                "actions": [
                    ["Start", f"/aicode {offer['todo_id']}", "primary"],
                    ["Dismiss", f"/stopcode {offer['todo_id']}", "ghost"],
                ],
            })
    for task in read_human_tasks():
        rows.append({
            "kind": "question",
            "when": _panel_when(task.get("timestamp", "")),
            "title": task.get("title", ""),
            "excerpt": task.get("question", ""),
            "actions": [["Answer", f"/answer {task['id']} ", "primary"]],
        })
    return rows


def _panel_usage() -> dict | None:
    if not claude_code_enabled():
        return None
    usage = claude_usage()
    if usage.get("status") != "success":
        return None
    return {
        "mode": "subscription",
        "fiveHourPct": round(usage["five_hour_percent"]),
        "sevenDayPct": round(usage["seven_day_percent"]),
        "resets": usage["five_hour_resets_in"],
        "buffered": len(read_buffered()),
        "threshold": buffer_threshold_percent(),
    }


def _panel_plan() -> list[dict]:
    if not journal_enabled():
        return []
    journal = read_journal()
    if journal.get("status") != "success":
        return []
    # The journal records picks, not completions, so nothing renders as done yet
    return [{"text": text, "done": False} for text in journal["plan"]]


def _panel_model() -> str:
    if claude_code_enabled():
        return claude_settings()["model"]
    return os.getenv("LLM_MODEL", "unknown")


_calendar_cache: dict = {"at": 0.0, "rows": None}

@app.get("/panel")
def get_panel():
    # Only the calendar hits the Google API on every build; cache just that briefly.
    # Approvals, plan and buffer are cheap local file reads and must stay fresh
    # (usage_connector keeps its own cache for the Anthropic usage API).
    if _calendar_cache["rows"] is None or time.time() - _calendar_cache["at"] >= 25:
        _calendar_cache["rows"] = _panel_calendar()
        _calendar_cache["at"] = time.time()
    return {
        "model": _panel_model(),
        "usage": _panel_usage(),
        "plan": _panel_plan(),
        "calendar": _calendar_cache["rows"],
        "approvals": _panel_approvals(),
    }


@app.get("/commands")
def get_commands():
    commands_path = base_dir.parent / "connectors" / "commands.json"
    return json.loads(commands_path.read_text())


@app.get("/oauth/calendar/start")
def oauth_calendar_start():
        result = create_calendar_oauth_session()
        if result.get("status") == "error":
                return result
        return RedirectResponse(result["auth_url"])


@app.get("/oauth/calendar/start-info")
def oauth_calendar_start_info():
        return create_calendar_oauth_session()


@app.get("/oauth/calendar/callback")
def oauth_calendar_callback(code: str = "", state: str = "", error: str = ""):
        result = complete_calendar_oauth(code=code, state=state, error=error)
        if result.get("status") == "ok":
                return HTMLResponse(
                        """
                        <html>
                            <head><title>Calendar OAuth Complete</title></head>
                            <body style='font-family: sans-serif; padding: 24px;'>
                                <h2>Calendar connected</h2>
                                <p>Google Calendar OAuth was validated and saved.</p>
                                <p>You can go back to the chat and use calendar commands now.</p>
                            </body>
                        </html>
                        """
                )
        return HTMLResponse(
                f"""
                <html>
                    <head><title>Calendar OAuth Failed</title></head>
                    <body style='font-family: sans-serif; padding: 24px;'>
                        <h2>Calendar connection failed</h2>
                        <p>{result.get('message', 'Unknown error')}</p>
                        <p>Go back to chat and run /calendarauth again.</p>
                    </body>
                </html>
                """,
                status_code=400,
        )