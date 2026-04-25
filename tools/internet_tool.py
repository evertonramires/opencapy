from connectors.tools_connector import notify_tool_use
from connectors.internet_connector import browse_internet as connector_browse_internet, check_internet_connection as connector_check_internet_connection

def browse_internet(url: str) -> dict:
    notify_tool_use(f"🔧🌐🔍 Internet tool used to browse {url}.")
    return connector_browse_internet(url)

def check_internet_connection() -> dict:
    notify_tool_use("🔧🌐🧪 Internet tool used to check internet connection.")
    return connector_check_internet_connection()

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

check_internet_connection_tool = {
    "type": "function",
    "function": {
        "name": "check_internet_connection",
        "description": "Check internet access using Cloudflare trace and return structured network diagnostics.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
