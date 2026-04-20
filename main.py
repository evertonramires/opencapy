from telegram_connector import send_telegram_message, listen_telegram_messages


if __name__ == "__main__":
    send_telegram_message("Ready to work!")
    while True:
        messages = listen_telegram_messages()
        for message in messages:
            print(f"Received message: {message['text']}")
