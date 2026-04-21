import requests

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
