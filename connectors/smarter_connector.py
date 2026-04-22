import json
import os
import requests
from dotenv import load_dotenv
load_dotenv()

def ask_smarter(question: str, tools=None, tool_handlers={}) -> str:
    host = os.getenv("SMARTER_LLM_API_HOST")
    key = os.getenv("SMARTER_LLM_API_KEY")
    model = os.getenv("SMARTER_LLM_MODEL")
    if not host or not key or not model:
        return "Sorry, I can't help. Smarter LLM is not properly configured."
    messages = [{"role": "user", "content": question}]
    payload = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
    try:
        while True:
            response = requests.post(
                host,
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
                timeout=600,
            )
            data = response.json()
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
    except Exception as e:
        return f"Sorry, I couldn't get a response from the smarter model. Error: {str(e)}"
