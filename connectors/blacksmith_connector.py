import ast
import compileall
import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from connectors.llm_connector import prompt_model
load_dotenv()


ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
ALLOWED_FILE_SUFFIXES = {
    "tools": "_custom_tool.py",
    "connectors": "_custom_connector.py",
}
NOTIFY_PREFIX_PATTERN = re.compile(r"^🔧\S(?:\ufe0f)?\S(?:\ufe0f)?\s")


def blacksmith_enabled() -> bool:
    return os.getenv("ENABLE_BLACKSMITH", "false").lower() in ["true", "1", "yes"]


def forge_tool(tool_name: str, tool_request: str) -> dict:
    if not blacksmith_enabled():
        return {
            "status": "error",
            "message": "Blacksmith tool is disabled. To enable it, set ENABLE_BLACKSMITH=true in your .env file.",
        }
    if not tool_name.strip():
        return {
            "status": "error",
            "message": "tool_name cannot be empty.",
        }
    if not re.match(r"^[a-z_][a-z0-9_]*$", tool_name):
        return {
            "status": "error",
            "message": "tool_name must be snake_case and must not include file suffixes.",
        }
    if not tool_request.strip():
        return {
            "status": "error",
            "message": "tool_request cannot be empty.",
        }

    host = os.getenv("BLACKSMITH_LLM_API_HOST")
    key = os.getenv("BLACKSMITH_LLM_API_KEY")
    model = os.getenv("BLACKSMITH_LLM_MODEL")
    if not host or not key or not model:
        return {
            "status": "error",
            "message": "Blacksmith LLM is not properly configured.",
        }

    prompt = _build_generation_prompt(tool_name, tool_request)
    llm_response = prompt_model(prompt, tools=None, host=host, key=key, model=model)
    payload = _parse_json_response(llm_response)
    if payload.get("status") == "error":
        return payload

    validation = _validate_payload(payload, tool_name)
    if validation["errors"]:
        return {
            "status": "error",
            "message": "Generated tool package failed validation.",
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "raw_response": llm_response,
        }

    compile_result = _compile_generated_files(validation["files"])
    if not compile_result["ok"]:
        return {
            "status": "error",
            "message": "Generated tool package failed compileall validation.",
            "errors": compile_result["errors"],
            "warnings": validation["warnings"],
            "files": [item["path"] for item in validation["files"]],
            "raw_response": llm_response,
        }

    write_errors = _write_generated_files(validation["files"])
    if write_errors:
        return {
            "status": "error",
            "message": "Generated files validated but could not be written.",
            "errors": write_errors,
            "files": [item["path"] for item in validation["files"]],
        }

    installed_compile = _compile_installed_files(validation["files"])
    result = {
        "status": "installed",
        "tool_name": tool_name,
        "summary": payload.get("summary", ""),
        "files": [item["path"] for item in validation["files"]],
        "warnings": validation["warnings"],
        "compileall": {
            "staged": compile_result,
            "installed": installed_compile,
        },
    }
    if not installed_compile["ok"]:
        result["status"] = "error"
        result["message"] = "Generated files were written, but installed compileall validation failed."
        result["errors"] = installed_compile["errors"]
        return result

    ready_result = _verify_tool_available(tool_name)
    if not ready_result["ok"]:
        result["status"] = "error"
        result["message"] = "Generated files were written, but the tool is not ready to be imported yet."
        result["errors"] = ready_result["errors"]
        return result

    result["message"] = "Generated tool files installed successfully."
    return result


