from connectors.tools_connector import notify_tool_use
from connectors.websearch_connector import web_search as connector_web_search


def web_search(query: str, count: int = 5) -> list[dict]:
    notify_tool_use(f"🔧🦆🔎 Websearch tool used to search DuckDuckGo for:\n\n{query}")
    return connector_web_search(query, count)


web_search_tool = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web using DuckDuckGo and return a list of result titles and links. Use this tool when you need to find recent information or explore a topic. The results are based on DuckDuckGo's search engine and may include a variety of sources.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to send to DuckDuckGo.",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 5).",
                },
            },
            "required": ["query"],
        },
    },
}
