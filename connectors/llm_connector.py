import json
import os
import random
import requests
from dotenv import load_dotenv
load_dotenv()


def _resolve_chat_endpoint(host: str) -> str:
    base = host.rstrip("/")
    if base.endswith("/v1/chat/completions"):
        return base
    return f"{base}/v1/chat/completions"


def _extract_original_user_prompt(text: str) -> str:
    marker = "Prompt:\n"
    if marker in text:
        prompt_text = text.split(marker, 1)[1].strip()
        if prompt_text.startswith("User said: "):
            return prompt_text[len("User said: "):].strip()
        return prompt_text
    return text


def prompt_model(text: str, tools=None, tool_handlers=None) -> str:
    host = os.getenv("LLM_API_HOST", "")
    key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    temperature = float(os.getenv("LLM_TEMPERATURE", "1.2"))
    top_p = float(os.getenv("LLM_TOP_P", "0.95"))
    seed = random.randint(1, 2147483647)
    if tool_handlers is None:
        tool_handlers = {}
    messages = [{"role": "user", "content": text}]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "seed": seed,
    }
    if tools:
        payload["tools"] = tools
    while True:
        response = requests.post(
            _resolve_chat_endpoint(host),
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
                if name == "ask_human":
                    args.setdefault("original_user_prompt", _extract_original_user_prompt(text))
                try:
                    result = tool_handlers[name](**args)
                except Exception as e:
                    result = {
                        "status": "error",
                        "tool": name,
                        "message": f"Tool execution failed: {str(e)}",
                    }
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result) if isinstance(result, dict) else str(result),
                })
        else:
            return choice["message"]["content"]