def _build_generation_prompt(tool_name: str, tool_request: str) -> str:
    existing_tools = _summarize_existing_tools()
    expected_tool_path, expected_connector_path = _expected_generated_paths(tool_name)
    return (
        "You are Blacksmith, a code generator for Open Capy tools.\n"
        "Create new tool files that follow the current repository standard exactly.\n\n"
        "Return only valid JSON. Do not use markdown fences, prose, comments, or trailing commas.\n\n"
        "All file content must be encoded as JSON strings with escaped newlines.\n\n"
        "Required response JSON shape:\n"
        "{\n"
        '  "summary": "short implementation summary",\n'
        '  "files": [\n'
        f'    {{"path": "{expected_connector_path}", "content": "complete file content"}},\n'
        f'    {{"path": "{expected_tool_path}", "content": "complete file content"}}\n'
        "  ]\n"
        "}\n\n"
        "Repository tool standard:\n"
        "- Tool modules live in tools/<name>_custom_tool.py.\n"
        "- Connector modules live in connectors/<name>_custom_connector.py.\n"
        f"- The requested tool name is '{tool_name}'.\n"
        f"- Generate the connector at {expected_connector_path}.\n"
        f"- Generate the tool wrapper at {expected_tool_path}.\n"
        "- Generate only brand-new file paths. Blacksmith never overwrites existing tools or connectors.\n"
        "- Tool modules are thin wrappers: import notify_tool_use, import connector functions, call notify_tool_use, then delegate.\n"
        "- Every tool wrapper function must call notify_tool_use before delegating to connector logic.\n"
        "- notify_tool_use message must start with exactly three emojis with no spaces; first emoji must be 🔧, second represents the tool, third represents the operation.\n"
        "- Connectors own environment gates, API calls, filesystem I/O, subprocess use, persistence, and other side effects.\n"
        "- Do not perform network calls, filesystem writes, subprocess calls, or expensive work at import time.\n"
        "- Dangerous or externally mutating capabilities must have an ENABLE_<TOOL> environment gate in the connector.\n"
        "- Never hardcode secrets. Read configuration from os.getenv inside connector functions.\n"
        "- Return JSON-serializable values: dict, list, str, int, float, bool, or None.\n"
        "- Keep generated code dependency-free unless the dependency already exists in requirements.txt.\n\n"
        "Function-tool schema standard:\n"
        "- Each exposed Python function must have a matching <function_name>_tool dictionary in the same tool file.\n"
        '- The dictionary must be literal Python data with shape {"type": "function", "function": {...}}.\n'
        "- function.name must exactly match the Python function name.\n"
        "- function.description must be a useful string.\n"
        '- function.parameters must be an object schema with "type": "object", "properties", and "required".\n'
        "- Every Python parameter without a default value must be listed in schema.required.\n"
        "- Every schema.required item must exist in schema.properties and in the Python function signature.\n"
        "- Every schema property must correspond to a Python function parameter.\n"
        "- Optional schema properties must have Python default values.\n"
        "- Use enum only when the valid choices are genuinely closed.\n\n"
        "Canonical tool wrapper pattern:\n"
        "from connectors.tools_connector import notify_tool_use\n"
        "from connectors.example_custom_connector import do_example as connector_do_example\n\n"
        "def do_example(name: str, excited: bool = False) -> dict:\n"
        '    notify_tool_use(f"🔧🧪🔍 Example tool used for {name}.")\n'
        "    return connector_do_example(name, excited)\n\n"
        "do_example_tool = {\n"
        '    "type": "function",\n'
        '    "function": {\n'
        '        "name": "do_example",\n'
        '        "description": "Do an example operation.",\n'
        '        "parameters": {\n'
        '            "type": "object",\n'
        '            "properties": {\n'
        '                "name": {"type": "string", "description": "Name to process."},\n'
        '                "excited": {"type": "boolean", "description": "Whether to be excited."}\n'
        "            },\n"
        '            "required": ["name"],\n'
        "        },\n"
        "    },\n"
        "}\n\n"
        "Existing tool function names to avoid:\n"
        f"{existing_tools}\n\n"
        "Requested tool name:\n"
        f"{tool_name}\n\n"
        "User request for the new tool:\n"
        f"{tool_request}"
    )


def _expected_generated_paths(tool_name: str) -> tuple[str, str]:
    return (
        f"tools/{tool_name}_custom_tool.py",
        f"connectors/{tool_name}_custom_connector.py",
    )


def _summarize_existing_tools() -> str:
    names = []
    for path in sorted(TOOLS_DIR.glob("*_tool.py")):
        try:
            tree = ast.parse(path.read_text())
        except Exception:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name) or not target.id.endswith("_tool"):
                    continue
                try:
                    data = ast.literal_eval(node.value)
                except Exception:
                    continue
                if isinstance(data, dict) and isinstance(data.get("function"), dict):
                    name = data["function"].get("name")
                    description = data["function"].get("description", "")
                    if name:
                        names.append(f"- {name}: {description}")
    return "\n".join(names) if names else "(none found)"


def _parse_json_response(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        return {
            "status": "error",
            "message": "Blacksmith LLM response was not valid JSON.",
            "error": str(error),
            "raw_response": text,
        }
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "message": "Blacksmith LLM response must be a JSON object.",
            "raw_response": text,
        }
    return payload


