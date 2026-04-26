import os
import requests

def currency_enabled() -> bool:
    return os.getenv("ENABLE_CURRENCY", "false").lower() in ["true", "1", "yes"]

def _get_crypto_rate(base: str, target: str) -> dict:
    search = requests.get(
        "https://api.coingecko.com/api/v3/search",
        params={"query": base},
    ).json()
    coin_id = search["coins"][0]["id"]
    price = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": coin_id, "vs_currencies": target.lower()},
    ).json()
    return {
        "base": base.upper(),
        "target": target.upper(),
        "rate": price[coin_id][target.lower()],
        "date": "real-time",
    }

def get_currency(base: str, target: str) -> dict:
    if not currency_enabled():
        return {
            "status": "error",
            "tool": "currency",
            "message": "Currency tool is disabled. To enable it, set ENABLE_CURRENCY=true in your .env file.",
        }
    response = requests.get(
        "https://api.frankfurter.dev/v1/latest",
        params={"from": base.upper(), "to": target.upper()},
    ).json()
    if "base" not in response:
        return _get_crypto_rate(base, target)
    return {
        "base": response["base"],
        "target": target.upper(),
        "rate": response["rates"][target.upper()],
        "date": response["date"],
    }
