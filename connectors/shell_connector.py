import os
import subprocess

def shell_enabled() -> bool:
    return os.getenv("ENABLE_SHELL", "false").lower() in ["true", "1", "yes"]


def run_shell_command(command: str) -> str:
    if not shell_enabled():
        return "Shell tool is disabled. To enable it, set ENABLE_SHELL=true in your .env file."
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "exit_code: 124\nstdout:\n(empty)\nstderr:\nCommand timed out after 30 seconds."
    output = completed.stdout.strip()
    errors = completed.stderr.strip()
    return (
        f"exit_code: {completed.returncode}\n"
        f"stdout:\n{output or '(empty)'}\n"
        f"stderr:\n{errors or '(empty)'}"
    )