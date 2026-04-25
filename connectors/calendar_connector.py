import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse, urlencode

import requests


_oauth_state_path = Path(__file__).resolve().parent.parent / "hood" / "calendar_oauth.json"
_env_path = Path(__file__).resolve().parent.parent / ".env"


def _read_dotenv_value(key: str) -> str:
    if not _env_path.exists():
        return ""
    for line in _env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _env_value(key: str, default: str = "") -> str:
    return _read_dotenv_value(key) or os.getenv(key, default)


_calendar_id = _env_value("CALENDAR_ID", "")


def _oauth_redirect_uri() -> str:
    chat_api_host = _env_value("CHAT_API_HOST", "http://localhost:8000").rstrip("/")
    return _env_value("CALENDAR_OAUTH_REDIRECT_URI", f"{chat_api_host}/oauth/calendar/callback")


def _read_oauth_data() -> dict:
    default = {"state": "", "refresh_token": "", "redirect_uri": ""}
    if not _oauth_state_path.exists():
        return default
    try:
        data = json.loads(_oauth_state_path.read_text())
        if isinstance(data, dict):
            return {
                "state": data.get("state", ""),
                "refresh_token": data.get("refresh_token", ""),
                "redirect_uri": data.get("redirect_uri", ""),
            }
    except Exception:
        pass
    return default


def _write_oauth_data(data: dict) -> None:
    _oauth_state_path.parent.mkdir(parents=True, exist_ok=True)
    _oauth_state_path.write_text(json.dumps(data))


def _save_oauth_state(state: str, redirect_uri: str = "") -> None:
    data = _read_oauth_data()
    data["state"] = state
    data["redirect_uri"] = redirect_uri
    _write_oauth_data(data)


def _load_oauth_refresh_token() -> str:
    refresh_token = _read_oauth_data().get("refresh_token", "")
    if refresh_token:
        return refresh_token
    return ""


def _save_oauth_refresh_token(refresh_token: str) -> None:
    data = _read_oauth_data()
    data["refresh_token"] = refresh_token
    _write_oauth_data(data)


def _oauth_network_hint(redirect_uri: str) -> str:
    host = (urlparse(redirect_uri).hostname or "").lower()
    if host in ["localhost", "127.0.0.1", "::1"]:
        return "Open the OAuth link in the same machine where this system is running, because callback host is localhost."
    return "Make sure the callback host is reachable using https requests from Google's servers for OAuth to work."


def create_calendar_oauth_session(redirect_uri: str = "") -> dict:
    client_id = _env_value("CALENDAR_OAUTH_CLIENT_ID", "")
    if not client_id:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Calendar OAuth client id is missing. Set CALENDAR_OAUTH_CLIENT_ID in .env.",
        }
    redirect_uri = redirect_uri or _oauth_redirect_uri()
    state = secrets.token_urlsafe(24)
    _save_oauth_state(state, redirect_uri)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    network_hint = _oauth_network_hint(redirect_uri)
    return {
        "status": "ok",
        "tool": "calendar",
        "message": f"Open the auth_url in a browser to authorize Google Calendar. {network_hint}",
        "auth_url": auth_url,
        "redirect_uri": redirect_uri,
        "network_hint": network_hint,
    }


def complete_calendar_oauth(code: str = "", state: str = "", error: str = "") -> dict:
    if error:
        return {
            "status": "error",
            "tool": "calendar",
            "message": f"Google OAuth returned an error: {error}",
        }
    if not code or not state:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Missing OAuth code or state.",
        }
    oauth_data = _read_oauth_data()
    expected_state = oauth_data.get("state", "")
    if not expected_state or state != expected_state:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Invalid OAuth state. Start auth again with /calendarauth.",
        }
    client_id = _env_value("CALENDAR_OAUTH_CLIENT_ID", "")
    client_secret = _env_value("CALENDAR_OAUTH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Calendar OAuth client settings are missing. Set CALENDAR_OAUTH_CLIENT_ID and CALENDAR_OAUTH_CLIENT_SECRET.",
        }
    redirect_uri = oauth_data.get("redirect_uri", "") or _oauth_redirect_uri()
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    data = response.json()
    if response.status_code != 200 or not data.get("access_token"):
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Failed to exchange OAuth code for token.",
            "details": data,
        }
    refresh_token = data.get("refresh_token", "")
    if refresh_token:
        _save_oauth_refresh_token(refresh_token)
    _save_oauth_state("", "")
    if refresh_token:
        return {
            "status": "ok",
            "tool": "calendar",
            "message": "Calendar OAuth validated. Refresh token saved to hood/calendar_oauth.json.",
            "scope": data.get("scope", ""),
        }
    if _load_oauth_refresh_token():
        return {
            "status": "ok",
            "tool": "calendar",
            "message": "Calendar OAuth validated. Existing refresh token from hood/calendar_oauth.json kept.",
            "scope": data.get("scope", ""),
        }
    return {
        "status": "error",
        "tool": "calendar",
        "message": "OAuth completed but no refresh token was returned.",
        "details": data,
    }


