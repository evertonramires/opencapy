import importlib.util
import json
import os
import re
import requests
from dotenv import load_dotenv
from connectors.claude_code_connector import claude_code_enabled, last_cli_model, prompt_claude_code
from connectors.usage_connector import buffering_active
load_dotenv()

# Which model actually wrote the last answer, taken from the response rather than
# from config — config lies exactly when it matters, whenever the usage buffer or a
# failure silently swaps the backend. The record is out-of-band on purpose: callers
# like blacksmith parse the returned string as JSON, so the string is never touched.
_model_used = {"name": ""}


def watermark_enabled() -> bool:
    return os.getenv("ENABLE_MODEL_WATERMARK", "true").lower() in ["true", "1", "yes"]


def short_model_name(raw: str) -> str:
    """'google/gemma-4-26b-a4b' -> 'gemma-4-26b-a4b', 'claude-sonnet-5' ->
    'sonnet-5', dated ids lose the date. The footer names the model, not the vendor."""
    name = (raw or "").split("/")[-1]
    name = re.sub(r"^claude-", "", name)
    return re.sub(r"-\d{8}$", "", name)


def record_model_used(name: str) -> None:
    if name:
        _model_used["name"] = short_model_name(name)


def current_model() -> str:
    """Peek, for content written mid-generation by tool calls."""
    return _model_used["name"] if watermark_enabled() else ""


def pop_model_used() -> str:
    """Read-and-clear, for the chat send: a message composed without a model run
    since the last one must not wear a stale signature."""
    name = current_model()
    _model_used["name"] = ""
    return name


def authoring_model() -> str:
    """The model behind whatever is being written right now. In this process that is
    the per-response record above; inside the MCP bridge subprocess — where CLI tool
    calls actually run — it is the hint passed through the bridge env, since the
    parent's record lives in a different interpreter."""
    return current_model() or (short_model_name(os.getenv("OPENCAPY_MODEL_HINT", "")) if watermark_enabled() else "")


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


def prompt_model(text: str, tools=None, tool_handlers=None, host=None, key=None, model=None, claude_model=None, _allow_fallback=True) -> str:
    # An explicit host/model override means the caller chose its backend — the
    # research tier picking claude-bridge, blacksmith picking its own — and the
    # Claude Code CLI must not hijack that choice.
    # Above the usage threshold the Claude window is saved for buffered work, so chat uses the configured LLM
    if _allow_fallback and not host and not model and claude_code_enabled() and not buffering_active():
        try:
            result = prompt_claude_code(text, model=claude_model, use_tools=bool(tools), original_prompt=_extract_original_user_prompt(text))
            record_model_used(last_cli_model())
            return result
        except Exception as e:
            print(f"⚠️ Claude Code CLI failed, trying the configured LLM: {str(e)}")
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
            # Recorded on every iteration, not just the last: tool calls write
            # comments and notes mid-generation and deserve the right signature
            record_model_used(data.get("model") or model or "")
            choice = data["choices"][0]
            if choice["finish_reason"] == "tool_calls":
                assistant_msg = dict(choice["message"])
                assistant_msg.pop("reasoning_content", None)
                assistant_msg.pop("reasoning", None)
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
            # No [FALLBACK] prefix anymore: the watermark carries the model name
            # everywhere the old in-band marker used to leak verbatim
            return prompt_model(text, tools=tools, tool_handlers=tool_handlers, host=fallback_host, key=fallback_key, model=fallback_model, _allow_fallback=False)
        except Exception as fe:
            print(f"⚠️ Fallback LLM also failed: {str(fe)}")
        error_msg = f"⚠️ Failed communicating with LLM model: {str(e)}"
        print(error_msg)
        return error_msg
