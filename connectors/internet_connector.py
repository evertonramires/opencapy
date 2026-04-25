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

def browse_internet(url: str) -> dict:
    if not _is_allowed(url):
        return {"status": 403, "body": "Domain not in whitelist."}
    response = requests.get(url)
    return {"status": response.status_code, "body": response.text}

def check_internet_connection() -> dict:
    response = requests.get("https://cloudflare.com/cdn-cgi/trace")
    trace = {}
    for line in response.text.strip().splitlines():
        key, value = line.split("=", 1)
        trace[key] = value
    return {
        "connected": response.ok or response.status_code == 200,
        "connection_state": "online" if (response.ok or response.status_code == 200) else "offline",
        "check_url": "https://cloudflare.com/cdn-cgi/trace",
        "http_status_code": response.status_code,
        "http_ok": response.ok,
        "public_ip": trace.get("ip"),
        "client_country_code": trace.get("loc"),
        "edge_datacenter": trace.get("colo"),
        "http_protocol": trace.get("http"),
        "tls_version": trace.get("tls"),
        "using_warp": trace.get("warp") == "on",
        "using_gateway": trace.get("gateway") == "on",
        "user_agent": trace.get("uag"),
        "trace_timestamp": trace.get("ts"),
        "trace": trace,
    }
