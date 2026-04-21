import os

IDENTITY_PATH = os.path.join(os.path.dirname(__file__), "IDENTITY.md")

def read_identity() -> str:
    with open(IDENTITY_PATH) as f:
        return f.read()

def write_identity(content: str) -> None:
    with open(IDENTITY_PATH, "w") as f:
        f.write(content)