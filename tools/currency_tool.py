from connectors.tools_connector import notify_tool_use
from connectors.currency_connector import get_currency as connector_get_currency

def get_currency(base: str, target: str) -> dict:
    notify_tool_use(f"🔧💱 currency_tool.get_currency called")
    return connector_get_currency(base, target)

get_currency_tool = {
    "type": "function",
    "function": {
        "name": "get_currency",
        "description": "Get the current exchange rate between two currencies.",
        "parameters": {
            "type": "object",
            "properties": {
                "base": {
                    "type": "string",
                    "description": "The source currency code (e.g. 'USD', 'EUR').",
                },
                "target": {
                    "type": "string",
                    "description": "The target currency code (e.g. 'BRL', 'GBP').",
                },
            },
            "required": ["base", "target"],
        },
    },
}
