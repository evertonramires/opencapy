import os
import requests
from time import sleep

from dotenv import load_dotenv

load_dotenv()

last_received_update_id = 0

def send_telegram_message(message: str) -> None:
	token = os.getenv("TELEGRAM_TOKEN")
	chat_id = os.getenv("TELEGRAM_CHAT_ID")
 
	if len(message) > 4000:
		message = message[:3980] + "\n\n(...truncated)"
		print("[System] Message truncated to fit Telegram limits.")

	requests.post(
		f"https://api.telegram.org/bot{token}/sendMessage",
		json={"chat_id": chat_id, "text": message},
		timeout=30,
	)

# TODO: convert to webhook
def read_telegram_messages() -> list[str]:
	global last_received_update_id

	token = os.getenv("TELEGRAM_TOKEN")
	response = requests.get(
		f"https://api.telegram.org/bot{token}/getUpdates",
		params={"offset": last_received_update_id + 1, "timeout": 1},
		timeout=35,
	)
	updates = response.json()["result"]

	if updates and len(updates) > 0:
		last_received_update_id = updates[-1]["update_id"]

	return [
		update["message"]["text"]
		for update in updates
		if "message" in update and "text" in update["message"]
	]
	
 
if __name__ == "__main__":
    send_telegram_message("Sending messages to Telegram is working!")
    while True:
        messages = read_telegram_messages()
        for message in messages:
            print(f"Received message from Telegram: {message}")
