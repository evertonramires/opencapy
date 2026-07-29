import os
import requests
from dotenv import load_dotenv
load_dotenv()

def transcription_enabled() -> bool:
    return os.getenv("ENABLE_TRANSCRIPTION", "false").lower() in ["true", "1", "yes"]

def transcribe_audio(audio: bytes) -> str:
    host = os.getenv("LLM_API_HOST", "").rstrip("/")
    # Telegram names voice notes .oga and the providers only accept .ogg, so the part is renamed here
    response = requests.post(
        f"{host}/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY')}"},
        files={"file": ("voice.ogg", audio)},
        data={"model": os.getenv("TRANSCRIPTION_MODEL", "groq/whisper-large-v3-turbo")},
        timeout=300,
    )
    return response.json()["text"].strip()
