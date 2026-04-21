import os
import requests

def send_sms(to: str, body: str) -> dict:
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
