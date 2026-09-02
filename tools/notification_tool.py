from connectors.tools_connector import notify_tool_use
from connectors.chat_connector import send_notification as connector_send_notification
from connectors.notification_connector import agent_notifications_enabled


def send_notification(message: str) -> dict:
    notify_tool_use("🔧🔔 Notification tool used to send a popup notification.")
    connector_send_notification(message)
    return {"status": "success", "message": "Notification sent. It popped up for the user; it is not part of the chat, so don't repeat it there."}


# NOTIFY_AGENT=false takes the tool off the table entirely, so a disabled
# notification never becomes an error the agent has to talk its way around
if agent_notifications_enabled():
    send_notification_tool = {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": (
                "Send the user a popup notification: a toast in the web chat and a system notification when the tab is in the "
                "background (plus a plain Telegram message when Telegram is on). Use it when something deserves their attention "
                "right now even if they are not looking at the chat: a reminder firing, a timer ending, something they asked to "
                "be pinged about, or urgent news from background work. It interrupts, so keep it to one short sentence and "
                "don't use it for ordinary replies — those belong in the chat itself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The notification text. One short plain-text sentence, no markdown.",
                    },
                },
                "required": ["message"],
            },
        },
    }
