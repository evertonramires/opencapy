from connectors.tools_connector import notify_tool_use
from connectors.fetch_connector import fetch_url as connector_fetch_url

def fetch_url(url: str, method: str, headers: dict, body: str) -> dict:
    notify_tool_use(f"🔧🌐📥 Fetch tool used to make a {method} request to {url}.")
    return connector_fetch_url(url, method, headers, body)

fetch_url_tool = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": "Fetch data from a URL, like curl or wget. Supports any HTTP method, custom headers, and a request body.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch.",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": "The HTTP method to use.",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers as key-value pairs.",
                },
                "body": {
                    "type": "string",
                    "description": "Optional request body (e.g. JSON string for POST requests).",
                },
            },
            "required": ["url", "method"],
        },
    },
}
