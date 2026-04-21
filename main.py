import os
import time
import calendar
from dotenv import load_dotenv
load_dotenv()

from clock_connector import get_time
from telegram_connector import register_telegram_commands
from taskbook_connector import delete_task, read_tasks
from agent import prompt
from chat_connector import send_message, read_messages


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
        print("[System] IDENTITY.md not found, creating with default content. Make sure to update it later!")
        with open("IDENTITY.md.EXAMPLE") as src, open("IDENTITY.md", "w") as dst:
            dst.write(src.read())
    if not os.path.exists(".env"):
        print("[System] .env not found, creating with default content. Make sure to update it later!")
        with open(".env.EXAMPLE") as src, open(".env", "w") as dst:
            dst.write(src.read())
    
    register_telegram_commands()
    print("[System] Ready to work!")
    send_message("[System] Ready to work!")
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
                        response = prompt(f"Task: {task['task']}")
                        send_message(f"[Task] {response}")
                        delete_task(task["id"])
        except Exception as e:
            print(f"[Error] {e}\n Continuing execution...")