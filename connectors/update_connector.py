import os
import sys
import subprocess

def _is_runtime_change(path: str) -> bool:
    return (
        path.endswith(".py")
        or path == "requirements.txt"
        or path == "SYSTEM_PROMPT.md"
        or path == "IDENTITY.md"
    )


def run_self_update() -> dict:
    before_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    git_pull = subprocess.run(["git", "pull"], capture_output=True, text=True)
    after_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    deps_update = subprocess.run(["uv", "pip", "install", "-r", "requirements.txt"], capture_output=True, text=True)

    changed_files = []
    if before_head != after_head:
        diff_output = subprocess.run(
            ["git", "diff", "--name-only", before_head, after_head],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if diff_output:
            changed_files = diff_output.split("\n")

    restart_needed = any(_is_runtime_change(path) for path in changed_files)
    changed_files_text = "\n".join(changed_files) if changed_files else "none"
    restart_text = "Restarting now..." if restart_needed else "No restart needed."

    message = (
        "✅ Update finished.\n\n"
        f"git pull:\n{git_pull.stdout.strip() or git_pull.stderr.strip() or 'done'}\n\n"
        f"dependencies:\n{deps_update.stdout.strip() or deps_update.stderr.strip() or 'done'}\n\n"
        f"changed files from pull:\n{changed_files_text}\n\n"
        f"{restart_text}"
    )

    return {
        "message": message,
        "restart_needed": restart_needed,
    }

def restart_process() -> None:
    subprocess.run(["pkill", "-f", "uvicorn"])
    os.execv(sys.executable, [sys.executable, "main.py"])
