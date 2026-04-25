import os
from connectors.api_connector import send_api_message, read_api_messages
from connectors.telegram_connector import send_telegram_message, read_telegram_messages, send_telegram_typing_action, register_telegram_commands
from connectors.notebook_connector import add_note, delete_note, read_notes
from connectors.identity_connector import read_identity, write_identity
from connectors.tools_connector import list_tools
from connectors.clock_connector import get_time
from connectors.taskbook_connector import add_task, delete_task, read_tasks
from connectors.routines_connector import add_routine, delete_routine, read_routines
from connectors.whitelist_connector import add_to_whitelist, remove_from_whitelist, read_whitelist
from connectors.internet_connector import check_internet_connection
from connectors.update_connector import run_self_update, restart_process
from agent import prompt


def _format_routine_interval(interval_seconds: int) -> str:
    if interval_seconds >= 86400 and interval_seconds % 86400 == 0:
        days = interval_seconds // 86400
        unit = "day" if days == 1 else "days"
        return f"{days} {unit}"

    hours = interval_seconds / 3600
    hours_text = f"{int(hours)}" if hours == int(hours) else f"{hours:.1f}"
    unit = "hour" if hours == 1 else "hours"
    return f"{hours_text} {unit}"


def _is_command(message: str, command: str) -> bool:
    return message == command or message.startswith(f"{command} ")

def register_commands():
    register_telegram_commands()

def send_message(message: str) -> None:
    send_telegram_message(message)
    send_api_message(message)

