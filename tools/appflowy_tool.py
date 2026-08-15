from connectors.tools_connector import notify_tool_use
from connectors.appflowy_connector import (
    list_appflowy_databases as connector_list_appflowy_databases,
    list_appflowy_rows as connector_list_appflowy_rows,
    add_appflowy_row as connector_add_appflowy_row,
    update_appflowy_row as connector_update_appflowy_row,
    list_appflowy_pages as connector_list_appflowy_pages,
    read_appflowy_page as connector_read_appflowy_page,
    add_appflowy_page as connector_add_appflowy_page,
    delete_appflowy_page as connector_delete_appflowy_page,
    append_appflowy_text as connector_append_appflowy_text,
)

def list_appflowy_databases() -> list[dict] | dict:
    notify_tool_use("🔧📓🗂️ AppFlowy tool used to list databases.")
    return connector_list_appflowy_databases()

def list_appflowy_rows(database_id: str = "", limit: int = 25) -> list[dict] | dict:
    notify_tool_use("🔧📓🔍 AppFlowy tool used to list database rows.")
    return connector_list_appflowy_rows(database_id, limit)

def add_appflowy_row(fields: dict, database_id: str = "") -> dict:
    notify_tool_use("🔧📓➕ AppFlowy tool used to add a database row.")
    return connector_add_appflowy_row(fields, database_id)

def update_appflowy_row(row_key: str, fields: dict, database_id: str = "") -> dict:
    notify_tool_use(f"🔧📓✏️ AppFlowy tool used to update row '{row_key}'.")
    return connector_update_appflowy_row(row_key, fields, database_id)

def list_appflowy_pages() -> dict:
    notify_tool_use("🔧📓📚 AppFlowy tool used to list pages.")
    return connector_list_appflowy_pages()

def read_appflowy_page(view_id: str) -> dict:
    notify_tool_use(f"🔧📓📖 AppFlowy tool used to read page {view_id}.")
    return connector_read_appflowy_page(view_id)

def delete_appflowy_page(view_id: str) -> dict:
    notify_tool_use(f"🔧📓🗑️ AppFlowy tool used to move page {view_id} to trash.")
    return connector_delete_appflowy_page(view_id)

def add_appflowy_page(title: str, parent_view_id: str) -> dict:
    notify_tool_use(f"🔧📓📄 AppFlowy tool used to create page '{title}'.")
    return connector_add_appflowy_page(title, parent_view_id)

def append_appflowy_text(view_id: str, text: str) -> dict:
    notify_tool_use(f"🔧📓✍️ AppFlowy tool used to append text to page {view_id}.")
    # Signed in the tool wrapper, not the connector, so code-composed writes like
    # the journal sync stay clean while model-authored page content carries its author
    from connectors.llm_connector import authoring_model
    model = authoring_model()
    if model:
        text = f"{text}\n· {model}"
    return connector_append_appflowy_text(view_id, text)

list_appflowy_databases_tool = {
    "type": "function",
    "function": {
        "name": "list_appflowy_databases",
        "description": "List the databases (grids, boards, calendars) in the user's AppFlowy knowledge base, with their ids. Use this to find a database id before listing or adding rows. AppFlowy is the knowledge base and notes system; to-dos live in Vikunja instead.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

list_appflowy_rows_tool = {
    "type": "function",
    "function": {
        "name": "list_appflowy_rows",
        "description": "List rows of an AppFlowy database, with each row's cell values under their human field names.",
        "parameters": {
            "type": "object",
            "properties": {
                "database_id": {
                    "type": "string",
                    "description": "The AppFlowy database id. Leave empty to use the default database from the configuration. Use list_appflowy_databases to find ids.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return. Defaults to 25.",
                },
            },
            "required": [],
        },
    },
}

add_appflowy_row_tool = {
    "type": "function",
    "function": {
        "name": "add_appflowy_row",
        "description": "Add a row to an AppFlowy database. Field names must match the database's own field names exactly, so call list_appflowy_rows or list_appflowy_databases first if unsure. Note that AppFlowy rows cannot be deleted through this tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "The cell values keyed by field name, e.g. {'Name': 'Read the docs', 'Status': 'To do'}.",
                },
                "database_id": {
                    "type": "string",
                    "description": "The AppFlowy database id. Leave empty to use the default database from the configuration.",
                },
            },
            "required": ["fields"],
        },
    },
}

update_appflowy_row_tool = {
    "type": "function",
    "function": {
        "name": "update_appflowy_row",
        "description": "Update an AppFlowy database row by the key it was created with. AppFlowy only supports an upsert keyed by that value, so this can only change rows you created with the same key; rows the user added in the AppFlowy app can be read but not changed. Passing an unused key creates a new row.",
        "parameters": {
            "type": "object",
            "properties": {
                "row_key": {
                    "type": "string",
                    "description": "The stable key identifying the row (the value used when it was created).",
                },
                "fields": {
                    "type": "object",
                    "description": "The cell values to set, keyed by field name.",
                },
                "database_id": {
                    "type": "string",
                    "description": "The AppFlowy database id. Leave empty to use the default database from the configuration.",
                },
            },
            "required": ["row_key", "fields"],
        },
    },
}

list_appflowy_pages_tool = {
    "type": "function",
    "function": {
        "name": "list_appflowy_pages",
        "description": "List the page tree of the user's AppFlowy workspace, with each page's view_id, name and whether it is a space. Use this to find a page to read or append to, or a parent to create a new page under. Use read_appflowy_page to get a page's contents.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

read_appflowy_page_tool = {
    "type": "function",
    "function": {
        "name": "read_appflowy_page",
        "description": "Read the full text of an AppFlowy page, rendered as markdown with its headings, bullets, checkboxes and quotes. Use list_appflowy_pages to find the view_id. Always read a page before appending to it, so you know what is already there.",
        "parameters": {
            "type": "object",
            "properties": {
                "view_id": {
                    "type": "string",
                    "description": "The view_id of the page to read.",
                },
            },
            "required": ["view_id"],
        },
    },
}

delete_appflowy_page_tool = {
    "type": "function",
    "function": {
        "name": "delete_appflowy_page",
        "description": "Move an AppFlowy page to the trash. The user can still restore it from the trash in the AppFlowy app. Database rows cannot be deleted this way, only pages.",
        "parameters": {
            "type": "object",
            "properties": {
                "view_id": {
                    "type": "string",
                    "description": "The view_id of the page to move to trash.",
                },
            },
            "required": ["view_id"],
        },
    },
}

add_appflowy_page_tool = {
    "type": "function",
    "function": {
        "name": "add_appflowy_page",
        "description": "Create a new page in the user's AppFlowy workspace under an existing parent page or space. Use list_appflowy_pages to find a parent_view_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the new page.",
                },
                "parent_view_id": {
                    "type": "string",
                    "description": "The view_id of the parent page or space to create it under.",
                },
            },
            "required": ["title", "parent_view_id"],
        },
    },
}

append_appflowy_text_tool = {
    "type": "function",
    "function": {
        "name": "append_appflowy_text",
        "description": "Append text to the end of an AppFlowy page, one paragraph per line. This only ever adds to the end: existing blocks cannot be edited or removed, so to revise a page read it first with read_appflowy_page and append a correction, or replace the page entirely.",
        "parameters": {
            "type": "object",
            "properties": {
                "view_id": {
                    "type": "string",
                    "description": "The view_id of the page to append to.",
                },
                "text": {
                    "type": "string",
                    "description": "The text to append. Each line becomes its own paragraph block.",
                },
            },
            "required": ["view_id", "text"],
        },
    },
}
