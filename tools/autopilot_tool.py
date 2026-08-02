from connectors.tools_connector import notify_tool_use
from connectors.autopilot_connector import (
    autopilot_enabled,
    queue_work as connector_queue_work,
    read_queue as connector_read_queue,
)

def queue_task_work(todo_id: int, goal: str) -> dict:
    notify_tool_use(f"🔧🚀➕ Autopilot tool used to queue work on to-do {todo_id}.")
    return connector_queue_work(todo_id, goal)

def list_queued_work() -> list[dict]:
    notify_tool_use("🔧🚀🔍 Autopilot tool used to list queued work.")
    return connector_read_queue()

if autopilot_enabled():
    queue_task_work_tool = {
        "type": "function",
        "function": {
            "name": "queue_task_work",
            "description": (
                "Take a to-do on yourself and move it forward without being asked. Use it whenever you could "
                "genuinely make progress alone: finding a phone number or address, checking opening hours, comparing "
                "options or prices, gathering links, drafting a message the user will send. The research runs shortly "
                "after and the findings get written into the to-do, so the task is smaller and more concrete when the "
                "user next looks at it. Do not queue things that need the user's body, wallet, memory or decision "
                "(going somewhere, paying, choosing between personal preferences) since there is nothing you can do "
                "alone there. One call per to-do."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "integer",
                        "description": "The id of the to-do you are taking on.",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Concretely what you will find out or produce, e.g. 'find three nearby dentists that take his insurance, with phone numbers and whether they book online'. This is the only instruction you get later, so make it specific.",
                    },
                },
                "required": ["todo_id", "goal"],
            },
        },
    }

    list_queued_work_tool = {
        "type": "function",
        "function": {
            "name": "list_queued_work",
            "description": "List the to-dos you have queued to research but not worked on yet.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }
