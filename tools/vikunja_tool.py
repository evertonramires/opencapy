from connectors.tools_connector import notify_tool_use
from connectors.vikunja_connector import (
    add_todo as connector_add_todo,
    list_todos as connector_list_todos,
    complete_todo as connector_complete_todo,
    delete_todo as connector_delete_todo,
    update_todo as connector_update_todo,
    add_subtasks as connector_add_subtasks,
    append_todo_description as connector_append_todo_description,
    add_todo_comment as connector_add_todo_comment,
    list_todo_comments as connector_list_todo_comments,
    rename_todo as connector_rename_todo,
    list_todo_projects as connector_list_todo_projects,
    triage_todo as connector_triage_todo,
    comments_enabled,
    retitle_enabled,
    subtasks_enabled,
    triage_enabled,
)

def add_todo(title: str, due_date: str = "", description: str = "", priority: int = 0, project_id: int = 0) -> dict:
    notify_tool_use(f"🔧✅➕ Vikunja tool used to add to-do '{title}'.")
    return connector_add_todo(title, due_date, description, priority, project_id)

def list_todos(include_done: bool = False) -> list[dict] | dict:
    notify_tool_use(f"🔧✅🔍 Vikunja tool used to list to-dos.")
    return connector_list_todos(include_done)

def complete_todo(todo_id: int) -> dict:
    notify_tool_use(f"🔧✅☑️ Vikunja tool used to complete to-do {todo_id}.")
    return connector_complete_todo(todo_id)

def delete_todo(todo_id: int) -> dict:
    notify_tool_use(f"🔧✅❌ Vikunja tool used to delete to-do {todo_id}.")
    return connector_delete_todo(todo_id)

def update_todo(todo_id: int, title: str = "", description: str = "", due_date: str = "", start_date: str = "", priority: int = -1) -> dict:
    notify_tool_use(f"🔧✅✏️ Vikunja tool used to update to-do {todo_id}.")
    return connector_update_todo(todo_id, title, description, due_date, start_date, priority)

def add_subtasks(parent_todo_id: int, titles: list[str]) -> dict:
    notify_tool_use(f"🔧✅🪜 Vikunja tool used to add {len(titles)} subtasks to to-do {parent_todo_id}.")
    return connector_add_subtasks(parent_todo_id, titles)

def list_todo_projects() -> list[dict] | dict:
    notify_tool_use(f"🔧✅📁 Vikunja tool used to list to-do projects.")
    return connector_list_todo_projects()

def add_todo_context(todo_id: int, notes: str) -> dict:
    notify_tool_use(f"🔧✅🔎 Vikunja tool used to add research notes to to-do {todo_id}.")
    return connector_append_todo_description(todo_id, notes)

def reply_on_todo(todo_id: int, message: str) -> dict:
    notify_tool_use(f"🔧✅💬 Vikunja tool used to reply on to-do {todo_id}.")
    return connector_add_todo_comment(todo_id, message)

def read_todo_comments(todo_id: int) -> dict:
    notify_tool_use(f"🔧✅💬 Vikunja tool used to read the comments on to-do {todo_id}.")
    return connector_list_todo_comments(todo_id)

def improve_todo_title(todo_id: int, title: str) -> dict:
    notify_tool_use(f"🔧✅✒️ Vikunja tool used to sharpen the title of to-do {todo_id}.")
    return connector_rename_todo(todo_id, title)

def triage_todo(todo_id: int, quadrant: str, extra_labels: list[str] = [], reason: str = "") -> dict:
    notify_tool_use(f"🔧✅🧭 Vikunja tool used to triage to-do {todo_id} as '{quadrant}'.")
    return connector_triage_todo(todo_id, quadrant, extra_labels, reason)

add_todo_tool = {
    "type": "function",
    "function": {
        "name": "add_todo",
        "description": "Add a to-do item to the user's Vikunja to-do list. Use this for things the user wants to remember to do, like shopping items, chores, or errands. Add it immediately with sensible defaults instead of asking clarifying questions first; details can always be added later.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The to-do item title (e.g. 'Buy groceries').",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date as an ISO8601 UTC timestamp (e.g. '2026-07-12T18:00:00Z'). Leave empty if the to-do has no due date.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional longer description with extra details.",
                },
                "priority": {
                    "type": "integer",
                    "description": "Optional priority from 0 (unset) to 5 (urgent). Use 0 unless the user mentions urgency.",
                },
                "project_id": {
                    "type": "integer",
                    "description": "Optional Vikunja project id to add the to-do to. Use 0 for the default project. Use list_todo_projects to find project ids.",
                },
            },
            "required": ["title"],
        },
    },
}

