from connectors.tools_connector import notify_tool_use
from connectors.browser_connector import run_browser_task as connector_run_browser_task

def run_browser_task(task: str) -> dict:
    notify_tool_use(f"🔧🌐🤖 Browser tool used to execute task: {task}")
    return connector_run_browser_task(task)

run_browser_task_tool = {
    "type": "function",
    "function": {
        "name": "run_browser_task",
        "description": "A full web browser controlled by another AI agent. This browser is fully configured by the user including pre-saved credentials. Use this to interact with websites, click buttons, fill forms, or extract information visually, specially for services that require authentication.",
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
