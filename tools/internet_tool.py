from connectors.tools_connector import notify_tool_use
from connectors.internet_connector import browse_internet as connector_browse_internet

def browse_internet(url: str) -> dict:
    notify_tool_use(f"🔧🌐 internet_tool.browse_internet called")
    return connector_browse_internet(url)

browse_internet_tool = {
    "type": "function",
    "function": {
        "name": "browse_internet",
        "description": "Browse a URL on the internet and get its content.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to browse.",
                },
            },
            "required": ["url"],
        },
    },
}
