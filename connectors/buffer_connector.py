import json
import os
import time
from connectors.clock_connector import get_time
from connectors.usage_connector import buffering_active, window_resets_at

BUFFER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "buffer.json")
WINDOW_SECONDS = 5 * 3600

def _ensure_buffer():
    if not os.path.exists(BUFFER_PATH):
        with open(BUFFER_PATH, "w") as f:
            json.dump({"items": []}, f)


def add_buffered(task, source, tier="") -> str:
    _ensure_buffer()
    data = read_buffered()
    # A recurring routine fires every interval while buffering, so keep one entry per distinct task
    if any(item["task"] == task for item in data):
        return f"🪫 Already buffered for the next usage window: {task}"
    next_id = max([item["id"] for item in data], default=0) + 1
    # run_after is this window's reset, so auto buffered and manually deferred work both wait for the next one.
    # Automatic buffering only happens when usage reads fine, so an unknown reset means someone asked for this
    # explicitly, and a whole window is a better guess than running it on the next heartbeat.
    run_after = window_resets_at() or int(time.time()) + WINDOW_SECONDS
    data.append({"id": next_id, "timestamp": get_time("utc"), "source": source, "task": task, "tier": tier, "run_after": run_after})
    with open(BUFFER_PATH, "w") as f:
        json.dump({"items": data}, f, indent=4)
    return f"🪫 Buffered for the next usage window: {next_id}. {task}"


def read_buffered():
    _ensure_buffer()
    with open(BUFFER_PATH) as f:
        return json.load(f)["items"]


def due_buffered():
    if buffering_active():
        return []
    now = int(time.time())
    return [item for item in read_buffered() if now >= item["run_after"]]


def delete_buffered(item_id):
    _ensure_buffer()
    data = [item for item in read_buffered() if item["id"] != item_id]
    with open(BUFFER_PATH, "w") as f:
        json.dump({"items": data}, f, indent=4)
