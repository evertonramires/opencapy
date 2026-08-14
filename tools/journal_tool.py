from datetime import datetime, timedelta, timezone

from connectors.tools_connector import notify_tool_use
from connectors.journal_connector import (
    journal_enabled,
    set_plan as connector_set_plan,
    add_wins as connector_add_wins,
    read_journal as connector_read_journal,
)

def record_tomorrow_plan(tasks: list[str]) -> dict:
    notify_tool_use(f"🔧📓🌙 Journal tool used to record tomorrow's plan ({len(tasks)} task(s)).")
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    return connector_set_plan(tomorrow, tasks, "user")

def record_today_plan(tasks: list[str], chosen_by_capy: bool = False) -> dict:
    notify_tool_use(f"🔧📓☀️ Journal tool used to record today's plan ({len(tasks)} task(s)).")
    today = datetime.now(timezone.utc).date().isoformat()
    return connector_set_plan(today, tasks, "capy" if chosen_by_capy else "user")

def record_daily_wins(wins: list[str]) -> dict:
    notify_tool_use(f"🔧📓🏆 Journal tool used to record {len(wins)} win(s).")
    today = datetime.now(timezone.utc).date().isoformat()
    return connector_add_wins(today, wins)

def read_journal(date: str = "") -> dict:
    notify_tool_use(f"🔧📓🔍 Journal tool used to read the journal.")
    return connector_read_journal(date)

if journal_enabled():
    record_tomorrow_plan_tool = {
        "type": "function",
        "function": {
            "name": "record_tomorrow_plan",
            "description": (
                "Record the first tasks the user wants to do tomorrow, in their own words. Call this the moment they answer the evening "
                "journal ask — a partial answer counts, two tasks are worth recording without waiting for a third, and at most three are "
                "kept. Tomorrow morning's focus message is built from this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Up to three tasks, in the order they named them, kept in their wording.",
                    },
                },
                "required": ["tasks"],
            },
        },
    }

    record_today_plan_tool = {
        "type": "function",
        "function": {
            "name": "record_today_plan",
            "description": (
                "Record or change today's three-task plan. Used two ways: when the user reshuffles their day mid-day (their choice, "
                "chosen_by_capy false), and by the morning fallback when they never answered the evening ask and you picked three for "
                "them (chosen_by_capy true). A plan the user chose is never overwritten by a Capy pick."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Up to three tasks in the order they should be done.",
                    },
                    "chosen_by_capy": {
                        "type": "boolean",
                        "description": "True only when you picked because the user never answered; false whenever the tasks are their own choice.",
                    },
                },
                "required": ["tasks"],
            },
        },
    }

    record_daily_wins_tool = {
        "type": "function",
        "function": {
            "name": "record_daily_wins",
            "description": (
                "Record things the user achieved today, verbatim in their words, however small. Call it whenever they name something done "
                "— in the evening journal answer or any time they mention finishing something worth keeping. Appends rather than replaces, "
                "so an evening answered across two messages still ends up whole. The record also lands on that day's page in the knowledge base."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wins": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The achievements, one string each, in the user's own words.",
                    },
                },
                "required": ["wins"],
            },
        },
    }

    read_journal_tool = {
        "type": "function",
        "function": {
            "name": "read_journal",
            "description": "Read a day's journal entry: the three-task plan, who chose it, and the recorded wins. Defaults to today.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Optional ISO date (e.g. '2026-08-14'). Empty means today.",
                    },
                },
                "required": [],
            },
        },
    }
