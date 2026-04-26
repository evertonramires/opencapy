import os
import importlib.util
from dotenv import load_dotenv
load_dotenv()

announce_tool_calls = os.getenv("ANNOUNCE_TOOL_CALLS", "false").lower()

def notify_tool_use(message: str) -> None:
    print(message)
    if announce_tool_calls in ["true", "1", "yes"]:
        from connectors.chat_connector import send_message
        send_message(message)
    
def list_tools() -> str:
    tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    human_readable_tools = ""
    for filename in os.listdir(tools_dir):
        if filename.endswith("_tool.py"):
            name = filename[:-3]
            spec = importlib.util.spec_from_file_location(name, os.path.join(tools_dir, filename))
            if spec is None:
                continue
            module = importlib.util.module_from_spec(spec)
            if spec.loader is None:
                continue
            spec.loader.exec_module(module)
            module_tools = [v for k, v in vars(module).items() if k.endswith("_tool") and isinstance(v, dict)]
            human_readable_tools += f"\n🔧 {name}:\n"
            for tool in module_tools:
                fn = tool["function"]
                human_readable_tools += f"- {fn['name']} - {fn['description']}\n"
    return human_readable_tools

if __name__ == "__main__":
    print(list_tools())