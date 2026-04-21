from tools_connector import notify_tool_use
from notebook_connector import add_note as add_note_connector, read_notes as read_notes_connector, delete_note as delete_note_connector

def add_note(timestamp: str, note: str) -> str:
    notify_tool_use(f"[Tool] notebook_tool.add_note called")
    return add_note_connector(timestamp, note)

def read_notes() -> str:
    notify_tool_use(f"[Tool] notebook_tool.read_notes called")
    return read_notes_connector()

def delete_note(note_id: int) -> None:
    notify_tool_use(f"[Tool] notebook_tool.delete_note called")
    delete_note_connector(note_id)

add_note_tool = {
    "type": "function",
    "function": {
        "name": "add_note",
        "description": "Add a note to the notebook. Use this if you want to remember something important.",
        "parameters": {
            "type": "object",
            "properties": {
                "timestamp": {
                    "type": "string",
                    "description": "The timestamp for the note.",
                },
                "note": {
                    "type": "string",
                    "description": "The note content.",
                }
            },
            "required": ["timestamp", "note"],
        },
    },
}

read_notes_tool = {
    "type": "function",
    "function": {
        "name": "read_notes",
        "description": "Read all notes from the notebook. Use this if you can't find in memory.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

delete_note_tool = {
    "type": "function",
    "function": {
        "name": "delete_note",
        "description": "Delete a note from the notebook by its ID. Use this if you want to remove something from the notebook.",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "integer",
                    "description": "The ID of the note to delete.",
                }
            },
            "required": ["note_id"],
        },
    },
}