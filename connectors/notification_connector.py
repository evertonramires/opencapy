import os
from dotenv import load_dotenv
load_dotenv()

# Which kinds of chat messages raise a popup notification in the web chat.
# The kind is read from the emoji the codebase already prefixes every message
# with, so nothing needs to be threaded through the call sites; a message with
# no recognized prefix is ordinary conversation and falls under NOTIFY_CHAT.
# Each row: (env switch, default, message prefixes it covers).
NOTIFY_RULES = [
    ("NOTIFY_TOOL_CALLS", "false", ("🔧",)),          # ANNOUNCE_TOOL_CALLS chatter
    ("NOTIFY_ERRORS", "true", ("⚠️",)),               # ANNOUNCE_ERRORS reports
    ("NOTIFY_SYSTEM", "false", ("⚙️",)),              # wake-up / status lines
    ("NOTIFY_TASKS", "true", ("🕰️",)),                # scheduled task firings
    ("NOTIFY_ROUTINES", "true", ("♾️",)),             # recurring routine firings
    ("NOTIFY_CALENDAR", "true", ("📅",)),             # calendar daily check and events
    ("NOTIFY_TODOS", "true", ("👀", "🎉", "💬")),     # Vikunja watcher: new, completed, comment threads
    ("NOTIFY_DAILY_FOCUS", "true", ("🎯",)),          # morning focus message
    ("NOTIFY_DATE_NUDGE", "true", ("🗓️",)),           # daily due-date nudge
    ("NOTIFY_WEEKLY_REVIEW", "true", ("🧹", "🏆", "🧭")),  # stale sweep, wins, balance
    ("NOTIFY_AUTOPILOT", "true", ("🔎",)),            # autopilot research results
    ("NOTIFY_DSH", "true", ("🧠",)),                  # dsh agent session updates
    ("NOTIFY_CODER", "true", ("🧑‍💻",)),               # coding agent offers and reports
    ("NOTIFY_SPRINTS", "true", ("⏰", "⏳")),          # sprint start and time's-up check-ins
    ("NOTIFY_JOURNAL", "true", ("📓",)),              # evening journal ask and entries
    ("NOTIFY_APPROVALS", "true", ("⌛", "✏️")),        # approval drafts expiring / being reworked
    ("NOTIFY_USAGE", "true", ("🪫",)),                # usage window alerts and buffered work
    ("NOTIFY_QUESTIONS", "true", ("🤝",)),            # human-escalation questions
]


def _enabled(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in ["true", "1", "yes"]


def agent_notifications_enabled() -> bool:
    """Gates the send_notification tool itself: off means the agent is never
    offered the tool, so it can't interrupt on purpose at all."""
    return _enabled("NOTIFY_AGENT", "true")


def should_notify(message: str) -> bool:
    """Whether this chat message should also raise a popup notification.
    First matching prefix wins; anything unrecognized counts as conversation."""
    text = message.lstrip()
    for name, default, prefixes in NOTIFY_RULES:
        if text.startswith(prefixes):
            return _enabled(name, default)
    return _enabled("NOTIFY_CHAT", "true")
