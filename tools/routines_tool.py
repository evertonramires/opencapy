from connectors.tools_connector import notify_tool_use
from connectors.routines_connector import add_routine as add_routine_connector, read_routines as read_routines_connector, delete_routine as delete_routine_connector

def add_routine(start_time: str, interval: int, task: str) -> str:
    notify_tool_use(f"🔧🔁➕ routines_tool.add_routine called")
    return add_routine_connector(start_time, interval, task)

def read_routines() -> str:
    notify_tool_use(f"🔧🔁🔍 routines_tool.read_routines called")
    return read_routines_connector()

def delete_routine(routine_id: int) -> None:
    notify_tool_use(f"🔧🔁❌ routines_tool.delete_routine called")
    delete_routine_connector(routine_id)

add_routine_tool = {
    "type": "function",
    "function": {
        "name": "add_routine",
        "description": "Schedule a recurring routine with a start time and repeat interval.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_time": {
                    "type": "string",
                    "description": "The ISO8601 UTC timestamp for when the routine should first run.",
                },
                "interval": {
                    "type": "integer",
                    "description": "How often the routine repeats, in seconds. Examples: 7200 for every 2 hours, 86400 for every day.",
                },
                "task": {
                    "type": "string",
                    "description": "The routine content.",
                }
            },
            "required": ["start_time", "interval", "task"],
        },
    },
}

read_routines_tool = {
    "type": "function",
    "function": {
        "name": "read_routines",
        "description": "Read all scheduled routines from the routines book.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

delete_routine_tool = {
    "type": "function",
    "function": {
        "name": "delete_routine",
        "description": "Delete a routine by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "routine_id": {
                    "type": "integer",
                    "description": "The ID of the routine to delete.",
                }
            },
            "required": ["routine_id"],
        },
    },
}