def _validate_payload(payload: dict, tool_name: str) -> dict:
    errors = []
    warnings = []
    files = []
    seen_paths = set()
    expected_tool_path, expected_connector_path = _expected_generated_paths(tool_name)

    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        errors.append("Payload must contain a non-empty files list.")
        return {"errors": errors, "warnings": warnings, "files": files}

    for index, raw_file in enumerate(raw_files):
        if not isinstance(raw_file, dict):
            errors.append(f"files[{index}] must be an object.")
            continue
        path = raw_file.get("path")
        content = raw_file.get("content")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"files[{index}].path must be a non-empty string.")
            continue
        if not isinstance(content, str) or not content.strip():
            errors.append(f"{path}: content must be a non-empty string.")
            continue
        normalized_path = _normalize_generated_path(path)
        if normalized_path is None:
            errors.append(f"{path}: path must be inside tools/ or connectors/ and must not escape the repository.")
            continue
        if normalized_path in {"tools/blacksmith_tool.py", "connectors/blacksmith_connector.py"}:
            errors.append(f"{normalized_path}: Blacksmith cannot overwrite itself.")
            continue
        top_level = normalized_path.split("/", 1)[0]
        suffix = ALLOWED_FILE_SUFFIXES[top_level]
        if not normalized_path.endswith(suffix):
            errors.append(f"{normalized_path}: files in {top_level}/ must end with {suffix}.")
            continue
        if top_level == "tools" and normalized_path != expected_tool_path:
            errors.append(f"{normalized_path}: generated tool file must be exactly {expected_tool_path}.")
            continue
        if top_level == "connectors" and normalized_path != expected_connector_path:
            errors.append(f"{normalized_path}: generated connector file must be exactly {expected_connector_path}.")
            continue
        if normalized_path in seen_paths:
            errors.append(f"{normalized_path}: duplicate generated path.")
            continue
        seen_paths.add(normalized_path)
        destination = ROOT_DIR / normalized_path
        if destination.exists():
            errors.append(f"{normalized_path}: file already exists. Blacksmith never overwrites existing files.")
            continue
        if not content.endswith("\n"):
            content += "\n"
            warnings.append(f"{normalized_path}: added trailing newline during validation.")
        files.append({"path": normalized_path, "content": content})

    tool_files = [item for item in files if item["path"].startswith("tools/")]
    if not tool_files:
        errors.append("At least one tools/<name>_custom_tool.py file is required.")

    generated_paths = {item["path"] for item in files}
    if expected_tool_path not in generated_paths:
        errors.append(f"Missing required generated tool file: {expected_tool_path}.")
    if expected_connector_path not in generated_paths:
        errors.append(f"Missing required generated connector file: {expected_connector_path}.")

    function_names = set()
    existing_names = _existing_tool_function_names(files)
    for item in files:
        path_errors, path_warnings, discovered_names = _validate_python_file(
            item,
            existing_names,
            function_names,
            generated_paths,
        )
        errors.extend(path_errors)
        warnings.extend(path_warnings)
        function_names.update(discovered_names)

    return {"errors": errors, "warnings": warnings, "files": files}


def _normalize_generated_path(raw_path: str) -> str | None:
    path = raw_path.replace("\\", "/").strip()
    if path.startswith("/") or "\x00" in path:
        return None
    normalized = os.path.normpath(path).replace("\\", "/")
    if normalized == "." or normalized.startswith("../") or "/../" in normalized:
        return None
    parts = normalized.split("/")
    if len(parts) != 2 or parts[0] not in ALLOWED_FILE_SUFFIXES:
        return None
    return normalized


def _existing_tool_function_names(generated_files: list[dict]) -> set[str]:
    generated_paths = {item["path"] for item in generated_files}
    names = set()
    for path in sorted(TOOLS_DIR.glob("*_tool.py")):
        relative_path = f"tools/{path.name}"
        if relative_path in generated_paths:
            continue
        try:
            tree = ast.parse(path.read_text())
        except Exception:
            continue
        names.update(_tool_schema_names(tree))
    return names


