import html
import json
import os
import re
import threading
import requests
from dotenv import load_dotenv
from connectors.transcription_connector import transcribe_audio, transcription_enabled
load_dotenv()

telegram_token = os.getenv("TELEGRAM_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
telegram_state_file = "hood/telegram_state.json"

if os.path.exists(telegram_state_file):
	with open(telegram_state_file) as f:
		last_received_update_id = json.load(f).get("last_received_update_id", 0)
else:
	last_received_update_id = 0
_typing_stop_event = None

def telegram_enabled() -> bool:
	return os.getenv("ENABLE_TELEGRAM", "false").lower() in ["true", "1", "yes"]

# The agent writes markdown and Telegram renders none of it, so translate it to the HTML subset Telegram understands
def _to_telegram_html(text: str) -> str:
	code = []

	def _stash_fence(match) -> str:
		language = f' class="language-{match.group(1)}"' if match.group(1) else ""
		code.append(f"<pre><code{language}>{html.escape(match.group(2), quote=False)}</code></pre>")
		return f"\x00{len(code) - 1}\x00"

	def _stash_inline(match) -> str:
		code.append(f"<code>{html.escape(match.group(1), quote=False)}</code>")
		return f"\x00{len(code) - 1}\x00"

	# Code comes out first so its contents are never read as formatting, and goes back in last
	text = re.sub(r"```(\w*)\n(.*?)```", _stash_fence, text, flags=re.DOTALL)
	text = re.sub(r"`([^`\n]+)`", _stash_inline, text)
	text = html.escape(text, quote=False)
	text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
	text = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", text, flags=re.MULTILINE)
	# Underscores are left alone on purpose, they would mangle every snake_case name Open Capy prints
	text = re.sub(r"\*\*\*(?!\s)([^\n]+?)(?<!\s)\*\*\*", r"<b><i>\1</i></b>", text)
	text = re.sub(r"\*\*(?!\s)([^\n]+?)(?<!\s)\*\*", r"<b>\1</b>", text)
	text = re.sub(r"\*(?!\s)([^\n]+?)(?<!\s)\*", r"<i>\1</i>", text)
	text = re.sub(r"~~(?!\s)([^\n]+?)(?<!\s)~~", r"<s>\1</s>", text)
	# Telegram has no images, so a badge (an image wrapped in a link) keeps its alt text and the outer target
	text = re.sub(r"\[!\[([^\]\n]+)\]\([^)\s]*\)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
	text = re.sub(r"!\[([^\]\n]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
	text = re.sub(r"\[([^\]\n]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
	return re.sub(r"\x00(\d+)\x00", lambda match: code[int(match.group(1))], text)

# buttons is a list of rows, each row a list of (label, callback_data) pairs. The
# callback data is sent back verbatim when tapped, so callers use it to carry a
# command like "/approve 3" that the chat connector already knows how to dispatch.
def _inline_keyboard(buttons) -> dict | None:
	if not buttons:
		return None
	return {"inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row] for row in buttons]}

def send_telegram_message(message: str, buttons=None) -> int | None:
	global _typing_stop_event
	if _typing_stop_event:
		_typing_stop_event.set()
		_typing_stop_event = None
	if not telegram_token or not telegram_chat_id or not telegram_enabled():
		return None
	# Lower than Telegram's 4096 limit because escaping and tags grow the text on the way out
	if len(message) > 3500:
		message = message[:3480] + "\n\n(...truncated)"
		print("⚙️ Message truncated to fit Telegram limits.")
	markup = _inline_keyboard(buttons)
	payload = {"chat_id": telegram_chat_id, "text": _to_telegram_html(message), "parse_mode": "HTML"}
	if markup:
		payload["reply_markup"] = markup
	try:
		response = requests.post(
			f"https://api.telegram.org/bot{telegram_token}/sendMessage",
			json=payload,
			timeout=30,
		)
		# Telegram answers 400 instead of raising when the markup is off, and the message would be lost silently
		if not response.ok:
			print(f"⚙️ Telegram rejected the formatting, sending as plain text: {response.text}")
			plain = {"chat_id": telegram_chat_id, "text": message}
			# The buttons ride along on the retry too, otherwise a formatting slip
			# silently turns an approval card into an undecidable message
			if markup:
				plain["reply_markup"] = markup
			response = requests.post(
				f"https://api.telegram.org/bot{telegram_token}/sendMessage",
				json=plain,
				timeout=30,
			)
		if response.ok:
			return response.json()["result"]["message_id"]
	except Exception:
		print(f"⚠️ Failed to send Telegram message.")
	return None

def edit_telegram_message(message_id: int, text: str) -> None:
	"""Rewrites a message in place, used to turn a decided card into its outcome."""
	if not telegram_token or not telegram_chat_id or not telegram_enabled() or not message_id:
		return
	try:
		response = requests.post(
			f"https://api.telegram.org/bot{telegram_token}/editMessageText",
			json={"chat_id": telegram_chat_id, "message_id": message_id, "text": _to_telegram_html(text), "parse_mode": "HTML"},
			timeout=30,
		)
		if not response.ok:
			requests.post(
				f"https://api.telegram.org/bot{telegram_token}/editMessageText",
				json={"chat_id": telegram_chat_id, "message_id": message_id, "text": text},
				timeout=30,
			)
	except Exception:
		print(f"⚠️ Failed to edit Telegram message.")

def send_telegram_typing_action() -> None:
	if not telegram_token or not telegram_chat_id or not telegram_enabled():
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
	if not telegram_token or not telegram_enabled():
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

def _download_telegram_file(file_id: str) -> bytes:
	file_path = requests.get(
		f"https://api.telegram.org/bot{telegram_token}/getFile",
		params={"file_id": file_id},
		timeout=30,
	).json()["result"]["file_path"]
	return requests.get(f"https://api.telegram.org/file/bot{telegram_token}/{file_path}", timeout=300).content

def _consume_callback(callback: dict) -> str:
	"""Acknowledges a tapped button and strips the keyboard, returning the command
	it carried. Answering clears the client side spinner and removing the buttons
	stops a second tap acting on something already decided."""
	try:
		requests.post(
			f"https://api.telegram.org/bot{telegram_token}/answerCallbackQuery",
			json={"callback_query_id": callback["id"]},
			timeout=30,
		)
	except Exception:
		pass
	message_id = (callback.get("message") or {}).get("message_id")
	if message_id:
		try:
			requests.post(
				f"https://api.telegram.org/bot{telegram_token}/editMessageReplyMarkup",
				json={"chat_id": telegram_chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}},
				timeout=30,
			)
		except Exception:
			pass
	return callback.get("data", "")

# TODO: convert to webhook
def read_telegram_messages() -> list[str]:
	global last_received_update_id
	if not telegram_token  or not telegram_enabled():
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
		with open(telegram_state_file, "w") as f:
			json.dump({"last_received_update_id": last_received_update_id}, f)
	messages = []
	for update in updates:
		if "callback_query" in update:
			tapped = _consume_callback(update["callback_query"])
			if tapped:
				messages.append(tapped)
			continue
		message = update.get("message", {})
		if "text" in message:
			messages.append(message["text"])
		elif transcription_enabled() and ("voice" in message or "audio" in message):
			transcript = transcribe_audio(_download_telegram_file(message.get("voice", message.get("audio"))["file_id"]))
			# Echoed back so a mishearing is visible instead of the agent quietly acting on the wrong words
			send_telegram_message(f"🎤 {transcript}")
			messages.append(transcript)
	return messages
	
if __name__ == "__main__":
    send_telegram_message("Sending messages to Telegram is working!")
    send_telegram_message(
        "Tap one to check buttons are working:",
        buttons=[[("👍 Yes", "/smoketest yes"), ("👎 No", "/smoketest no")]],
    )
    while True:
        messages = read_telegram_messages()
        for message in messages:
            print(f"Received message from Telegram: {message}")
