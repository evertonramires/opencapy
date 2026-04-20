import json
import os

TASKBOOK_PATH = os.path.join(os.path.dirname(__file__), "hood", "taskbook.json")

def _ensure_taskbook():
    if not os.path.exists(TASKBOOK_PATH):
        with open(TASKBOOK_PATH, "w") as f:
            json.dump({"tasks": []}, f)


def add_task(timestamp, task) -> str:
    _ensure_taskbook()
    data = read_tasks()
    next_id = max([item["id"] for item in data], default=0) + 1
    data.append({"id": next_id, "timestamp": timestamp, "task": task})
    with open(TASKBOOK_PATH, "w") as f:
        json.dump({"tasks": data}, f, indent=4)
    return f"[System] Task added: {next_id}. {task} at {timestamp}"
def read_tasks():
    _ensure_taskbook()
    with open(TASKBOOK_PATH) as f:
        return json.load(f)["tasks"]
    
def delete_task(task_id):
    _ensure_taskbook()
    data = read_tasks()
    data = [task for task in data if task["id"] != task_id]
    with open(TASKBOOK_PATH, "w") as f:
        json.dump({"tasks": data}, f, indent=4)
    
