import os

IDENTITY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "IDENTITY.md")

def _ensure_identity():
    if not os.path.exists(IDENTITY_PATH):
        open(IDENTITY_PATH, "w").close()

def read_identity() -> str:
    _ensure_identity()
    with open(IDENTITY_PATH) as f:
        return f.read()

def write_identity(content: str) -> None:
    _ensure_identity()
    if content.strip() == "":
        raise ValueError("Identity content cannot be empty.")
    with open(IDENTITY_PATH, "w") as f:
        f.write(content)