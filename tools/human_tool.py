from connectors.tools_connector import notify_tool_use
from connectors.clock_connector import get_time
from connectors.human_connector import add_human_task
from connectors.chat_connector import send_message


def ask_human(title: str, question: str, description: str, original_user_prompt: str = "") -> dict:
    notify_tool_use("🔧🤝💬 Human tool used to request user guidance.")
    timestamp = get_time("utc")
    task = add_human_task(timestamp, title, question, description, original_user_prompt)
    send_message(
        f"🤝 I need your help with pending task {task['id']} ({task['title']}).\n\n"
        f"Question: {task['question']}\n\n"
        f"Reply with: /answer {task['id']} <response>\n"
        f"Tip: Use /listpending to see all tasks pending human interaction."
    )
    return {
        "status": "waiting_for_user",
        "task_id": task["id"],
        "timestamp": task["timestamp"],
        "title": task["title"],
        "question": task["question"],
        "description": task["description"],
        "original_user_prompt": task["original_user_prompt"],
        "message": f"Human guidance requested. User must reply with /answer {task['id']} <response>",
    }


ask_human_tool = {
    "type": "function",
    "function": {
        "name": "ask_human",
        "description": "Ask the user for guidance when blocked or when the assignment is unclear. This is async and returns immediately.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "A short title for the pending human task.",
                },
                "question": {
                    "type": "string",
                    "description": "The exact question to ask the user.",
                },
                "description": {
                    "type": "string",
                    "description": "A summary of the task/job being executed before you needed human help.",
                }
            },
            "required": ["title", "question", "description"],
        },
    },
}
