from connectors.tools_connector import notify_tool_use
from connectors.coder_connector import (
    coder_enabled,
    offer_coding_work as connector_offer_coding_work,
    read_coding_work as connector_read_coding_work,
)

def offer_coding_work(todo_id: int, goal: str) -> dict:
    notify_tool_use(f"🔧🧑‍💻➕ Coder tool used to offer a coding agent for to-do {todo_id}.")
    return connector_offer_coding_work(todo_id, goal)

def list_coding_work() -> dict:
    notify_tool_use(f"🔧🧑‍💻🔍 Coder tool used to list coding offers and jobs.")
    return connector_read_coding_work()

if coder_enabled():
    offer_coding_work_tool = {
        "type": "function",
        "function": {
            "name": "offer_coding_work",
            "description": (
                "Offer to put a Claude Code coding agent on a to-do. Use this for the ai-can-do tasks that plain research can't cover: "
                "writing or changing code, working in a repo, running shell commands, or doing anything on one of the user's machines. "
                "Plain research — finding facts, comparing options, drafting text — stays with queue_task_work and needs no offer. "
                "This tool only OFFERS: a button goes to the user and absolutely nothing runs until they tap it, because the coding agent "
                "holds a real shell. Never present the offer as something already started."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "integer",
                        "description": "The id of the to-do the agent would work on.",
                    },
                    "goal": {
                        "type": "string",
                        "description": "One concrete sentence of what the agent should build, fix or set up — the agent starts from this, so name the outcome, not the activity.",
                    },
                },
                "required": ["todo_id", "goal"],
            },
        },
    }

    list_coding_work_tool = {
        "type": "function",
        "function": {
            "name": "list_coding_work",
            "description": "See the coding agent's plate: offers waiting on the user, queued and running jobs, and how many of today's runs are left.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
