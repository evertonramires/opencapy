import os
import time
import calendar
from dotenv import load_dotenv
load_dotenv()

from telegram_connector import send_telegram_message, read_telegram_messages
from taskbook_connector import add_task, delete_task, read_tasks
from llm_connector import prompt


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
    print("[System] Ready to work!")
    send_telegram_message("[System] Ready to work!")
    while True:
        try:
            time.sleep(1)
            if heartbeat():
                            
                # Read telegram messages and process commands
                messages = read_telegram_messages()
                if messages:
                    for message in messages:
                        if "/delete" in message:
                            task_id = int(message.split("/delete")[1].strip())
                            delete_task(task_id)
                        elif "/add" in message:
                            try:
                                task_text = message.split("/add")[1].strip()
                                current_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                                llm_response = prompt(f"Current time: {current_time}\nExtract a task and scheduled timestamp from: \"{task_text}\"\nReply with exactly two lines:\nTASK: <task description>\nTIMESTAMP: <ISO8601 UTC timestamp>")
                                task = llm_response.split("TASK:")[1].split("\n")[0].strip()
                                timestamp = llm_response.split("TIMESTAMP:")[1].strip().split("\n")[0].strip()
                                add_task_response = add_task(timestamp, task)
                                print(add_task_response)
                                send_telegram_message(add_task_response)
                            except Exception as e:
                                send_telegram_message(f"Sorry, I couldn't add the task, can we try again? Details: {e}")
                        elif "/list" in message:
                            tasks = read_tasks()
                            task_list = "\n".join([f"[{task['timestamp']}] {task['id']}. {task['task']}" for task in tasks])
                            send_telegram_message(f"Current tasks:\n{task_list}")
                        else:
                            response = prompt(f"User said: {message}")
                            send_telegram_message(response)
                        
                # Read tasks and execute if in time
                tasks = read_tasks()
                for task in tasks:
                    task_time = calendar.timegm(time.strptime(task["timestamp"], "%Y-%m-%dT%H:%M:%SZ"))
                    if now >= task_time:
                        response = prompt(f"Task: {task['task']}")
                        send_telegram_message(f"[Task] {response}")
                        delete_task(task["id"])
        except Exception as e:
            print(f"[Error] {e}\n Continuing execution...")