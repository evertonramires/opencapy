import json
import os
from urllib.parse import urlparse

_whitelist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hood", "whitelist.json")

def _ensure_whitelist():
    if not os.path.exists(_whitelist_path):
        with open(_whitelist_path, "w") as f:
            json.dump([], f)

def _extract_domain(raw: str) -> str:
    raw = raw.strip().strip("\"'")
    return urlparse(raw).hostname or raw

def add_to_whitelist(raw: str) -> str:
    _ensure_whitelist()
    domain = _extract_domain(raw)
    with open(_whitelist_path) as f:
        whitelist = json.load(f)
    if domain not in whitelist:
        whitelist.append(domain)
        with open(_whitelist_path, "w") as f:
            json.dump(whitelist, f, indent=4)
    return domain

def remove_from_whitelist(raw: str) -> str | None:
    _ensure_whitelist()
    domain = _extract_domain(raw)
    with open(_whitelist_path) as f:
        whitelist = json.load(f)
    if domain not in whitelist:
        return None
    whitelist = [d for d in whitelist if d != domain]
    with open(_whitelist_path, "w") as f:
        json.dump(whitelist, f, indent=4)
    return domain

def read_whitelist() -> list[str]:
    _ensure_whitelist()
    with open(_whitelist_path) as f:
        return json.load(f)
