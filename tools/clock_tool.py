from connectors.tools_connector import notify_tool_use
from connectors.clock_connector import get_time as connector_get_time

def get_time(format: str) -> str | int:
    notify_tool_use(f"🔧⌚🕒 Clock tool used to get current time in {format} format.")
    return connector_get_time(format)

clock_tool = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Get the current time. Use 'utc' for UTC ISO string, 'local' for local ISO string, or 'timestamp' for Unix timestamp.",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["utc", "local", "timestamp"],
                    "description": "The time format to return. UTC preferred.",
                }
            },
            "required": ["format"],
        },
    },
}