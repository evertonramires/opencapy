import os
import json
import time
import calendar
import random
import sys
import subprocess
import traceback
from dotenv import load_dotenv
load_dotenv()

from connectors.clock_connector import get_time
from connectors.taskbook_connector import delete_task, read_tasks
from connectors.routines_connector import read_routines
from connectors.calendar_connector import calendar_today
from connectors.vikunja_connector import (
    check_new_todos,
    daily_dateless_todos,
    daily_focus_todos,
    mark_date_nudge_sent,
    mark_focus_sent,
    mark_todos_seen,
    vikunja_enabled,
)
from agent import prompt
from connectors.chat_connector import register_commands, send_message, read_messages
from datetime import datetime


heartbeat_interval_seconds = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))
announce_errors = os.getenv("ANNOUNCE_ERRORS", "false").lower()
vikunja_watch_interval_seconds = int(os.getenv("VIKUNJA_WATCH_INTERVAL_SECONDS", 30))
last_vikunja_check = 0
vikunja_watch_error_notified = False

chat_api_host = os.getenv("CHAT_API_HOST", "http://localhost:8000")
chat_api_bind = chat_api_host.replace("http://", "").replace("https://", "")
chat_api_bind_host, chat_api_bind_port = chat_api_bind.split(":")
chat_api_bind_host = os.getenv("CHAT_API_BIND_HOST", chat_api_bind_host)
chat_api_bind_port = os.getenv("CHAT_API_BIND_PORT", chat_api_bind_port)
    
now = int(get_time("timestamp"))
last_heartbeat = now
delta_time = 0

def heartbeat() -> bool:
    global now, last_heartbeat, delta_time
    now = int(get_time("timestamp"))
    delta_time = now - last_heartbeat
    if delta_time >= heartbeat_interval_seconds:
        last_heartbeat = now
        delta_time = 0
        return True
    return False

