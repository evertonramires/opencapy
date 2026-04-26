import os
import requests

def sms_enabled() -> bool:
    return os.getenv("ENABLE_SMS", "false").lower() in ["true", "1", "yes"]

def send_sms(to: str, body: str) -> dict:
    if not sms_enabled():
        return {"status": "error", "message": "SMS tool is disabled. To enable it, set ENABLE_SMS=true in your .env file."}
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    response = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        auth=(account_sid, os.getenv("TWILIO_AUTH_TOKEN", "")),
        data={
            "From": os.getenv("TWILIO_FROM"),
            "To": to,
            "Body": body,
        },
    )
    return {"status": response.status_code, "message": response.text}
