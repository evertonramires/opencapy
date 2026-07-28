import json
import os
import subprocess
import sys
from dotenv import load_dotenv
load_dotenv()


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE_PATH = os.path.join(ROOT_DIR, "mcp_bridge.py")
# --system-prompt replaces the Claude Code coding agent prompt, so the CLI behaves like Open Capy
SYSTEM_PROMPT = (
    "You are a personal assistant, not a coding agent. "
    "The user message carries your system rules, identity, memory, notes and the actual prompt. "
    "Follow them exactly and answer in plain text, with no preamble and no markdown fences."
)


def claude_code_enabled() -> bool:
    return os.getenv("ENABLE_CLAUDE_CODE", "false").lower() in ["true", "1", "yes"]


def prompt_claude_code(text: str, model: str = "", use_tools: bool = True, original_prompt: str = "") -> str:
    command = [
        os.getenv("CLAUDE_CODE_BINARY", "claude"),
        "-p", text,
        "--output-format", "json",
        "--no-session-persistence",
        "--system-prompt", SYSTEM_PROMPT,
        "--model", model or os.getenv("CLAUDE_CODE_MODEL", "sonnet"),
    ]
    if use_tools:
        mcp_config = {
            "mcpServers": {
                "opencapy": {
                    "command": sys.executable,
                    "args": [BRIDGE_PATH],
                    "env": {"OPENCAPY_ORIGINAL_PROMPT": original_prompt},
                    # Without alwaysLoad the bridge connects asynchronously and misses the single -p turn
                    "alwaysLoad": True,
                }
            }
        }
        command += [
            "--mcp-config", json.dumps(mcp_config),
            "--strict-mcp-config",
            "--tools", os.getenv("CLAUDE_CODE_BUILTIN_TOOLS", "Bash,Read,Write,WebSearch"),
            "--permission-mode", "bypassPermissions",
        ]
    else:
        command += ["--tools", ""]
    environment = dict(os.environ)
    # Without this the CLI bills an API key instead of using the logged in subscription
    environment.pop("ANTHROPIC_API_KEY", None)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=ROOT_DIR,
        env=environment,
        timeout=int(os.getenv("CLAUDE_CODE_TIMEOUT_SECONDS", "600")),
    )
    if not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or f"claude exited with code {result.returncode}")
    data = json.loads(result.stdout)
    if data.get("is_error"):
        raise RuntimeError(data.get("result"))
    return data["result"]
