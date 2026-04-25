import json
import os
import threading
import requests
from dotenv import load_dotenv
load_dotenv()

telegram_enabled = os.getenv("ENABLE_TELEGRAM", "false").lower()
telegram_token = os.getenv("TELEGRAM_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

last_received_update_id = 0
_typing_stop_event = None

def send_telegram_message(message: str) -> None:
	global _typing_stop_event
	if _typing_stop_event:
		_typing_stop_event.set()
		_typing_stop_event = None
	if not telegram_token or not telegram_chat_id or telegram_enabled == "false":
		return
	if len(message) > 4000:
		message = message[:3980] + "\n\n(...truncated)"
		print("⚙️ Message truncated to fit Telegram limits.")
	try:
		requests.post(
			f"https://api.telegram.org/bot{telegram_token}/sendMessage",
			json={"chat_id": telegram_chat_id, "text": message},
			timeout=30,
		)
	except Exception:
		print(f"⚠️ Failed to send Telegram message.")

def send_telegram_typing_action() -> None:
	if not telegram_token or not telegram_chat_id or telegram_enabled == "false":
		return
	global _typing_stop_event
	if _typing_stop_event:
		_typing_stop_event.set()
	_typing_stop_event = threading.Event()
	stop = _typing_stop_event

	def _loop():
		while not stop.is_set():
			try:
				requests.post(
					f"https://api.telegram.org/bot{telegram_token}/sendChatAction",
					json={"chat_id": telegram_chat_id, "action": "typing"},
					timeout=30,
				)
			except Exception:
				pass
			stop.wait(4)
	threading.Thread(target=_loop, daemon=True).start()

def register_telegram_commands() -> None:
	if not telegram_token or telegram_enabled == "false":
		return
	with open(os.path.join(os.path.dirname(__file__), "commands.json")) as f:
		commands = json.load(f)
	try:
		requests.post(
			f"https://api.telegram.org/bot{telegram_token}/setMyCommands",
			json=commands,
			timeout=30,
		)
	except Exception:
		print(f"⚠️ Failed to register Telegram commands.")

# TODO: convert to webhook
def read_telegram_messages() -> list[str]:
	global last_received_update_id
	if not telegram_token  or telegram_enabled == "false":
		return []
	try:
		response = requests.get(
			f"https://api.telegram.org/bot{telegram_token}/getUpdates",
			params={"offset": last_received_update_id + 1, "timeout": 1},
			timeout=35,
		)
	except Exception:
		return []
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
