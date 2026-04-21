from connectors.tools_connector import notify_tool_use
from connectors.weather_connector import get_weather as connector_get_weather

def get_weather(location: str) -> dict:
    notify_tool_use(f"🔧🌤️ weather_tool.get_weather called")
    return connector_get_weather(location)

get_weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a given location. Returns temperature, humidity, wind speed, and a weather code.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city or location name to get weather for (e.g. 'London', 'New York').",
                }
            },
            "required": ["location"],
        },
    },
}
