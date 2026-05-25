from connectors.tools_connector import notify_tool_use
from connectors.blacksmith_connector import forge_tool as connector_forge_tool


def forge_new_tool(tool_name: str, tool_request: str) -> dict:
    notify_tool_use(f"🔧⚒️➕ Blacksmith tool used to generate a new {tool_name} tool.")
    return connector_forge_tool(tool_name, tool_request)


forge_new_tool_tool = {
    "type": "function",
    "function": {
        "name": "forge_new_tool",
        "description": "Ask a blacksmith to forge a new tool for you. Use this tool only when you need a new capability that no combination of other available tools can provide. Be as specific as possible in your request to ensure the generated tool meets your needs.",
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "The exact base name for the generated tool files. Example: 'calendar' creates tools/calendar_custom_tool.py and connectors/calendar_custom_connector.py.",
                },
                "tool_request": {
                    "type": "string",
                    "description": "A precise description of the new tool to create, including expected functions, inputs, behavior, configuration, and safety gates.",
                },
            },
            "required": ["tool_name", "tool_request"],
        },
    },
}
