import json
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from connectors.calendar_connector import create_calendar_oauth_session, complete_calendar_oauth

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