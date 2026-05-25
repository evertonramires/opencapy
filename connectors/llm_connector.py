import importlib.util
import json
import os
import requests
from dotenv import load_dotenv
load_dotenv()


def _resolve_chat_endpoint(host: str) -> str:
    base = host.rstrip("/")
    if base.endswith("/completions"):
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


def _load_tools_from_disk() -> tuple[list[dict], dict]:
    tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    tools = []
    handlers = {}
    for filename in os.listdir(tools_dir):
        if not filename.endswith("_tool.py"):
            continue
        name = filename[:-3]
        spec = importlib.util.spec_from_file_location(name, os.path.join(tools_dir, filename))
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for k, v in vars(module).items():
            if k.endswith("_tool") and isinstance(v, dict):
                tools.append(v)
                handlers[v["function"]["name"]] = getattr(module, v["function"]["name"])
    return tools, handlers


def prompt_model(text: str, tools=None, tool_handlers=None, host=None, key=None, model=None, _allow_fallback=True) -> str:
    try:
        host = host or os.getenv("LLM_API_HOST", "")
        key = key or os.getenv("LLM_API_KEY")
        model = model or os.getenv("LLM_MODEL")
        temperature = float(os.getenv("LLM_TEMPERATURE", "1.2"))
        top_p = float(os.getenv("LLM_TOP_P", "0.95"))
        if tool_handlers is None:
            tool_handlers = {}
        messages = [{"role": "user", "content": text}]
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
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
                raise RuntimeError(data)
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
                    if name == "forge_new_tool" and isinstance(result, dict) and result.get("status") == "installed":
                        tools, tool_handlers = _load_tools_from_disk()
                        payload["tools"] = tools
            else:
                return choice["message"]["content"]
    except Exception as e:
        if not _allow_fallback:
            raise
        try:
            fallback_host = os.getenv("FALLBACK_LLM_API_HOST")
            fallback_key = os.getenv("FALLBACK_LLM_API_KEY")
            fallback_model = os.getenv("FALLBACK_LLM_MODEL")
            print(f"⚠️ Primary LLM failed, trying fallback model: {fallback_model}")
            return f"[FALLBACK]{prompt_model(text, tools=tools, tool_handlers=tool_handlers, host=fallback_host, key=fallback_key, model=fallback_model, _allow_fallback=False)}"
        except Exception as fe:
            print(f"⚠️ Fallback LLM also failed: {str(fe)}")
        error_msg = f"⚠️ Failed communicating with LLM model: {str(e)}"
        print(error_msg)
        return error_msg
