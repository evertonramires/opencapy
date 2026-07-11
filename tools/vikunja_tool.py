from connectors.tools_connector import notify_tool_use
from connectors.vikunja_connector import (
    add_todo as connector_add_todo,
    list_todos as connector_list_todos,
    complete_todo as connector_complete_todo,
    delete_todo as connector_delete_todo,
    list_todo_projects as connector_list_todo_projects,
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

def list_todo_projects() -> list[dict] | dict:
    notify_tool_use(f"🔧✅📁 Vikunja tool used to list to-do projects.")
    return connector_list_todo_projects()

add_todo_tool = {
    "type": "function",
    "function": {
        "name": "add_todo",
        "description": "Add a to-do item to the user's Vikunja to-do list. Use this for things the user wants to remember to do, like shopping items, chores, or errands.",
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
