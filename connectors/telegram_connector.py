import json
import os
import threading
import time
import requests

from dotenv import load_dotenv

load_dotenv()

last_received_update_id = 0

_typing_stop_event = None

def send_telegram_message(message: str) -> None:
	global _typing_stop_event
	if _typing_stop_event:
		_typing_stop_event.set()
		_typing_stop_event = None

	token = os.getenv("TELEGRAM_TOKEN")
	chat_id = os.getenv("TELEGRAM_CHAT_ID")
	if not token or not chat_id:
		return
 
	if len(message) > 4000:
		message = message[:3980] + "\n\n(...truncated)"
		print("⚙️ Message truncated to fit Telegram limits.")

	requests.post(
		f"https://api.telegram.org/bot{token}/sendMessage",
		json={"chat_id": chat_id, "text": message},
		timeout=30,
	)

def send_telegram_typing_action() -> None:
	if not os.getenv("TELEGRAM_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
		return
	global _typing_stop_event
	if _typing_stop_event:
		_typing_stop_event.set()
	_typing_stop_event = threading.Event()
	stop = _typing_stop_event

	def _loop():
		token = os.getenv("TELEGRAM_TOKEN")
		chat_id = os.getenv("TELEGRAM_CHAT_ID")
		while not stop.is_set():
			requests.post(
				f"https://api.telegram.org/bot{token}/sendChatAction",
				json={"chat_id": chat_id, "action": "typing"},
				timeout=30,
			)
			stop.wait(4)

	threading.Thread(target=_loop, daemon=True).start()

def register_telegram_commands() -> None:
	token = os.getenv("TELEGRAM_TOKEN")
	if not token:
		return
	with open(os.path.join(os.path.dirname(__file__), "commands.json")) as f:
		commands = json.load(f)
	requests.post(
		f"https://api.telegram.org/bot{token}/setMyCommands",
		json=commands,
		timeout=30,
	)

# TODO: convert to webhook
def read_telegram_messages() -> list[str]:
	global last_received_update_id

	token = os.getenv("TELEGRAM_TOKEN")
	if not token:
		return []
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
