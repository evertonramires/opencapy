import os

import requests
import xml.etree.ElementTree as ET

def news_enabled() -> bool:
    return os.getenv("ENABLE_NEWS", "false").lower() in ["true", "1", "yes"]

_FEEDS = {
    "top":         "https://feeds.bbci.co.uk/news/rss.xml",
    "world":       "https://feeds.bbci.co.uk/news/world/rss.xml",
    "technology":  "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "science":     "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "business":    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "health":      "https://feeds.bbci.co.uk/news/health/rss.xml",
    "sport":       "https://feeds.bbci.co.uk/news/sport/rss.xml",
}

def get_news(topic: str, count: int) -> list[dict]:
    if not news_enabled():
        return [{"status": "error", "message": "News tool is disabled. To enable it, set ENABLE_NEWS=true in your .env file."}]
    url = _FEEDS.get(topic, _FEEDS["top"])
    xml = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text
    root = ET.fromstring(xml)
    items = root.findall(".//item")[:count]
    return [
        {
            "title": item.findtext("title"),
            "description": item.findtext("description"),
            "link": item.findtext("link"),
            "published": item.findtext("pubDate"),
        }
        for item in items
    ]
