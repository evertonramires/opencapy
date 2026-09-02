import os
import requests

from dotenv import load_dotenv

load_dotenv()

# Both swallow transport errors the way the Telegram connector does: send_message is
# now also called from inside tools, so a web UI that is down must not take out the
# tool call or lose an approval card that Telegram already delivered fine.
def send_api_message(message: str, notify: bool = True) -> None:
    api_url = os.getenv("CHAT_API_HOST")
    if not api_url:
        return
    try:
        requests.post(f"{api_url}/outbox", json={"message": message, "notify": notify}, timeout=30)
    except Exception:
        print("⚠️ Failed to send message to the chat API.")

def send_api_notification(message: str) -> None:
    api_url = os.getenv("CHAT_API_HOST")
    if not api_url:
        return
    try:
        requests.post(f"{api_url}/notify", json={"message": message}, timeout=30)
    except Exception:
        print("⚠️ Failed to send notification to the chat API.")

def read_api_messages() -> list[str]:
    api_url = os.getenv("CHAT_API_HOST")
    if not api_url:
        return []
    try:
        response = requests.get(f"{api_url}/inbox", timeout=30)
        return response.json()["messages"]
    except Exception:
        print("⚠️ Failed to read messages from the chat API.")
        return []
