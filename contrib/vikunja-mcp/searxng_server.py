"""SearXNG web-search MCP server for dsh agent sessions (stdio transport).

dsh ships search providers for DeepSeek/Exa/Perplexity only, so the self-hosted
SearXNG instances are bridged in as MCP tools instead. Same venv as the vikunja
server:

    SEARXNG_URL=https://searxng.example.internal \
    SEARXNG_PRIVATE_URL=https://searxng-tor.example.internal \
    .venv/bin/python searxng_server.py

The private instance routes engine traffic through Tor and is slow by design
(30-60s per query) — reach for it only when asked to search privately.
"""
import os

import requests
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("searxng")

def _search(base_url: str, query: str, max_results: int, timeout: int) -> list:
    response = requests.get(
        f"{base_url.rstrip('/')}/search",
        params={"q": query, "format": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    return [{
        "title": r.get("title") or "",
        "url": r.get("url") or "",
        "snippet": (r.get("content") or "")[:500],
        "engine": r.get("engine") or "",
    } for r in results[:max(1, min(max_results, 20))]]

@mcp.tool()
def web_search(query: str, max_results: int = 8) -> list:
    """Search the web (self-hosted SearXNG metasearch). Returns titles, URLs and
    snippets; follow up with web_fetch on the promising URLs to read the pages."""
    return _search(os.environ["SEARXNG_URL"], query, max_results, timeout=30)

@mcp.tool()
def web_search_private(query: str, max_results: int = 8) -> list:
    """Search the web through the Tor-routed SearXNG instance. Slow (30-60s) by
    design — use only when the search itself should not be attributable; for
    ordinary research use web_search."""
    private = os.environ.get("SEARXNG_PRIVATE_URL", "").strip()
    if not private:
        return [{"error": "SEARXNG_PRIVATE_URL is not configured; use web_search instead."}]
    return _search(private, query, max_results, timeout=90)

if __name__ == "__main__":
    mcp.run()
