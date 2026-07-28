from connectors.tools_connector import notify_tool_use
from connectors.usage_connector import claude_usage as connector_claude_usage
from connectors.claude_code_connector import (
    set_claude_model as connector_set_claude_model,
    set_claude_effort as connector_set_claude_effort,
)
from connectors.buffer_connector import (
    add_buffered as connector_add_buffered,
    read_buffered as connector_read_buffered,
)

def check_claude_usage() -> dict:
    notify_tool_use("🔧📊⏳ Claude tool used to check subscription usage.")
    return connector_claude_usage()

def set_claude_model(model: str) -> dict:
    notify_tool_use(f"🔧📊🧠 Claude tool used to switch the model to '{model}'.")
    return connector_set_claude_model(model)

def set_claude_effort(level: str) -> dict:
    notify_tool_use(f"🔧📊🎚️ Claude tool used to set the effort to '{level}'.")
    return connector_set_claude_effort(level)

def buffer_for_next_window(task: str, source: str = "agent") -> str:
    notify_tool_use(f"🔧📊🪫 Claude tool used to buffer work for the next usage window.")
    return connector_add_buffered(task, source)

def list_buffered_work() -> list[dict]:
    notify_tool_use("🔧📊📋 Claude tool used to list buffered work.")
    return connector_read_buffered()

check_claude_usage_tool = {
    "type": "function",
    "function": {
        "name": "check_claude_usage",
        "description": "Check how much of the Claude subscription's rolling 5 hour usage window has been spent and when it resets, plus the 7 day window. Use this before starting anything long, or when the user asks how much usage is left. Percentages are 0 to 100.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

set_claude_model_tool = {
    "type": "function",
    "function": {
        "name": "set_claude_model",
        "description": "Switch the Claude model used for your own replies, for example to 'sonnet' when the usage window is getting tight or 'opus' for harder work. This takes effect on the next message, not the current one, because each reply runs in a fresh CLI session.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "A model alias such as 'sonnet', 'opus' or 'haiku', or a full model name. Leave empty to go back to the model from the configuration.",
                },
            },
            "required": ["model"],
        },
    },
}

set_claude_effort_tool = {
    "type": "function",
    "function": {
        "name": "set_claude_effort",
        "description": "Set how much reasoning effort you spend per reply. Lower effort stretches the usage window further. This takes effect on the next message, not the current one, because each reply runs in a fresh CLI session.",
        "parameters": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "description": "One of 'low', 'medium', 'high', 'xhigh' or 'max'. Leave empty to go back to the effort from the configuration.",
                },
            },
            "required": ["level"],
        },
    },
}

buffer_for_next_window_tool = {
    "type": "function",
    "function": {
        "name": "buffer_for_next_window",
        "description": "Park a piece of work until the next 5 hour usage window instead of doing it now. Use this for things that are neither urgent nor important when usage is high, or when the user says something can wait. The buffered text is replayed to you as a prompt once the window resets, so write it as an instruction to your future self.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "What to do later, phrased as an instruction (e.g. 'Summarise the AppFlowy schema page and post it to the user').",
                },
                "source": {
                    "type": "string",
                    "description": "Short label for where this came from, e.g. 'agent' or 'user'. Defaults to 'agent'.",
                },
            },
            "required": ["task"],
        },
    },
}

list_buffered_work_tool = {
    "type": "function",
    "function": {
        "name": "list_buffered_work",
        "description": "List the work waiting for the next usage window, with each item's id, source and the time it was buffered. Use this when the user asks what is queued or what you are going to do later.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
