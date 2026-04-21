import os
import requests

from dotenv import load_dotenv

load_dotenv()

def send_api_message(message: str) -> None:
    api_url = os.getenv("CHAT_API_HOST")
    if not api_url:
        return
    requests.post(f"{api_url}/outbox", json={"message": message}, timeout=30)

def read_api_messages() -> list[str]:
    api_url = os.getenv("CHAT_API_HOST")
    if not api_url:
        return []
    response = requests.get(f"{api_url}/inbox", timeout=30)
    return response.json()["messages"]
