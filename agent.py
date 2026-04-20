import os
import time

from llm_connector import prompt_model
from memory_connector import add_memory, read_memory, prune_memory

identity_path = os.path.join(os.path.dirname(__file__), "IDENTITY.md")
memory_length_messages = int(os.getenv("MEMORY_LENGTH_MESSAGES", 5))


def load_identity():
    with open(identity_path, "r") as f:
        return f.read().strip()
    
def prompt(text: str) -> str:
    identity = load_identity()
    memory = read_memory()
    memory_text = "\n".join([f"{item['person']}: {item['memory']}" for item in memory])
    full_prompt = f"{identity}\n\nMemory:\n{memory_text}\n\n Prompt: {text}"
    response = prompt_model(full_prompt)
    add_memory(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), text, "user")
    add_memory(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), response, "you")
    prune_memory(memory_length_messages)
    return response