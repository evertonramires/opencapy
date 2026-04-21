import json
import os

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "hood", "memory.json")

def _ensure_memory():
    if not os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "w") as f:
            json.dump({"memory": []}, f)


def add_memory(timestamp, memory, person) -> str:
    _ensure_memory()
    data = read_memory()
    next_id = max([item["id"] for item in data], default=0) + 1
    data.append({"id": next_id, "timestamp": timestamp, "memory": memory, "person": person})
    with open(MEMORY_PATH, "w") as f:
        json.dump({"memory": data}, f, indent=4)
    return f"⚙️ Memory added: {next_id}. {memory} at {timestamp}"
def read_memory():
    _ensure_memory()
    with open(MEMORY_PATH) as f:
        return json.load(f)["memory"]
    
def delete_memory(memory_id):
    _ensure_memory()
    data = read_memory()
    data = [memory for memory in data if memory["id"] != memory_id]
    with open(MEMORY_PATH, "w") as f:
        json.dump({"memory": data}, f, indent=4)

def prune_memory(max_length):
    memory = read_memory()
    if len(memory) > max_length:
        memory = memory[-max_length:]
        with open(MEMORY_PATH, "w") as f:
            json.dump({"memory": memory}, f, indent=4)
    
