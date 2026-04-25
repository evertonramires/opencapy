from connectors.tools_connector import notify_tool_use
from connectors.calendar_connector import (
    list_calendar_events as connector_list_calendar_events,
    add_calendar_event as connector_add_calendar_event,
    delete_calendar_event as connector_delete_calendar_event,
)


def list_calendar_events(days_ahead: int = 7, max_results: int = 10) -> list[dict] | dict:
    notify_tool_use("🔧📅🔍 Calendar tool used to list events.")
    return connector_list_calendar_events(days_ahead, max_results)


def add_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
) -> dict:
    notify_tool_use(f"🔧📅➕ Calendar tool used to add event: {summary}")
    return connector_add_calendar_event(summary, start_time, end_time, description)


def delete_calendar_event(event_id: str) -> dict:
    notify_tool_use(f"🔧📅❌ Calendar tool used to delete event: {event_id}.")
    return connector_delete_calendar_event(event_id)


list_calendar_events_tool = {
    "type": "function",
    "function": {
        "name": "list_calendar_events",
        "description": "List upcoming events from the calendar. Be aware of timezone differences.",
        "parameters": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "How many days ahead to search starting from the current time.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to return.",
                },
            },
        },
    },
}


add_calendar_event_tool = {
    "type": "function",
    "function": {
        "name": "add_calendar_event",
        "description": "Create an event in the calendar. Always be explicit about timezone when choosing event times and pass ISO8601 timestamps with an explicit offset or Z suffix.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Event title/summary.",
                },
                "start_time": {
                    "type": "string",
                    "description": "Event start as an ISO8601 timestamp with explicit timezone. Prefer the user's local timezone offset when known. Examples: 2026-04-25T15:00:00+01:00 or 2026-04-25T14:00:00Z.",
                },
                "end_time": {
                    "type": "string",
                    "description": "Event end as an ISO8601 timestamp with explicit timezone. Use the same timezone basis as start_time. Examples: 2026-04-25T16:00:00+01:00 or 2026-04-25T15:00:00Z.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional event description.",
                },
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
}


delete_calendar_event_tool = {
    "type": "function",
    "function": {
        "name": "delete_calendar_event",
        "description": "Delete an event from the calendar by event id. ",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Event id to delete.",
                },
            },
            "required": ["event_id"],
        },
    },
}