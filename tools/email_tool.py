from connectors.tools_connector import notify_tool_use
from connectors.email_connector import send_email as connector_send_email, read_emails as connector_read_emails

def send_email(to: str, subject: str, body: str) -> dict:
    notify_tool_use(f"🔧📧➕ email_tool.send_email called")
    return connector_send_email(to, subject, body)

def read_emails(count: int) -> list[dict]:
    notify_tool_use(f"🔧📧🔍 email_tool.read_emails called")
    return connector_read_emails(count)

send_email_tool = {
    "type": "function",
    "function": {
        "name": "send_email",
        "description": "Send an email to a recipient.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "The recipient email address.",
                },
                "subject": {
                    "type": "string",
                    "description": "The email subject.",
                },
                "body": {
                    "type": "string",
                    "description": "The plain text body of the email.",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
}

read_emails_tool = {
    "type": "function",
    "function": {
        "name": "read_emails",
        "description": "Read the latest received emails from the inbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of recent emails to retrieve.",
                },
            },
            "required": ["count"],
        },
    },
}
