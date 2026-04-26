from connectors.tools_connector import notify_tool_use
from connectors.shell_connector import run_shell_command as connector_run_shell_command


def run_shell_command(command: str) -> str:
    notify_tool_use(f"🔧🐚 Shell tool used with command:\n\n{command}")
    return connector_run_shell_command(command)


run_shell_command_tool = {
    "type": "function",
    "function": {
        "name": "run_shell_command",
        "description": "Run a command in the host machine Linux shell and read the command response.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute on the host Linux machine.",
                }
            },
            "required": ["command"],
        },
    },
}