list_todos_tool = {
    "type": "function",
    "function": {
        "name": "list_todos",
        "description": "List the user's to-do items from Vikunja with their ids, due dates, and priorities.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_done": {
                    "type": "boolean",
                    "description": "Whether to include already completed to-dos. Defaults to false (only pending to-dos).",
                },
            },
            "required": [],
        },
    },
}

complete_todo_tool = {
    "type": "function",
    "function": {
        "name": "complete_todo",
        "description": "Mark a to-do item as done in Vikunja by its id. Use list_todos to find the id.",
        "parameters": {
            "type": "object",
            "properties": {
                "todo_id": {
                    "type": "integer",
                    "description": "The id of the to-do to mark as done.",
                },
            },
            "required": ["todo_id"],
        },
    },
}

delete_todo_tool = {
    "type": "function",
    "function": {
        "name": "delete_todo",
        "description": "Permanently delete a to-do item from Vikunja by its id. Prefer complete_todo when the user finished something; only delete when they want it removed.",
        "parameters": {
            "type": "object",
            "properties": {
                "todo_id": {
                    "type": "integer",
                    "description": "The id of the to-do to delete.",
                },
            },
            "required": ["todo_id"],
        },
    },
}

update_todo_tool = {
    "type": "function",
    "function": {
        "name": "update_todo",
        "description": "Update a to-do in Vikunja: set or change its due date, start date, title, description, or priority. Use this when the user gives a date for an existing to-do. Start and due dates make the Gantt timeline view work.",
        "parameters": {
            "type": "object",
            "properties": {
                "todo_id": {
                    "type": "integer",
                    "description": "The id of the to-do to update. Use list_todos to find it.",
                },
                "title": {
                    "type": "string",
                    "description": "Optional new title. Leave empty to keep the current one.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional new description. Leave empty to keep the current one.",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date as an ISO8601 UTC timestamp (e.g. '2026-07-17T18:00:00Z'). Leave empty to keep the current one.",
                },
                "start_date": {
                    "type": "string",
                    "description": "Optional start date as an ISO8601 UTC timestamp, shown in the Gantt view. Leave empty to keep the current one.",
                },
                "priority": {
                    "type": "integer",
                    "description": "Optional priority from 0 (unset) to 5 (urgent). Use -1 to keep the current one.",
                },
            },
            "required": ["todo_id"],
        },
    },
}

if subtasks_enabled():
    add_subtasks_tool = {
        "type": "function",
        "function": {
            "name": "add_subtasks",
            "description": "Break a Vikunja to-do into subtasks (small concrete steps). Each subtask title is automatically prefixed with the parent's name and step number (e.g. '[ change car tyres - 1 ] lift car'), so pass only the bare step titles. The parent's progress bar fills automatically as subtasks get done, which the user finds motivating. Use this whenever a to-do is really a multi-step project. Keep steps small and actionable, 3 to 6 of them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_todo_id": {
                        "type": "integer",
                        "description": "The id of the to-do to break down. Use list_todos to find it.",
                    },
                    "titles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The subtask titles, in the order they should be done, each a small concrete step (e.g. 'Find the workshop phone number').",
                    },
                },
                "required": ["parent_todo_id", "titles"],
            },
        },
    }

add_todo_context_tool = {
    "type": "function",
    "function": {
        "name": "add_todo_context",
        "description": "Write research findings into a Vikunja to-do so the work is there when the user opens it: phone numbers, addresses, opening hours, prices, links, a drafted message. Everything the user wrote themselves is preserved, and re-running replaces your previous notes instead of duplicating them. Use short HTML (<p>, <ul><li>, <a href>, <b>) since Vikunja renders descriptions as HTML.",
        "parameters": {
            "type": "object",
            "properties": {
                "todo_id": {
                    "type": "integer",
                    "description": "The id of the to-do to add context to.",
                },
                "notes": {
                    "type": "string",
                    "description": "The findings as short HTML. Lead with the single most useful fact, keep it scannable, and end with the concrete next step.",
                },
            },
            "required": ["todo_id", "notes"],
        },
    },
}

if comments_enabled():
    reply_on_todo_tool = {
        "type": "function",
        "function": {
            "name": "reply_on_todo",
            "description": "Post a reply in a Vikunja to-do's own comment thread. The user comments on their to-dos to steer them, and answering there keeps the whole conversation attached to the task instead of scrolling away in chat. Use this whenever you answer a comment, and whenever you change a task because of one, so the reason is recorded next to the task. Short HTML (<p>, <ul><li>, <a href>, <b>), a few sentences at most. Your replies are signed automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "integer",
                        "description": "The id of the to-do to comment on.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The reply as short HTML. Answer the point that was raised and say plainly what you changed or found, no preamble.",
                    },
                },
                "required": ["todo_id", "message"],
            },
        },
    }

    read_todo_comments_tool = {
        "type": "function",
        "function": {
            "name": "read_todo_comments",
            "description": "Read the comment thread on a Vikunja to-do, oldest first, with each comment marked as written by you or by the user. Use it to catch up on what has already been discussed about a task before acting on it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "integer",
                        "description": "The id of the to-do whose comments you want to read.",
                    },
                },
                "required": ["todo_id"],
            },
        },
    }

