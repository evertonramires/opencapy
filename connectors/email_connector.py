import os
import requests

def _auth() -> tuple[str, str]:
    return ("api", os.getenv("MAILGUN_API_KEY", ""))

def _domain():
    return os.getenv("MAILGUN_DOMAIN")

def send_email(to: str, subject: str, body: str) -> dict:
    response = requests.post(
        f"https://api.mailgun.net/v3/{_domain()}/messages",
        auth=_auth(),
        data={
            "from": os.getenv("MAILGUN_FROM"),
            "to": to,
            "subject": subject,
            "text": body,
        },
    )
    return {"status": response.status_code, "message": response.text}

def read_emails(count: int) -> list[dict]:
    events = requests.get(
        f"https://api.mailgun.net/v3/{_domain()}/events",
        auth=_auth(),
        params={"event": "stored", "limit": count},
    ).json()
    emails = []
    for item in events.get("items", []):
        storage_url = item.get("storage", {}).get("url")
        if not storage_url:
            continue
        msg = requests.get(storage_url, auth=_auth()).json()
        emails.append({
            "from": msg.get("sender"),
            "to": msg.get("recipients"),
            "subject": msg.get("subject"),
            "body": msg.get("body-plain") or msg.get("stripped-text"),
            "date": msg.get("Date"),
        })
    return emails
