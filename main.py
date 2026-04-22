import os
import json
import time
import calendar
import subprocess
from dotenv import load_dotenv
load_dotenv()

from connectors.clock_connector import get_time
from connectors.taskbook_connector import delete_task, read_tasks
from connectors.routines_connector import read_routines
from agent import prompt
from connectors.chat_connector import register_commands, send_message, read_messages


heartbeat_interval_seconds = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))
    
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
        subprocess.Popen(["uvicorn", "api.api:app", "--host", "0.0.0.0", "--port", "8000"], stdout=subprocess.DEVNULL)
    except Exception as e:
        print(f"⚠️ Failed to start API: {e}")
    print("🟢 Ready to work!")
    send_message("🟢 Ready to work!")
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
                        send_message(f"🔁 {response}")
        except Exception as e:
            print(f"⚠️ {e}\n 🔵 Continuing execution...")
            try:
                send_message(f"⚠️ {e}\n 🔵 Continuing execution...")
            except Exception:
                pass