import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from connectors.calendar_connector import create_calendar_oauth_session, complete_calendar_oauth, calendar_enabled, list_calendar_events
from connectors.taskbook_connector import read_tasks
from connectors.human_connector import read_human_tasks

app = FastAPI()
base_dir = Path(__file__).resolve().parent
app.mount("/assets", StaticFiles(directory=base_dir / "assets"), name="assets")

incoming_queue: list[str] = []  # messages from client to bot
outgoing_queue: list[str] = []  # messages from bot to client

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


def _panel_approvals() -> list[dict]:
    approvals = []
    for task in read_human_tasks():
        try:
            when_dt = datetime.strptime(task["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
            when = when_dt.strftime("%H:%M") if when_dt.date() == datetime.now().astimezone().date() else when_dt.strftime("%b %d %H:%M")
        except (ValueError, KeyError):
            when = ""
        approvals.append({
            "kind": "question",
            "when": when,
            "title": task.get("title", ""),
            "excerpt": task.get("question", ""),
            "actions": [["Answer", f"/answer {task['id']} ", "primary"]],
        })
    return approvals


_calendar_cache: dict = {"at": 0.0, "rows": None}

@app.get("/panel")
def get_panel():
    # Only the calendar hits the Google API, so cache just that briefly;
    # plan and approvals are cheap local file reads and must stay fresh.
    if _calendar_cache["rows"] is None or time.time() - _calendar_cache["at"] >= 25:
        _calendar_cache["rows"] = _panel_calendar()
        _calendar_cache["at"] = time.time()
    return {
        "model": os.getenv("LLM_MODEL", "unknown"),
        "usage": None,  # no usage tracking backend yet; the UI hides the card
        "plan": [{"text": t["task"], "done": False} for t in read_tasks()],
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