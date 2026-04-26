import os
import re
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests


def websearch_enabled() -> bool:
    websearch_env = os.getenv("ENABLE_WEBSEARCH", "false").lower() in ["true", "1", "yes"]
    internet_env = os.getenv("ENABLE_INTERNET", "false").lower() in ["true", "1", "yes"]
    return (websearch_env and internet_env)



def web_search(query: str, count: int = 5) -> list[dict]:
    if not websearch_enabled():
        return [{"status": "error", "message": "Websearch tool is disabled. To enable it, set ENABLE_WEBSEARCH=true and ENABLE_INTERNET=true in your .env file."}]

    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text

    matches = re.findall(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    results = []
    for href, raw_title in matches[:count]:
        title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        if "uddg=" in href:
            params = parse_qs(urlparse(href).query)
            href = unquote(params.get("uddg", [href])[0])
        results.append({"title": title, "link": href})

    if results:
        return results

    # Fallback keeps basic search usable when DDG HTML endpoint returns anti-bot pages.
    payload = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
        headers={"User-Agent": "Mozilla/5.0"},
    ).json()

    for item in payload.get("Results", []):
        results.append({"title": item.get("Text"), "link": item.get("FirstURL")})

    for item in payload.get("RelatedTopics", []):
        topics = item.get("Topics")
        if topics:
            for topic in topics:
                results.append({"title": topic.get("Text"), "link": topic.get("FirstURL")})
            continue
        results.append({"title": item.get("Text"), "link": item.get("FirstURL")})

    return results[:count]
