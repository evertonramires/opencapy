import os
import json
import time
import calendar
import subprocess
import traceback
from dotenv import load_dotenv
load_dotenv()

from connectors.clock_connector import get_time
from connectors.taskbook_connector import delete_task, read_tasks
from connectors.routines_connector import read_routines
from agent import prompt
from connectors.chat_connector import register_commands, send_message, read_messages
from datetime import datetime


heartbeat_interval_seconds = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))
announce_errors = os.getenv("ANNOUNCE_ERRORS", "false").lower()

chat_api_host = os.getenv("CHAT_API_HOST", "http://localhost:8000")
chat_api_bind = chat_api_host.replace("http://", "").replace("https://", "")
chat_api_bind_host, chat_api_bind_port = chat_api_bind.split(":")
    
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
            subprocess.Popen(["uvicorn", "api.api:app", "--host", chat_api_bind_host, "--port", chat_api_bind_port], stdout=subprocess.DEVNULL)
        except Exception as e:
            print(f"⚠️ Failed to start API: {e}")
        time.sleep(2)  # Wait for API server to start
        print("\n\n⚙️ Waking up your Capy, this may take a minute..")
        send_message("⚙️ Waking up your Capy, this may take a minute...")
        wake_message = prompt(f"[system] Wake up! tell the user that you just woke up in a fun, playful way!")
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
                            send_message(f"🔁 {response}")
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