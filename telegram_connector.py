import os
import requests
from time import sleep

from dotenv import load_dotenv

load_dotenv()

POLLING_INTERVAL_SECONDS = 2

last_received_update_id = 0

def send_telegram_message(message: str) -> None:
	token = os.getenv("TELEGRAM_TOKEN")
	chat_id = os.getenv("TELEGRAM_CHAT_ID")

	requests.post(
		f"https://api.telegram.org/bot{token}/sendMessage",
		json={"chat_id": chat_id, "text": message},
		timeout=30,
	)

# TODO: convert to webhook
def listen_telegram_messages() -> list[dict]:
	global last_received_update_id

	sleep(POLLING_INTERVAL_SECONDS)

	token = os.getenv("TELEGRAM_TOKEN")
	response = requests.get(
		f"https://api.telegram.org/bot{token}/getUpdates",
		params={"offset": last_received_update_id + 1, "timeout": 30},
		timeout=35,
	)
	updates = response.json()["result"]

	if updates:
		last_received_update_id = updates[-1]["update_id"]

	return [
		update["message"]
		for update in updates
		if "message" in update and "text" in update["message"]
	]
	

if __name__ == "__main__":
    send_telegram_message("Sending messages to Telegram is working!")
    while True:
        messages = listen_telegram_messages()
        for message in messages:
            print(f"Received message from Telegram: {message['text']}")