if __name__ == "__main__":
    try:
        # if IDENTITY.md and .env doesn't exist, create them with default content
        if not os.path.exists("IDENTITY.md"):
            print("⚙️ IDENTITY.md not found, creating with default content. Make sure to update it later!")
            with open("IDENTITY.md.EXAMPLE") as src, open("IDENTITY.md", "w") as dst:
                dst.write(src.read())
        if not os.path.exists(".env"):
            print("⚙️ .env not found, creating with default content. Make sure to update it later!")
            with open(".env.EXAMPLE") as src, open(".env", "w") as dst:
                dst.write(src.read())
        
        hood_files = {
            "hood/memory.json": '{"memory": []}',
            "hood/routines.json": '{"routines": []}',
            "hood/taskbook.json": '{"tasks": []}',
            "hood/human_pending.json": '{"tasks": []}',
            "hood/calendar_oauth.json": '{"state": "", "refresh_token": "", "redirect_uri": ""}',  
            "hood/whitelist.json": '[]',
            "hood/notebook.md": "",
        }
        for path, default in hood_files.items():
            valid = False
            if os.path.exists(path):
                try:
                    if path.endswith(".json"):
                        json.loads(open(path).read())
                    valid = True
                except Exception:
                    pass
            if not valid:
                print(f"⚙️ {path} missing or invalid, recreating with default content.")
                with open(path, "w") as f:
                    f.write(default)

        register_commands()
        try:
            subprocess.Popen([sys.executable, "-m", "uvicorn", "api.api:app", "--host", chat_api_bind_host, "--port", chat_api_bind_port], stdout=subprocess.DEVNULL)
        except Exception as e:
            print(f"⚠️ Failed to start API: {e}")
        time.sleep(2)  # Wait for API server to start
        print("\n\n⚙️ Waking up your Capy, this may take a minute..")
        send_message("⚙️ Waking up your Capy, this may take a minute...")
        wake_style = random.choice([
            "fun and playful",
            "sleepy and grumpy but lovable",
            "dramatic and theatrical",
            "chill and minimal, barely a word",
            "overly formal butler style, tongue in cheek",
            "like you overslept and are pretending you didn't",
        ])
        wake_message = prompt(f"[system] Wake up! Greet the user in a {wake_style} way, in one or two short sentences. Do not reuse greetings or phrasing from your memory.")
        send_message(f"{wake_message}\n\n🟢 Ready to work!")
        print(f"\n\nNavigate to {chat_api_host}/ to start chatting.\n\n🟢 Ready to work!\n\n")

        while True:
            try:
                time.sleep(1)
                if heartbeat():
                    read_messages()
                    # Read tasks and execute if in time
                    tasks = read_tasks()
                    for task in tasks:
                        task_time = calendar.timegm(time.strptime(task["timestamp"], "%Y-%m-%dT%H:%M:%SZ"))
                        if now >= task_time:
                            response = prompt(f"[system] This task just triggered, if it requires a tool, execute, if not, treat as a notification to the user: {task['task']}")
                            send_message(f"🕰️ {response}")
                            delete_task(task["id"])
                    routines = read_routines()
                    for routine in routines:
                        routine_start = calendar.timegm(time.strptime(routine["start_time"], "%Y-%m-%dT%H:%M:%SZ"))
                        if now >= routine_start and (now - routine_start) % routine["interval"] < heartbeat_interval_seconds:
                            response = prompt(f"[system] This routine just triggered, if it requires a tool, execute, if not, treat as a notification to the user: {routine['task']}")
                            send_message(f"♾️ {response}")
                    calendar_events = calendar_today()
                    if calendar_events is not False:
                        response = prompt(f"[system] These are today's calendar events: {calendar_events}. If it requires a tool, execute, if not, treat as a notification to the user.")
                        send_message(f"📅 {response}")
                    if vikunja_enabled() and now - last_vikunja_check >= vikunja_watch_interval_seconds:
                        last_vikunja_check = now
                        new_todos = check_new_todos()
                        if isinstance(new_todos, dict):
                            if not vikunja_watch_error_notified:
                                vikunja_watch_error_notified = True
                                if announce_errors == "true":
                                    send_message(f"⚠️ Vikunja watcher: {new_todos.get('message')}")
                                print(f"⚠️ Vikunja watcher: {new_todos.get('message')}")
                        else:
                            vikunja_watch_error_notified = False
                            if new_todos:
                                response = prompt(
                                    "[system] The user just added these to-dos directly in Vikunja (not through you): "
                                    f"{json.dumps(new_todos)}. Acknowledge them in one or two friendly sentences, mentioning the titles. "
                                    "Capturing the thought was the win, so don't demand decisions. "
                                    "If one is clearly a multi-step project, break it into 3 to 6 small subtasks with add_subtasks and mention you did, "
                                    "so its progress bar and Gantt view work; if the breakdown isn't obvious, don't guess, just acknowledge. "
                                    "Ask at most one short optional question, and only if something is clearly time-sensitive and missing a due date. "
                                    "No guilt, no lectures, no other tools."
                                )
                                if response.startswith("⚠️ Failed communicating"):
                                    print(f"⚠️ Vikunja watcher: LLM unavailable, will retry announcing new to-dos on the next check.")
                                else:
                                    send_message(f"👀 {response}")
                                    mark_todos_seen([todo["id"] for todo in new_todos])
                    focus_todos = daily_focus_todos()
                    if isinstance(focus_todos, list):
                        if not focus_todos:
                            mark_focus_sent()
                        else:
                            response = prompt(
                                "[system] Morning focus time. These are the user's pending to-dos: "
                                f"{json.dumps(focus_todos)}. Keep this light: pick at most 3 that matter most today "
                                "(due or overdue first), then suggest exactly one to start with, with a first step so small it takes two minutes. "
                                "Be brief, warm and encouraging. Never mention how many tasks are pending in total, never guilt about overdue ones."
                            )
                            if response.startswith("⚠️ Failed communicating"):
                                print("⚠️ Vikunja focus: LLM unavailable, will retry on the next heartbeat.")
                            else:
                                send_message(f"🎯 {response}")
                                mark_focus_sent()
                    dateless_todos = daily_dateless_todos()
                    if isinstance(dateless_todos, list):
                        if not dateless_todos:
                            mark_date_nudge_sent()
                        else:
                            response = prompt(
                                "[system] Daily planning nudge. These to-dos have no due date: "
                                f"{json.dumps(dateless_todos)}. In one short friendly message, list them (at most 5) and ask the user "
                                "to reply with rough dates so their Gantt timeline and planning views stay useful. Make clear that rough "
                                "answers like 'friday' or 'next week' are fine and that skipping any of them is ok. "
                                "When they reply later, set the dates with the update_todo tool. No guilt, keep it inviting."
                            )
                            if response.startswith("⚠️ Failed communicating"):
                                print("⚠️ Vikunja date nudge: LLM unavailable, will retry on the next heartbeat.")
                            else:
                                send_message(f"🗓️ {response}")
                                mark_date_nudge_sent()

            except Exception as e:
                try:
                    error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error_type = type(e).__name__
                    frames = traceback.extract_tb(e.__traceback__)
                    connector_frame = next((frame for frame in reversed(frames) if "/connectors/" in frame.filename and frame.filename.endswith("_connector.py")), None)
                    error_frame = connector_frame or frames[-1]
                    error_module = os.path.splitext(os.path.basename(error_frame.filename))[0]
                    error_trace = traceback.format_exc()
                    error_msg = f"\n⚠️ [{error_time}][{error_module}] {error_type}.\n\n{e if announce_errors == "true" else ""}\n🔵 Continuing execution...\n\n"
                    print(error_msg)
                    if announce_errors == "true":
                        send_message(f"⚠️ Error at {error_time}:\nModule: {error_module}\n{error_type}: {e}")
                except Exception:
                    pass
    except KeyboardInterrupt:
        print("\n\n⚙️ Ctrl+C detected, running stop.sh..\n\n")
        subprocess.run(["bash", "stop.sh"])