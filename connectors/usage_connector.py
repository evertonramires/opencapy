import json
import os
import time
from datetime import datetime
import requests
from dotenv import load_dotenv
from connectors.claude_code_connector import claude_code_enabled, read_state, write_state
load_dotenv()


USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CACHE_SECONDS = 60
_cached_usage = {}
_cached_at = 0


def _credentials_path() -> str:
    return os.path.join(os.path.expanduser(os.getenv("CLAUDE_CODE_CONFIG_DIR", "~/.claude")), ".credentials.json")


def _access_token() -> str:
    # The CLI refreshes this file on every run, and Open Capy runs it constantly, so it stays fresh on its own
    with open(_credentials_path()) as f:
        return json.load(f)["claudeAiOauth"]["accessToken"]


def _resets_in(resets_at: str) -> str:
    seconds = int(datetime.fromisoformat(resets_at).timestamp() - time.time())
    if seconds <= 0:
        return "now"
    if seconds >= 86400:
        return f"{seconds // 86400}d{(seconds % 86400) // 3600}h"
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60}m"
    return f"{seconds // 60}m"


def _cache(usage: dict) -> dict:
    # Errors are cached too, otherwise a failing endpoint gets retried on every heartbeat
    global _cached_usage, _cached_at
    _cached_usage = usage
    _cached_at = time.time()
    return usage


def claude_usage() -> dict:
    if not claude_code_enabled():
        return {
            "status": "error",
            "tool": "usage",
            "message": "Claude Code is disabled. To enable it, set ENABLE_CLAUDE_CODE=true in your .env file.",
        }
    if _cached_usage and time.time() - _cached_at < CACHE_SECONDS:
        return _cached_usage
    try:
        response = requests.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {_access_token()}",
                "anthropic-beta": "oauth-2025-04-20",
            },
            timeout=30,
        )
    except requests.RequestException as e:
        return _cache({"status": "error", "tool": "usage", "message": f"Anthropic usage API is unreachable: {e}"})
    if response.status_code == 401:
        return _cache({
            "status": "error",
            "tool": "usage",
            "message": "The Claude Code CLI login has expired. Run 'claude' once and sign in.",
        })
    if not response.ok:
        return _cache({
            "status": "error",
            "tool": "usage",
            "message": f"The Anthropic usage API answered {response.status_code}, this is usually temporary.",
            "details": response.text,
        })
    data = response.json()
    five_hour = data["five_hour"]
    seven_day = data["seven_day"]
    return _cache({
        "status": "success",
        "five_hour_percent": five_hour["utilization"],
        "five_hour_resets_at": five_hour["resets_at"],
        "five_hour_resets_in": _resets_in(five_hour["resets_at"]),
        "seven_day_percent": seven_day["utilization"],
        "seven_day_resets_at": seven_day["resets_at"],
        "seven_day_resets_in": _resets_in(seven_day["resets_at"]),
    })


def buffer_threshold_percent() -> int:
    return int(os.getenv("USAGE_BUFFER_THRESHOLD_PERCENT", "80"))


def buffering_active() -> bool:
    usage = claude_usage()
    if usage.get("status") != "success":
        return False
    return usage["five_hour_percent"] >= buffer_threshold_percent()


def window_resets_at() -> int:
    """Epoch second the current 5 hour window resets, used to stamp buffered work
    so it waits for the next window. Zero when usage is unavailable, which makes
    buffered items due immediately rather than stranding them."""
    usage = claude_usage()
    if usage.get("status") != "success":
        return 0
    # The API jitters this by a fraction of a second per call, so round to the minute
    # (resets land on the hour) to keep it usable as the once per window alert key
    return int(round(datetime.fromisoformat(usage["five_hour_resets_at"]).timestamp() / 60) * 60)


def usage_alert_message() -> str:
    """Returns the threshold warning once per 5 hour window, keyed on the window's
    reset time, so the user is told but not nagged every heartbeat."""
    if not buffering_active():
        return ""
    resets_at = window_resets_at()
    state = read_state()
    if state.get("notified_for_reset") == resets_at:
        return ""
    state["notified_for_reset"] = resets_at
    write_state(state)
    usage = claude_usage()
    return (
        f"Claude 5 hour window is at {usage['five_hour_percent']}%, resetting in {usage['five_hour_resets_in']} "
        f"({usage['five_hour_resets_at'][:16].replace('T', ' ')} UTC). Background work waits until then, "
        "and chat falls back to the configured LLM."
    )
