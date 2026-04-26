import os
import requests

def weather_enabled() -> bool:
    return os.getenv("ENABLE_WEATHER", "false").lower() in ["true", "1", "yes"]

def get_weather(location: str) -> dict:
    if not weather_enabled():
        return {"status": "error", "message": "Weather tool is disabled. To enable it, set ENABLE_WEATHER=true in your .env file."}
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
    ).json()
    result = geo["results"][0]
    lat, lon, name, country = result["latitude"], result["longitude"], result["name"], result["country"]

    weather = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
        },
    ).json()
    current = weather["current"]
    return {
        "location": f"{name}, {country}",
        "temperature_celsius": current["temperature_2m"],
        "humidity_percent": current["relative_humidity_2m"],
        "wind_speed_kmh": current["wind_speed_10m"],
        "weather_code": current["weather_code"],
    }