if retitle_enabled():
    improve_todo_title_tool = {
        "type": "function",
        "function": {
            "name": "improve_todo_title",
            "description": (
                "Rewrite a Vikunja to-do's title so it is easier to actually start. A title captured in a hurry is often a vague noun "
                "('dentist', 'etsy thing'), and a vague title is a task the user has to re-decide every time they look at the list. "
                "Rewrite it as the first concrete action instead. Rules: open with a plain verb; name the very first physical step, not the "
                "outcome; keep every specific the user gave you and invent nothing, no names, prices, places or times they didn't write; "
                "eight words or fewer; sentence case; no emoji, no exclamation marks, no motivational adjectives; write in the same language "
                "the user used. 'dentist' becomes 'Call the dentist to book a cleaning'; 'cancel the gym membership' is already an action, so "
                "leave it alone. Skip titles that are already a clear action, and never use this to record progress or notes, that is what "
                "add_todo_context and reply_on_todo are for. The original title is kept so the user can undo it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "integer",
                        "description": "The id of the to-do to rename.",
                    },
                    "title": {
                        "type": "string",
                        "description": "The rewritten title: one concrete action, eight words or fewer, in the user's own language and using only facts they gave.",
                    },
                },
                "required": ["todo_id", "title"],
            },
        },
    }

if triage_enabled():
    triage_todo_tool = {
        "type": "function",
        "function": {
            "name": "triage_todo",
            "description": (
                "File a Vikunja to-do into the user's four boxes and tag what else is true about it. Run this on every to-do that has no "
                "quadrant label yet. Two independent axes decide the box. IMPORTANT means it moves something the user actually cares about "
                "forward, or there are real consequences if it never happens; a task can be loud and still not be important. URGENT means "
                "there is time pressure on it right now, a deadline, an appointment, something that expires or blocks someone else; a task "
                "can matter enormously and not be urgent at all, and those are the ones that quietly never get done.\n"
                "Then ask three questions in this order, because the order is the whole point: does this really need to be done at all, "
                "before anything else, since there is no sense automating or delegating something that should simply not exist; if it must "
                "happen, can someone or something else do it, an AI, a person the user could hire, or a product they could just buy; and only "
                "then, does it have to happen now.\n"
                "Answer the first with 'not-needed' when you genuinely doubt it needs doing, the second with 'ai-can-do', 'hire-out' or "
                "'buy-instead', and the third by setting a due date with update_todo rather than a label. If it would take under two minutes, "
                "label it 'two-minute' and don't route it to anyone, doing it is cheaper than delegating it.\n"
                "Add extra labels only when clearly true, never more than three, and never guess a context or an energy level you have no "
                "evidence for. 'drop' and 'not-needed' are proposals, not decisions: they raise a button for the user and you must never "
                "delete anything yourself, never lecture about the task, and never imply they were wrong to have written it down."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "integer",
                        "description": "The id of the to-do to triage.",
                    },
                    "quadrant": {
                        "type": "string",
                        "enum": ["do", "schedule", "delegate", "drop"],
                        "description": (
                            "Which box it belongs in. 'do' is urgent and important, handle it personally and soon. 'schedule' is important "
                            "but not urgent, the quadrant worth protecting, so give it a date. 'delegate' is urgent but not important, it "
                            "wants to come off the user's plate. 'drop' is neither and is only ever a suggestion."
                        ),
                    },
                    "extra_labels": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "not-needed", "ai-can-do", "hire-out", "buy-instead", "project", "two-minute",
                                "low-energy", "deep-focus", "@computer", "@home", "@errands", "@calls", "@waiting-for",
                            ],
                        },
                        "description": (
                            "At most three, and only what is clearly true. 'project' means it needs more than one step, so follow it with "
                            "add_subtasks. 'two-minute' means it is faster to just do than to plan. 'low-energy' is doable while depleted, "
                            "'deep-focus' needs a good head. The @ labels are where or with what it can be done, and '@waiting-for' is for "
                            "anything now sitting with someone else."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "One short sentence on why, in the user's own language. Saved on the task only when you propose dropping it, "
                            "since that is the verdict they will want to question later."
                        ),
                    },
                },
                "required": ["todo_id", "quadrant"],
            },
        },
    }

list_todo_projects_tool = {
    "type": "function",
    "function": {
        "name": "list_todo_projects",
        "description": "List the Vikunja projects (to-do lists) with their ids, useful to pick a project_id for add_todo.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
