from connectors.tools_connector import notify_tool_use
from connectors.news_connector import get_news as connector_get_news

def get_news(topic: str, count: int) -> list[dict]:
    notify_tool_use(f"🔧📰 News tool used to get {count} headlines for topic {topic}.")
    return connector_get_news(topic, count)

get_news_tool = {
    "type": "function",
    "function": {
        "name": "get_news",
        "description": "Get the latest news headlines from BBC News for a given topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": ["top", "world", "technology", "science", "business", "health", "sport"],
                    "description": "The news topic to fetch.",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of headlines to return (e.g. 5).",
                },
            },
            "required": ["topic", "count"],
        },
    },
}
