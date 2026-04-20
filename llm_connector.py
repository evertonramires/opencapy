import os
import requests
from dotenv import load_dotenv
load_dotenv()

def prompt_model(text: str) -> str:
    host = os.getenv("LLM_API_HOST")
    key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    response = requests.post(
        f"{host}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": text}]},
        timeout=600, # 10 minutes timeout for long tasks or slow machines or big models or... you get it
    )
    return response.json()["choices"][0]["message"]["content"]
