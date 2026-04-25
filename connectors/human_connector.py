import json
import os

HUMAN_PENDING_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "human_pending.json")


def _ensure_human_pending():
    if not os.path.exists(HUMAN_PENDING_PATH):
        with open(HUMAN_PENDING_PATH, "w") as f:
            json.dump({"tasks": []}, f)


def add_human_task(timestamp, title, question, description, original_user_prompt):
    _ensure_human_pending()
    tasks = read_human_tasks()
    next_id = max([item["id"] for item in tasks], default=0) + 1
    task = {
        "id": next_id,
        "timestamp": timestamp,
        "title": title,
        "question": question,
        "description": description,
        "original_user_prompt": original_user_prompt,
    }
    tasks.append(task)
    with open(HUMAN_PENDING_PATH, "w") as f:
        json.dump({"tasks": tasks}, f, indent=4)
    return task


def read_human_tasks():
    _ensure_human_pending()
    with open(HUMAN_PENDING_PATH) as f:
        return json.load(f)["tasks"]


def get_human_task(task_id):
    _ensure_human_pending()
    tasks = read_human_tasks()
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None


def delete_human_task(task_id):
    _ensure_human_pending()
    tasks = read_human_tasks()
    tasks = [task for task in tasks if task["id"] != task_id]
    with open(HUMAN_PENDING_PATH, "w") as f:
        json.dump({"tasks": tasks}, f, indent=4)
