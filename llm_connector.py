import os
import requests
from dotenv import load_dotenv
load_dotenv()

IDENTITY_PATH = os.path.join(os.path.dirname(__file__), "IDENTITY.md")

def load_identity():
    with open(IDENTITY_PATH, "r") as f:
        return f.read().strip()

def prompt(text: str) -> str:
    host = os.getenv("LLM_API_HOST")
    key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    identity = load_identity()
    full_prompt = f"{identity}\n\n prompt: {text}"    
    response = requests.post(
        f"{host}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": full_prompt}]},
        timeout=600, # 10 minutes timeout for long tasks or slow machines or big models or... you get it
    )
    return response.json()["choices"][0]["message"]["content"]
