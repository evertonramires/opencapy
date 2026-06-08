from connectors.tools_connector import notify_tool_use
from connectors.browser_connector import run_browser_task as connector_run_browser_task

def run_browser_task(task: str) -> dict:
    notify_tool_use(f"🔧🌐🤖 Browser tool used to execute task: {task}")
    return connector_run_browser_task(task)

run_browser_task_tool = {
    "type": "function",
    "function": {
        "name": "run_browser_task",
        "description": "Execute a task in the web browser using an AI agent. Use this to interact with websites, click buttons, fill forms, or extract information visually.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The detailed task instructions for the browser agent to execute.",
                },
            },
            "required": ["task"],
        },
    },
}