def _oauth_access_token() -> dict:
    client_id = _env_value("CALENDAR_OAUTH_CLIENT_ID", "")
    client_secret = _env_value("CALENDAR_OAUTH_CLIENT_SECRET", "")
    refresh_token = _load_oauth_refresh_token()
    if not client_id or not client_secret or not refresh_token:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Calendar OAuth is not configured. Set CALENDAR_OAUTH_CLIENT_ID and CALENDAR_OAUTH_CLIENT_SECRET in .env, then run /calendarauth to save refresh token in hood/calendar_oauth.json.",
        }
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    data = response.json()
    if response.status_code != 200 or not data.get("access_token"):
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Failed to get Google OAuth access token.",
            "details": data,
        }
    return {"status": "ok", "access_token": data["access_token"]}


def _calendar_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _calendar_url(calendar_id: str, event_id: str = "") -> str:
    encoded_calendar_id = quote(calendar_id, safe="")
    if event_id:
        encoded_event_id = quote(event_id, safe="")
        return f"https://www.googleapis.com/calendar/v3/calendars/{encoded_calendar_id}/events/{encoded_event_id}"
    return f"https://www.googleapis.com/calendar/v3/calendars/{encoded_calendar_id}/events"


def list_calendar_events(days_ahead: int = 7, max_results: int = 10) -> list[dict] | dict:
    calendar_id = _calendar_id
    if not calendar_id:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Calendar id is missing. Set CALENDAR_ID in .env or pass calendar_id.",
        }
    token_result = _oauth_access_token()
    if token_result["status"] == "error":
        return token_result
    now = datetime.now(timezone.utc)
    time_min = now.isoformat().replace("+00:00", "Z")
    time_max = (now + timedelta(days=days_ahead)).isoformat().replace("+00:00", "Z")
    response = requests.get(
        _calendar_url(calendar_id),
        headers=_calendar_headers(token_result["access_token"]),
        params={
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
        },
    )
    data = response.json()
    if response.status_code != 200:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Failed to list calendar events.",
            "details": data,
        }
    items = data.get("items", [])
    return [
        {
            "id": item["id"],
            "summary": item.get("summary"),
            "description": item.get("description"),
            "start": item["start"].get("dateTime", item["start"].get("date")),
            "end": item["end"].get("dateTime", item["end"].get("date")),
            "status": item.get("status"),
            "link": item.get("htmlLink"),
        }
        for item in items
    ]


def add_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
) -> dict:
    calendar_id = _calendar_id
    if not calendar_id:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Calendar id is missing. Set CALENDAR_ID in .env or pass calendar_id.",
        }
    token_result = _oauth_access_token()
    if token_result["status"] == "error":
        return token_result
    payload = {
        "summary": summary,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        payload["description"] = description
    response = requests.post(
        _calendar_url(calendar_id),
        headers=_calendar_headers(token_result["access_token"]),
        json=payload,
    )
    data = response.json()
    if response.status_code not in [200, 201]:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Failed to add calendar event.",
            "details": data,
        }
    return {
        "status": "ok",
        "message": "Calendar event created.",
        "event": {
            "id": data.get("id"),
            "summary": data.get("summary"),
            "start": data.get("start", {}).get("dateTime", data.get("start", {}).get("date")),
            "end": data.get("end", {}).get("dateTime", data.get("end", {}).get("date")),
            "link": data.get("htmlLink"),
        },
    }


def delete_calendar_event(event_id: str) -> dict:
    calendar_id = _calendar_id
    if not calendar_id:
        return {
            "status": "error",
            "tool": "calendar",
            "message": "Calendar id is missing. Set CALENDAR_ID in .env or pass calendar_id.",
        }
    token_result = _oauth_access_token()
    if token_result["status"] == "error":
        return token_result
    response = requests.delete(
        _calendar_url(calendar_id, event_id),
        headers=_calendar_headers(token_result["access_token"]),
    )
    if response.status_code in [200, 204]:
        return {
            "status": "ok",
            "message": "Calendar event deleted.",
            "event_id": event_id,
        }
    data = response.json() if response.text else {}
    return {
        "status": "error",
        "tool": "calendar",
        "message": "Failed to delete calendar event.",
        "details": data,
    }