def _validate_python_file(
    item: dict,
    existing_names: set[str],
    generated_names: set[str],
    generated_paths: set[str],
) -> tuple[list[str], list[str], set[str]]:
    path = item["path"]
    content = item["content"]
    errors = []
    warnings = []
    discovered_names = set()

    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as error:
        return [f"{path}: syntax error: {error}"], warnings, discovered_names

    if path.startswith("connectors/"):
        return errors, warnings, discovered_names

    errors.extend(_missing_connector_imports(path, tree, generated_paths))

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    tool_assignments = _tool_assignments(tree)
    if not tool_assignments:
        errors.append(f"{path}: tool file must define at least one literal *_tool dictionary.")
        return errors, warnings, discovered_names

    imports_notify = _imports_notify_tool_use(tree)
    if not imports_notify:
        errors.append(f"{path}: tool file must import notify_tool_use from connectors.tools_connector.")

    for variable_name, tool_data in tool_assignments:
        schema_errors, function_name = _validate_tool_schema(path, variable_name, tool_data, functions)
        errors.extend(schema_errors)
        if not function_name:
            continue
        if function_name in existing_names:
            errors.append(f"{path}: function name {function_name} already exists in another tool.")
        if function_name in generated_names or function_name in discovered_names:
            errors.append(f"{path}: duplicate generated function name {function_name}.")
        function_node = functions.get(function_name)
        if function_node is not None:
            errors.extend(_validate_notify_call(path, function_name, function_node))
        discovered_names.add(function_name)

    return errors, warnings, discovered_names


def _missing_connector_imports(path: str, tree: ast.Module, generated_paths: set[str]) -> list[str]:
    errors = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("connectors."):
            continue
        module_path = f"{node.module.replace('.', '/')}.py"
        if module_path in generated_paths:
            continue
        if not (ROOT_DIR / module_path).exists():
            errors.append(f"{path}: imports missing connector module {node.module}.")
    return errors


def _tool_assignments(tree: ast.Module) -> list[tuple[str, dict]]:
    assignments = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.endswith("_tool"):
                continue
            try:
                data = ast.literal_eval(node.value)
            except Exception:
                continue
            if isinstance(data, dict):
                assignments.append((target.id, data))
    return assignments


def _tool_schema_names(tree: ast.Module) -> set[str]:
    names = set()
    for _variable_name, data in _tool_assignments(tree):
        function = data.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.add(function["name"])
    return names


