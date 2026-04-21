import os
from connectors.api_connector import send_api_message, read_api_messages
from connectors.telegram_connector import send_telegram_message, read_telegram_messages, send_telegram_typing_action, register_telegram_commands
from connectors.notebook_connector import add_note, delete_note, read_notes
from connectors.identity_connector import read_identity, write_identity
from connectors.tools_connector import list_tools
from connectors.clock_connector import get_time
from connectors.taskbook_connector import add_task, delete_task, read_tasks
from connectors.routines_connector import add_routine, delete_routine, read_routines
from connectors.whitelist_connector import add_to_whitelist, remove_from_whitelist
from agent import prompt

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
            if "/addtask" in message:
                try:
                    task_text = message.split("/addtask")[1].strip()
                    current_time = get_time("utc")
                    llm_response = prompt(f"Current time: {current_time}\nExtract a task and scheduled timestamp from: \"{task_text}\"\nReply with exactly two lines:\nTASK: <task description>\nTIMESTAMP: <ISO8601 UTC timestamp>")
                    task = llm_response.split("TASK:")[1].split("\n")[0].strip()
                    timestamp = llm_response.split("TIMESTAMP:")[1].strip().split("\n")[0].strip()
                    add_task_response = add_task(timestamp, task)
                    print(add_task_response)
                    send_message(add_task_response)
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the task, can we try again? Details: {e}")
            elif "/listtasks" in message:
                tasks = read_tasks()
                task_list = "\n".join([f"[{task['timestamp']}] {task['id']}. {task['task']}" for task in tasks])
                send_message(f"📑 Current tasks:\n{task_list}")
            elif "/deletetask" in message:
                try:
                    task_id = int(message.split("/deletetask")[1].strip())
                    delete_task(task_id)
                    send_message(f"Task {task_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the task, can we try again? Details: {e}")
            elif "/addroutine" in message:
                try:
                    routine_text = message.split("/addroutine")[1].strip()
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
            elif "/listroutines" in message:
                routines = read_routines()
                routine_list = "\n".join([f"[{r['start_time']} every {r['interval']}s] {r['id']}. {r['task']}" for r in routines])
                send_message(f"🔁 Current routines:\n{routine_list}")
            elif "/deleteroutine" in message:
                try:
                    routine_id = int(message.split("/deleteroutine")[1].strip())
                    delete_routine(routine_id)
                    send_message(f"Routine {routine_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the routine, can we try again? Details: {e}")
            elif "/addnote" in message:
                try:
                    note_text = message.split("/addnote")[1].strip()
                    current_time = get_time("utc")
                    add_note_response = add_note(current_time, note_text)
                    print(add_note_response)
                    send_message(add_note_response)
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the note, can we try again? Details: {e}")
            elif "/listnotes" in message:
                notes = read_notes()
                send_message(f"📔 Current notes:\n{notes}")
            elif "/deletenote" in message:
                try:
                    note_id = int(message.split("/deletenote")[1].strip())
                    delete_note(note_id)
                    send_message(f"Note {note_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the note, can we try again? Details: {e}")
            elif "/listtools" in message:
                tools = list_tools()
                send_message(tools)
            elif "/readidentity" in message:
                identity = read_identity()
                send_message(identity)
            elif "/writeidentity" in message:
                try:
                    identity_content = message.split("/writeidentity")[1].strip()
                    if not identity_content:
                        send_message("Identity content cannot be empty. Try typing the entire command followed by the new identity content in the same line.")
                        continue
                    write_identity(identity_content)
                    identity = read_identity()
                    send_message(f"New identity:\n{identity}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't update the identity, can we try again? Details: {e}")
            elif "/whitelist" in message:
                try:
                    raw = message.split("/whitelist")[1].strip()
                    domain = add_to_whitelist(raw)
                    send_message(f"✅ {domain} added to whitelist.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't add to the whitelist, can we try again? Details: {e}")
            elif "/blacklist" in message:
                try:
                    raw = message.split("/blacklist")[1].strip()
                    domain = remove_from_whitelist(raw)
                    if domain:
                        send_message(f"🗑️ {domain} removed from whitelist.")
                    else:
                        send_message(f"Domain already not existent in whitelist.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't remove from the whitelist, can we try again? Details: {e}")
            elif "/model" in message:
                send_message(os.getenv("LLM_MODEL", "unknown"))
            elif "/help" in message:
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