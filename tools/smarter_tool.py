import importlib.util
import os
from connectors.tools_connector import notify_tool_use
from connectors.smarter_connector import ask_smarter as connector_ask_smarter

_tools_dir = os.path.dirname(os.path.abspath(__file__))

def _load_tools():
    tools = []
    handlers = {}
    for filename in os.listdir(_tools_dir):
        if not filename.endswith("_tool.py") or filename == "smarter_tool.py":
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
                handlers[v["function"]["name"]] = getattr(module, v["function"]["name"])
    return tools, handlers

def ask_smarter(question: str) -> str:
    notify_tool_use(f"🔧🧠✨ Smarter tool used to ask a smarter agent.")
    tools, handlers = _load_tools()
    return connector_ask_smarter(question, tools=tools, tool_handlers=handlers)

ask_smarter_tool = {
    "type": "function",
    "function": {
        "name": "ask_smarter",
        "description": "Ask a smarter, more capable agent for help when the current task requires deeper reasoning, complex analysis, or expert-level knowledge. The smarter agent has access to all the same tools you do and can call them on your behalf.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question or task to send to the smarter model.",
                },
            },
            "required": ["question"],
        },
    },
}
