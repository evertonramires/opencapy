import os
import time
from dotenv import load_dotenv
load_dotenv()

from telegram_connector import send_telegram_message, read_telegram_messages


heartbeat_interval_seconds = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))
now = time.time()
last_heartbeat = now
delta_time = 0

def heartbeat() -> bool:
    global last_heartbeat, delta_time
    now = time.time()
    delta_time = now - last_heartbeat
    if delta_time >= heartbeat_interval_seconds:
        last_heartbeat = now
        delta_time = 0
        return True
    return False

if __name__ == "__main__":
    send_telegram_message("Ready to work!")
    while True:
        time.sleep(1)
        if heartbeat():
            messages = read_telegram_messages()
            if messages:
                print(f"Received message from Telegram: {messages}")
