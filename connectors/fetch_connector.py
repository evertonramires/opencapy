import json
import os
import requests
from urllib.parse import urlparse

_whitelist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hood", "whitelist.json")

def _ensure_whitelist():
    if not os.path.exists(_whitelist_path):
        with open(_whitelist_path, "w") as f:
            json.dump([], f)

def _is_allowed(url: str) -> bool:
    _ensure_whitelist()
    host = urlparse(url).hostname or ""
    with open(_whitelist_path) as f:
        whitelist = json.load(f)
    return any(host == domain or host.endswith("." + domain) for domain in whitelist)

def fetch_url(url: str, method: str, headers: dict, body: str) -> dict:
    if not _is_allowed(url):
        return {"status": 403, "body": "Domain not in whitelist."}
    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers or {},
        data=body or None,
    )
    return {"status": response.status_code, "body": response.text}
