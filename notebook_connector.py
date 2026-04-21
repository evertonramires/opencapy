import os

NOTEBOOK_PATH = os.path.join(os.path.dirname(__file__), "hood", "notebook.md")

def _ensure_notebook():
    if not os.path.exists(NOTEBOOK_PATH):
        open(NOTEBOOK_PATH, "w").close()

def add_note(timestamp, note) -> str:
    _ensure_notebook()
    lines = [l for l in read_notes().splitlines() if l.strip()]
    next_id = len(lines) + 1
    with open(NOTEBOOK_PATH, "a") as f:
        f.write(f"- {next_id}. [{timestamp}] {note}\n")
    prune_notes()
    return f"[System] Note added: {next_id}. {note} at {timestamp}"

def read_notes() -> str:
    _ensure_notebook()
    with open(NOTEBOOK_PATH) as f:
        return f.read()

def delete_note(note_id):
    _ensure_notebook()
    with open(NOTEBOOK_PATH) as f:
        lines = f.readlines()
    lines = [line for line in lines if not line.startswith(f"- {note_id}.")]
    with open(NOTEBOOK_PATH, "w") as f:
        f.writelines(lines)

def prune_notes():
    max_chars = int(os.getenv("NOTEBOOK_LENGTH_CHARACTERS", 10000))
    content = read_notes()
    if len(content) > max_chars:
        with open(NOTEBOOK_PATH, "w") as f:
            f.write(content[-max_chars:])

