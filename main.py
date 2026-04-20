import os
import time
from dotenv import load_dotenv
load_dotenv()

from telegram_connector import send_telegram_message, read_telegram_messages
from taskbook_connector import add_task, delete_task, read_tasks


heartbeat_interval_seconds = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))
now = time.time()
last_heartbeat = now
delta_time = 0

def heartbeat() -> bool:
    global now, last_heartbeat, delta_time
    now = time.time()
    delta_time = now - last_heartbeat
    if delta_time >= heartbeat_interval_seconds:
        last_heartbeat = now
        delta_time = 0
        return True
    return False

if __name__ == "__main__":
    send_telegram_message("Ready to work!")
    while True:
        time.sleep(1)
        if heartbeat():
            
            # Read telegram messages and process commands
            messages = read_telegram_messages()
            if messages:
                for message in messages:
                    if "/delete" in message:
                        task_id = int(message.split("/delete")[1].strip())
                        delete_task(task_id)
                    if "/add" in message:
                        task = message.split("/add")[1].strip()
                        add_task(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), task)
                    if "/list" in message:
                        tasks = read_tasks()
                        task_list = "\n".join([f"{task['id']}. [{task['timestamp']}] {task['task']}" for task in tasks])
                        send_telegram_message(f"Current tasks:\n{task_list}")

            # Read tasks and execute if in time
            tasks = read_tasks()
            for task in tasks:
                task_time = time.mktime(time.strptime(task["timestamp"], "%Y-%m-%dT%H:%M:%SZ"))
                if now >= task_time:
                    send_telegram_message(f"Executing task: {task['task']}")
                    delete_task(task["id"])