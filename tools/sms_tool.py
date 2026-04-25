from connectors.tools_connector import notify_tool_use
from connectors.sms_connector import send_sms as connector_send_sms

def send_sms(to: str, body: str) -> dict:
    notify_tool_use(f"🔧📱➕ SMS tool used to send an SMS to {to}.")
    return connector_send_sms(to, body)

send_sms_tool = {
    "type": "function",
    "function": {
        "name": "send_sms",
        "description": "Send an SMS message to a phone number via Twilio.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "The recipient phone number in E.164 format (e.g. '+15551234567').",
                },
                "body": {
                    "type": "string",
                    "description": "The SMS message content.",
                },
            },
            "required": ["to", "body"],
        },
    },
}
