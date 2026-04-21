from tools_connector import notify_tool_use
from taskbook_connector import add_task as add_task_connector, read_tasks as read_tasks_connector, delete_task as delete_task_connector

def add_task(timestamp: str, task: str) -> str:
    notify_tool_use(f"🪛📑➕ taskbook_tool.add_task called")
    return add_task_connector(timestamp, task)

def read_tasks() -> str:
    notify_tool_use(f"🪛📑🔍 taskbook_tool.read_tasks called")
    return read_tasks_connector()

def delete_task(task_id: int) -> None:
    notify_tool_use(f"🪛📑❌ taskbook_tool.delete_task called")
    delete_task_connector(task_id)

add_task_tool = {
    "type": "function",
    "function": {
        "name": "add_task",
        "description": "Schedule a task to be executed at a given timestamp.",
        "parameters": {
            "type": "object",
            "properties": {
                "timestamp": {
                    "type": "string",
                    "description": "The ISO8601 UTC timestamp for when the task should be executed.",
                },
                "task": {
                    "type": "string",
                    "description": "The task content.",
                }
            },
            "required": ["timestamp", "task"],
        },
    },
}

read_tasks_tool = {
    "type": "function",
    "function": {
        "name": "read_tasks",
        "description": "Read all scheduled tasks from the taskbook.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

delete_task_tool = {
    "type": "function",
    "function": {
        "name": "delete_task",
        "description": "Delete a task from the taskbook by its ID. Use this if you want to remove something from the taskbook.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The ID of the task to delete.",
                }
            },
            "required": ["task_id"],
        },
    },
}