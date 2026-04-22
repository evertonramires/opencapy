import json
import os
import requests
from dotenv import load_dotenv
load_dotenv()

def prompt_model(text: str, tools=None, tool_handlers={}) -> str:
    host = os.getenv("LLM_API_HOST")
    key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    temperature = float(os.getenv("LLM_TEMPERATURE", "1.2"))
    messages = [{"role": "user", "content": text}]
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
    while True:
        response = requests.post(
            f"{host}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=600, # 10 minutes timeout for long tasks or slow machines or big models or... you get it
        )
        data = response.json()
        if "choices" not in data:
            raise RuntimeError(data.get("error", {}).get("message", data))
        choice = data["choices"][0]
        if choice["finish_reason"] == "tool_calls":
            assistant_msg = choice["message"]
            messages.append(assistant_msg)
            for tool_call in assistant_msg["tool_calls"]:
                name = tool_call["function"]["name"]
                args = json.loads(tool_call["function"]["arguments"])
                result = tool_handlers[name](**args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": str(result),
                })
        else:
            return choice["message"]["content"]