def read_messages():
    messages = []
    messages.extend(read_telegram_messages())
    messages.extend(read_api_messages())
    
    if messages:
        send_telegram_typing_action()
        for message in messages:
            if _is_command(message, "/addtask"):
                try:
                    task_text = message[len("/addtask"):].strip()
                    current_time = get_time("utc")
                    llm_response = prompt(f"Current time: {current_time}\nExtract a task and scheduled timestamp from: \"{task_text}\"\nReply with exactly two lines:\nTASK: <task description>\nTIMESTAMP: <ISO8601 UTC timestamp>")
                    task = llm_response.split("TASK:")[1].split("\n")[0].strip()
                    timestamp = llm_response.split("TIMESTAMP:")[1].strip().split("\n")[0].strip()
                    add_task_response = add_task(timestamp, task)
                    print(add_task_response)
                    send_message(add_task_response)
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the task, can we try again? Details: {e}")
            elif _is_command(message, "/listtasks"):
                tasks = read_tasks()
                task_list = "\n".join([f"[{task['timestamp']}] {task['id']}. {task['task']}" for task in tasks])
                send_message(f"📑 Current tasks:\n{task_list}")
            elif _is_command(message, "/deletetask"):
                try:
                    task_id = int(message[len("/deletetask"):].strip())
                    delete_task(task_id)
                    send_message(f"Task {task_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the task, can we try again? Details: {e}")
            elif _is_command(message, "/addroutine"):
                try:
                    routine_text = message[len("/addroutine"):].strip()
                    current_time = get_time("utc")
                    llm_response = prompt(f"Current time: {current_time}\nExtract a recurring routine from: \"{routine_text}\"\nReply with exactly three lines:\nTASK: <task description>\nSTART_TIME: <ISO8601 UTC timestamp>\nINTERVAL_SECONDS: <integer seconds>")
                    task = llm_response.split("TASK:")[1].split("\n")[0].strip()
                    start_time = llm_response.split("START_TIME:")[1].split("\n")[0].strip()
                    interval = int(llm_response.split("INTERVAL_SECONDS:")[1].strip().split("\n")[0].strip())
                    add_routine_response = add_routine(start_time, interval, task)
                    print(add_routine_response)
                    send_message(add_routine_response)
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the routine, can we try again? Details: {e}")
            elif _is_command(message, "/listroutines"):
                routines = read_routines()
                routine_list = "\n".join([f"[{r['start_time']} every {_format_routine_interval(r['interval'])}] {r['id']}. {r['task']}" for r in routines])
                send_message(f"♾️ Current routines:\n{routine_list}")
            elif _is_command(message, "/deleteroutine"):
                try:
                    routine_id = int(message[len("/deleteroutine"):].strip())
                    delete_routine(routine_id)
                    send_message(f"Routine {routine_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the routine, can we try again? Details: {e}")
            elif _is_command(message, "/addnote"):
                try:
                    note_text = message[len("/addnote"):].strip()
                    current_time = get_time("utc")
                    add_note_response = add_note(current_time, note_text)
                    print(add_note_response)
                    send_message(add_note_response)
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the note, can we try again? Details: {e}")
            elif _is_command(message, "/listnotes"):
                notes = read_notes()
                send_message(f"📔 Current notes:\n{notes}")
            elif _is_command(message, "/deletenote"):
                try:
                    note_id = int(message[len("/deletenote"):].strip())
                    delete_note(note_id)
                    send_message(f"Note {note_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the note, can we try again? Details: {e}")
            elif _is_command(message, "/listtools"):
                tools = list_tools()
                send_message(tools)
            elif _is_command(message, "/readidentity"):
                identity = read_identity()
                send_message(identity)
            elif _is_command(message, "/writeidentity"):
                try:
                    identity_content = message[len("/writeidentity"):].strip()
                    if not identity_content:
                        send_message("Identity content cannot be empty. Try typing the entire command followed by the new identity content in the same line.")
                        continue
                    write_identity(identity_content)
                    identity = read_identity()
                    send_message(f"New identity:\n{identity}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't update the identity, can we try again? Details: {e}")
            elif _is_command(message, "/whitelist"):
                try:
                    raw = message[len("/whitelist"):].strip()
                    domain = add_to_whitelist(raw)
                    send_message(f"✅ {domain} added to whitelist.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't add to the whitelist, can we try again? Details: {e}")
            elif _is_command(message, "/blacklist"):
                try:
                    raw = message[len("/blacklist"):].strip()
                    domain = remove_from_whitelist(raw)
                    if domain:
                        send_message(f"❌ {domain} removed from whitelist.")
                    else:
                        send_message(f"Domain already not existent in whitelist.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't remove from the whitelist, can we try again? Details: {e}")
            elif _is_command(message, "/listwhitelist"):
                whitelist = read_whitelist()
                send_message(f"📝 Whitelist:\n" + "\n".join(whitelist) if whitelist else "📝 Whitelist is empty.")
            elif _is_command(message, "/commands"):
                import json
                with open("connectors/commands.json") as f:
                    commands = json.load(f)["commands"]
                command_list = "\n".join([f"/{c['command']} - {c['description']}" for c in commands])
                send_message(f"Available commands:\n{command_list}")
            elif _is_command(message, "/internet"):
                internet = check_internet_connection()
                send_message(
                    "🌐 Internet check:\n"
                    f"Status: {internet['connection_state']}\n"
                    f"Public IP: {internet['public_ip']}\n"
                    f"Country: {internet['client_country_code']}\n"
                    f"Datacenter: {internet['edge_datacenter']}\n"
                    f"HTTP: {internet['http_protocol']}\n"
                    f"TLS: {internet['tls_version']}\n"
                    f"WARP: {internet['using_warp']}\n"
                    f"Gateway: {internet['using_gateway']}"
                )
            elif _is_command(message, "/update"):
                try:
                    send_message("🔄 Running self update...")
                    update_result = run_self_update()
                    send_message(update_result["message"])
                    if update_result["restart_needed"]:
                        restart_process()
                except Exception as e:
                    send_message(f"Sorry, I couldn't update right now, can we try again? Details: {e}")
            elif _is_command(message, "/restart"):
                try:
                    send_message("🔄 Restarting now...")
                    restart_process()
                except Exception as e:
                    send_message(f"Sorry, I couldn't restart right now, can we try again? Details: {e}")
            elif _is_command(message, "/model"):
                send_message(os.getenv("LLM_MODEL", "unknown"))
            elif _is_command(message, "/help"):
                try:
                    # Prints README.md content
                    with open("README.md") as f:
                        readme_content = f.read()
                    send_message(readme_content)
                except Exception as e:
                    send_message(f"Sorry, I couldn't read the README file, can we try again? Details: {e}")
            else:
                response = prompt(f"User said: {message}")
                send_message(response)