import importlib.util
import os

from connectors.llm_connector import prompt_model
from connectors.memory_connector import add_memory, read_memory, prune_memory
from connectors.clock_connector import get_time as connector_get_time

identity_path = os.path.join(os.path.dirname(__file__), "IDENTITY.md")
memory_length_messages = int(os.getenv("MEMORY_LENGTH_MESSAGES", 5))
_tools_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")


def _load_tools():
    tools = []
    handlers = {}
    for filename in os.listdir(_tools_dir):
        if not filename.endswith("_tool.py"):
            continue
        name = filename[:-3]
        spec = importlib.util.spec_from_file_location(name, os.path.join(_tools_dir, filename))
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for k, v in vars(module).items():
            if k.endswith("_tool") and isinstance(v, dict):
                tools.append(v)
                fn_name = v["function"]["name"]
                handlers[fn_name] = getattr(module, fn_name)
    return tools, handlers


def load_identity():
    with open(identity_path, "r") as f:
        return f.read().strip()
    
def prompt(text: str) -> str:
    identity = load_identity()
    memory = read_memory()
    memory_text = "\n".join([f"{item['person']}: {item['memory']}" for item in memory])
    tools, handlers = _load_tools()
    full_prompt = f"{identity}\n\nMemory:\n{memory_text}\n\n Prompt: {text}"
    response = prompt_model(full_prompt, tools=tools, tool_handlers=handlers)
    add_memory(connector_get_time("utc"), text, "user")
    add_memory(connector_get_time("utc"), response, "you")
    prune_memory(memory_length_messages)
    return response