def _imports_notify_tool_use(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "connectors.tools_connector":
            return any(alias.name == "notify_tool_use" for alias in node.names)
    return False


def _validate_notify_call(path: str, function_name: str, function_node: ast.FunctionDef) -> list[str]:
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "notify_tool_use":
            continue
        if not node.args:
            return [f"{path}: {function_name} must call notify_tool_use with a message argument."]

        message_prefix = _notify_message_prefix(node.args[0])
        if not message_prefix:
            return [f"{path}: {function_name} notify_tool_use message must be a string or f-string."]
        if not NOTIFY_PREFIX_PATTERN.match(message_prefix):
            return [
                f"{path}: {function_name} notify_tool_use message must start with three emojis and the first one must be 🔧."
            ]
        return []

    return [f"{path}: {function_name} must call notify_tool_use before delegating to connector logic."]


def _notify_message_prefix(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
                continue
            break
        return "".join(parts)
    return ""


def _validate_tool_schema(path: str, variable_name: str, data: dict, functions: dict[str, ast.FunctionDef]) -> tuple[list[str], str | None]:
    errors = []
    if data.get("type") != "function":
        errors.append(f"{path}: {variable_name}.type must be 'function'.")
    function = data.get("function")
    if not isinstance(function, dict):
        errors.append(f"{path}: {variable_name}.function must be an object.")
        return errors, None

    function_name = function.get("name")
    if not isinstance(function_name, str) or not function_name:
        errors.append(f"{path}: {variable_name}.function.name must be a non-empty string.")
        return errors, None
    if not re.match(r"^[a-z_][a-z0-9_]*$", function_name):
        errors.append(f"{path}: function name {function_name} must be snake_case.")
    if variable_name != f"{function_name}_tool":
        errors.append(f"{path}: tool dictionary must be named {function_name}_tool.")
    if not isinstance(function.get("description"), str) or not function["description"].strip():
        errors.append(f"{path}: {function_name} needs a non-empty description.")

    parameters = function.get("parameters")
    if not isinstance(parameters, dict):
        errors.append(f"{path}: {function_name}.parameters must be an object schema.")
        return errors, function_name
    if parameters.get("type") != "object":
        errors.append(f"{path}: {function_name}.parameters.type must be 'object'.")
    properties = parameters.get("properties")
    required = parameters.get("required")
    if not isinstance(properties, dict):
        errors.append(f"{path}: {function_name}.parameters.properties must be an object.")
        properties = {}
    if not isinstance(required, list):
        errors.append(f"{path}: {function_name}.parameters.required must be a list.")
        required = []
    if any(not isinstance(item, str) for item in required):
        errors.append(f"{path}: {function_name}.parameters.required must contain only strings.")

    function_node = functions.get(function_name)
    if function_node is None:
        errors.append(f"{path}: Python function {function_name} is missing.")
        return errors, function_name

    args = [arg.arg for arg in function_node.args.args]
    default_count = len(function_node.args.defaults)
    required_args = set(args[:len(args) - default_count] if default_count else args)
    optional_args = set(args) - required_args
    property_names = set(properties)
    required_names = set(required)

    missing_required = sorted(required_args - required_names)
    if missing_required:
        errors.append(f"{path}: Python required args missing from schema.required: {missing_required}.")

    missing_properties = sorted(required_names - property_names)
    if missing_properties:
        errors.append(f"{path}: schema.required names missing from properties: {missing_properties}.")

    unknown_required = sorted(required_names - set(args))
    if unknown_required:
        errors.append(f"{path}: schema.required names missing from Python signature: {unknown_required}.")

    unknown_properties = sorted(property_names - set(args))
    if unknown_properties:
        errors.append(f"{path}: schema property names missing from Python signature: {unknown_properties}.")

    optional_without_default = sorted((property_names - required_names) - optional_args)
    if optional_without_default:
        errors.append(f"{path}: optional schema properties need Python defaults: {optional_without_default}.")

    for property_name, property_schema in properties.items():
        if not isinstance(property_schema, dict):
            errors.append(f"{path}: property {property_name} schema must be an object.")
        elif "type" not in property_schema:
            errors.append(f"{path}: property {property_name} schema must include a type.")

    return errors, function_name


def _compile_generated_files(files: list[dict]) -> dict:
    with tempfile.TemporaryDirectory(prefix="opencapy-blacksmith-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        for item in files:
            destination = tmp_root / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(item["content"])
        return _compile_dir(tmp_root)


def _compile_installed_files(files: list[dict]) -> dict:
    paths = [ROOT_DIR / item["path"] for item in files]
    errors = []
    output_parts = []
    for path in paths:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            ok = compileall.compile_file(str(path), quiet=1)
        output = (stdout.getvalue() + stderr.getvalue()).strip()
        if output:
            output_parts.append(output)
        if not ok:
            errors.append(f"{path.relative_to(ROOT_DIR)} failed compileall validation.")
    return {"ok": not errors, "errors": errors, "output": "\n".join(output_parts)}


def _verify_tool_available(tool_name: str) -> dict:
    tool_path, connector_path = _expected_generated_paths(tool_name)
    missing_paths = []
    for path in [connector_path, tool_path]:
        if not (ROOT_DIR / path).exists():
            missing_paths.append(path)
    if missing_paths:
        return {
            "ok": False,
            "errors": [f"{path}: generated file is not available on disk." for path in missing_paths],
        }

    try:
        tool_file = ROOT_DIR / tool_path
        module_name = f"generated_{tool_name}_custom_tool"
        spec = importlib.util.spec_from_file_location(module_name, tool_file)
        if spec is None or spec.loader is None:
            return {"ok": False, "errors": [f"{tool_path}: could not load module spec."]}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as error:
        return {"ok": False, "errors": [f"{tool_path}: could not import generated tool module: {error}"]}

    return {"ok": True, "errors": []}


def _compile_dir(path: Path) -> dict:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        ok = compileall.compile_dir(str(path), quiet=1)
    output = (stdout.getvalue() + stderr.getvalue()).strip()
    errors = [] if ok else ["compileall.compile_dir returned false."]
    if output and not ok:
        errors.append(output)
    return {"ok": ok, "errors": errors, "output": output}


def _write_generated_files(files: list[dict]) -> list[str]:
    errors = []
    for item in files:
        destination = ROOT_DIR / item["path"]
        if destination.exists():
            errors.append(f"{item['path']}: file already exists. Blacksmith never overwrites existing files.")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_name(f".{destination.name}.tmp")
        try:
            temp_path.write_text(item["content"])
            os.replace(temp_path, destination)
        except Exception as error:
            errors.append(f"{item['path']}: {error}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    return errors
