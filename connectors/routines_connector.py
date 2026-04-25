import json
import os

ROUTINES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "routines.json")

def _ensure_routines():
    if not os.path.exists(ROUTINES_PATH):
        with open(ROUTINES_PATH, "w") as f:
            json.dump({"routines": []}, f)


def add_routine(start_time, interval, task) -> str:
    _ensure_routines()
    data = read_routines()
    next_id = max([item["id"] for item in data], default=0) + 1
    data.append({"id": next_id, "start_time": start_time, "interval": interval, "task": task})
    with open(ROUTINES_PATH, "w") as f:
        json.dump({"routines": data}, f, indent=4)
    return f"♾️ Routine added: {next_id}. {task} starting at {start_time}, repeating every {interval}s"

def read_routines():
    _ensure_routines()
    with open(ROUTINES_PATH) as f:
        return json.load(f)["routines"]

def delete_routine(routine_id):
    _ensure_routines()
    data = read_routines()
    data = [routine for routine in data if routine["id"] != routine_id]
    with open(ROUTINES_PATH, "w") as f:
        json.dump({"routines": data}, f, indent=4)
