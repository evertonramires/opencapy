import json
import os
from datetime import datetime, timedelta, timezone
from connectors.api_connector import send_api_message, read_api_messages
from connectors.telegram_connector import send_telegram_message, read_telegram_messages, send_telegram_typing_action, register_telegram_commands, edit_telegram_message
from connectors.notebook_connector import add_note, delete_note, read_notes
from connectors.identity_connector import read_identity, write_identity
from connectors.tools_connector import list_tools
from connectors.clock_connector import get_time
from connectors.taskbook_connector import add_task, delete_task, read_tasks
from connectors.routines_connector import add_routine, delete_routine, read_routines
from connectors.calendar_connector import (
    create_calendar_oauth_session,
    list_calendar_events,
    add_calendar_event,
    delete_calendar_event,
)
from connectors.vikunja_connector import (
    add_todo,
    add_todo_comment,
    configure_triage_projects,
    list_todos,
    complete_todo,
    delete_todo,
    get_todo,
    merge_todos,
    restore_todo_title,
    take_blocked_capture,
    retitle_enabled,
    set_todo_action,
    set_todo_quadrant,
    todo_action_buttons,
    triage_enabled,
    undo_title_buttons,
    untriaged_todos,
    update_todo,
)
from connectors.autopilot_connector import autopilot_enabled, read_queue, remaining_today
from connectors.coder_connector import accept_coding_offer, coder_enabled, start_next_coding_job, stop_coding_work, stop_report_html
from connectors.journal_connector import journal_enabled, read_journal
from connectors.sprint_connector import (
    default_minutes,
    end_sprint,
    extend_sprint,
    get_sprint,
    sprints_enabled,
    start_sprint,
)
from connectors.human_connector import read_human_tasks, get_human_task, delete_human_task
from connectors.approval_connector import (
    delete_approval,
    execute_approval,
    get_approval,
    pending_tweak,
    read_approvals,
    set_awaiting_tweak,
)
from connectors.whitelist_connector import add_to_whitelist, remove_from_whitelist, read_whitelist
from connectors.internet_connector import check_internet_connection
from connectors.update_connector import run_self_update, restart_process
from connectors.claude_code_connector import claude_code_enabled, claude_settings, set_claude_effort, set_claude_model
from connectors.usage_connector import claude_usage, buffer_threshold_percent
from connectors.buffer_connector import add_buffered, delete_buffered, read_buffered
from connectors.llm_connector import pop_model_used
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


def _rework_approval(approval: dict, instructions: str) -> None:
    """Drops the old draft and lets the agent redraft it, which re-parks a fresh
    approval, so a corrected message still needs an explicit OK before it goes out."""
    send_message(f"✏️ Reworking the {approval['label']}...")
    delete_approval(approval["id"])
    response = prompt(
        f"[system] The user reviewed a {approval['label']} you drafted and asked for changes before it goes out.\n\n"
        f"Original draft ({approval['tool']}): {json.dumps(approval['args'])}\n"
        f"What they want changed: {instructions}\n\n"
        f"Call {approval['tool']} again with the corrected content. It will be shown to them for approval again, "
        f"so do not claim it was sent."
    )
    send_message(response)

def register_commands():
    register_telegram_commands()

def send_message(message: str, buttons=None) -> int | None:
    """Returns the Telegram message id when there is one, so callers holding a card
    with buttons can rewrite it once the user decides. The web UI has no buttons, so
    it just receives the text and the typed command stays the way in from there.

    Every message that had a model behind it gets signed with that model's name,
    popped so a mechanical message sent right after never wears a stale signature."""
    watermark = pop_model_used()
    message_id = send_telegram_message(message, buttons, watermark=watermark)
    send_api_message(f"{message}\n\n· {watermark}" if watermark else message)
    return message_id

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
            elif _is_command(message, "/listpending"):
                pending_tasks = read_human_tasks()
                if pending_tasks:
                    pending_list = "\n".join([
                        f"[{task['timestamp']}] {task['id']}. {task.get('title', 'Human guidance')} - {task.get('question', task.get('title', ''))}"
                        for task in pending_tasks
                    ])
                    send_message(f"🤝 Pending human tasks:\n{pending_list}")
                else:
                    send_message("🤝 No pending human tasks.")
            elif _is_command(message, "/deleteroutine"):
                try:
                    routine_id = int(message[len("/deleteroutine"):].strip())
                    delete_routine(routine_id)
                    send_message(f"Routine {routine_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the routine, can we try again? Details: {e}")
            elif _is_command(message, "/addtodo"):
                try:
                    todo_text = message[len("/addtodo"):].strip()
                    if not todo_text:
                        send_message("Usage: /addtodo <to-do title>\nExample: /addtodo Buy groceries")
                        continue
                    result = add_todo(todo_text)
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't add the to-do. {result.get('message')}\nDetails: {result.get('details', '')}")
                        continue
                    if result.get("status") == "duplicate":
                        # Nothing was created, so the way forward has to be one tap: the
                        # capture itself is held and replayed by /addtodoanyway
                        existing = result["existing"][0]["todo"]
                        already_done = " (already done)" if existing.get("done") else ""
                        send_message(
                            f"🔁 You already have this one: {existing['id']}. {existing['title']}{already_done}\n"
                            f"Nothing added, so it doesn't show up twice.",
                            buttons=[[("➕ Add it anyway", "/addtodoanyway")]],
                        )
                        continue
                    todo = result.get("todo", {})
                    message_text = f"✅ To-do added: {todo.get('title', todo_text)} (id: {todo.get('id')})"
                    if result.get("similar"):
                        close = result["similar"][0]["todo"]
                        message_text += f"\n🔁 Close to this one, in case it's the same thing: {close['id']}. {close['title']}"
                    send_message(message_text)
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the to-do, can we try again? Details: {e}")
            elif _is_command(message, "/addtodoanyway"):
                try:
                    capture = take_blocked_capture()
                    if not capture:
                        send_message("Nothing waiting to be added. Use /addtodo <title> to capture something new.")
                        continue
                    result = add_todo(**capture, allow_duplicate=True)
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't add the to-do. {result.get('message')}\nDetails: {result.get('details', '')}")
                        continue
                    todo = result.get("todo", {})
                    send_message(f"✅ To-do added: {todo.get('title')} (id: {todo.get('id')})")
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the to-do, can we try again? Details: {e}")
            elif _is_command(message, "/mergetodo"):
                try:
                    source_id, target_id = (int(part) for part in message[len("/mergetodo"):].split())
                except Exception:
                    send_message("Usage: /mergetodo <duplicate_id> <keep_id>. Example: /mergetodo 31 12")
                    continue
                try:
                    result = merge_todos(source_id, target_id)
                    if result.get("status") != "success":
                        send_message(f"Sorry, I couldn't merge those to-dos. {result.get('message')}\nDetails: {result.get('details', '')}")
                        continue
                    conflicts = "\n⚠️ Kept the dates and priority already on it: " + json.dumps(result["conflicts"]) if result["conflicts"] else ""
                    send_message(
                        f"🔗 Merged into {target_id}. {result['todo']['title']}\n"
                        f"'{result['merged_title']}' is now a line on that to-do instead of a second one.{conflicts}"
                    )
                except Exception as e:
                    send_message(f"Sorry, I couldn't merge those to-dos, can we try again? Details: {e}")
            elif _is_command(message, "/listtodos"):
                try:
                    include_done = message[len("/listtodos"):].strip().lower() == "all"
                    todos = list_todos(include_done=include_done)
                    if isinstance(todos, dict) and todos.get("status") == "error":
                        send_message(f"Sorry, I couldn't list the to-dos. {todos.get('message')}\nDetails: {todos.get('details', '')}")
                        continue
                    if not todos:
                        send_message("✅ No pending to-dos found.")
                        continue
                    todo_list = "\n".join([
                        f"{'☑️' if todo['done'] else '⬜'} {todo['id']}. {todo['title']}" + (f" (due {todo['due_date']})" if todo['due_date'] else "")
                        for todo in todos
                    ])
                    send_message(f"✅ Current to-dos:\n{todo_list}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't list the to-dos, can we try again? Details: {e}")
            elif _is_command(message, "/donetodo"):
                try:
                    todo_id = int(message[len("/donetodo"):].strip())
                    result = complete_todo(todo_id)
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't complete the to-do. {result.get('message')}\nDetails: {result.get('details', '')}")
                        continue
                    send_message(f"☑️ To-do {todo_id} marked as done.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't complete the to-do, can we try again? Details: {e}")
            elif _is_command(message, "/focus"):
                try:
                    todos = list_todos()
                    if isinstance(todos, dict) and todos.get("status") == "error":
                        send_message(f"Sorry, I couldn't check the to-dos. {todos.get('message')}\nDetails: {todos.get('details', '')}")
                        continue
                    if not todos:
                        send_message("🎯 Nothing pending, you're all clear! Enjoy it 🎉")
                        continue
                    response = prompt(
                        "[system] The user asked what to focus on right now. These are their pending to-dos: "
                        f"{json.dumps(todos)}. Pick exactly one (due or overdue first, otherwise the one that unblocks the most), "
                        "and give a first step so small it takes two minutes. Offer to check in on them in about 25 minutes "
                        "(if they say yes later, schedule it with the taskbook). Be brief and encouraging, never mention the rest of the list."
                    )
                    send_message(f"🎯 {response}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't pick a focus, can we try again? Details: {e}")
            elif _is_command(message, "/deletetodo"):
                try:
                    todo_id = int(message[len("/deletetodo"):].strip())
                    result = delete_todo(todo_id)
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't delete the to-do. {result.get('message')}\nDetails: {result.get('details', '')}")
                        continue
                    send_message(f"🗑️ To-do {todo_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the to-do, can we try again? Details: {e}")
            elif _is_command(message, "/calendarauth"):
                try:
                    result = create_calendar_oauth_session()
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't start calendar OAuth. {result.get('message')}")
                        continue
                    send_message(
                        "🔐 Google Calendar OAuth started.\n"
                        f"Open this link:\n{result.get('auth_url')}\n\n"
                        f"{result.get('network_hint', '')}\n\n"
                        "After approval, the callback validates automatically in this system."
                    )
                except Exception as e:
                    send_message(f"Sorry, I couldn't start calendar OAuth, can we try again? Details: {e}")
            elif _is_command(message, "/listcalendar"):
                try:
                    raw = message[len("/listcalendar"):].strip()
                    days_ahead = int(os.getenv("CALENDAR_DEFAULT_DAYS_AHEAD", "7"))
                    max_results = int(os.getenv("CALENDAR_DEFAULT_MAX_RESULTS", "10"))
                    if raw:
                        args = raw.split()
                        if len(args) >= 1:
                            days_ahead = int(args[0])
                        if len(args) >= 2:
                            max_results = int(args[1])
                    events = list_calendar_events(days_ahead=days_ahead, max_results=max_results)
                    if isinstance(events, dict) and events.get("status") == "error":
                        send_message(f"Sorry, I couldn't list calendar events. {events.get('message')}\nDetails: {events.get('details', '')}")
                        continue
                    if not events:
                        send_message("📅 No upcoming calendar events found.")
                        continue
                    event_list = "\n".join([
                        f"[{event['start']}] {event.get('summary', '(no title)')} - id: {event['id']}"
                        for event in events
                    ])
                    send_message(f"📅 Upcoming calendar events:\n{event_list}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't list calendar events, can we try again? Details: {e}")
            elif _is_command(message, "/addcalendarevent"):
                try:
                    raw = message[len("/addcalendarevent"):].strip()
                    parts = [part.strip() for part in raw.split("|")]
                    if len(parts) < 3 or not parts[0] or not parts[1] or not parts[2]:
                        send_message(
                            "Usage: /addcalendarevent <summary> | <start_iso_utc> | <end_iso_utc> | <optional_description>\n"
                            "Example: /addcalendarevent Team sync | 2026-04-25T14:00:00Z | 2026-04-25T14:30:00Z | Weekly check-in"
                        )
                        continue
                    summary = parts[0]
                    start_time = parts[1]
                    end_time = parts[2]
                    description = parts[3] if len(parts) > 3 else ""
                    result = add_calendar_event(summary, start_time, end_time, description)
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't add the calendar event. {result.get('message')}\nDetails: {result.get('details', '')}")
                        continue
                    event = result.get("event", {})
                    send_message(
                        f"📅 Event created: {event.get('summary', summary)}\n"
                        f"ID: {event.get('id')}\n"
                        f"Start: {event.get('start')}\n"
                        f"End: {event.get('end')}"
                    )
                except Exception as e:
                    send_message(f"Sorry, I couldn't add the calendar event, can we try again? Details: {e}")
            elif _is_command(message, "/deletecalendarevent"):
                try:
                    event_id = message[len("/deletecalendarevent"):].strip()
                    if not event_id:
                        send_message("Usage: /deletecalendarevent <event_id>\nUse /listcalendar to find event ids.")
                        continue
                    result = delete_calendar_event(event_id)
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't delete the calendar event. {result.get('message')}\nDetails: {result.get('details', '')}")
                        continue
                    send_message(f"🗑️ Calendar event {event_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete the calendar event, can we try again? Details: {e}")
            elif _is_command(message, "/answer"):
                try:
                    raw = message[len("/answer"):].strip()
                    parts = raw.split(" ", 1)
                    if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
                        send_message("Usage: /answer <id> <response>\nUse /listpending to check open task ids.")
                        continue
                    task_id = int(parts[0].strip())
                    answer = parts[1].strip()
                    task = get_human_task(task_id)
                    if not task:
                        send_message(f"Pending task {task_id} not found. Use /listpending to check open task ids.")
                        continue
                    # A tapped button sends "#<index>" because callback data is too small
                    # to carry the answer text itself
                    if answer.startswith("#") and answer[1:].isdigit():
                        options = task.get("options") or []
                        index = int(answer[1:])
                        if index >= len(options):
                            send_message(f"That option is no longer available for task {task_id}. Reply with /answer {task_id} <response>.")
                            continue
                        answer = options[index]
                    task_title = task.get("title", "Human guidance")
                    task_question = task.get("question", task_title)
                    task_description = task.get("description", "")
                    original_user_prompt = task.get("original_user_prompt", "")
                    send_message(f"✅ Answer received for pending task [ {task_id} ] ({task_title}). Continuing now...")
                    # Delete before the (slow) prompt so a second /answer can't re-run it
                    delete_human_task(task_id)
                    response = prompt(
                        f"[system] Human answered your pending clarification task.\n\n"
                        f"Task ID: {task['id']}\n"
                        f"Task timestamp (UTC): {task['timestamp']}\n"
                        f"Original user prompt: {original_user_prompt}\n"
                        f"Task title: {task_title}\n"
                        f"Question asked to user: {task_question}\n"
                        f"Task summary before asking help: {task_description}\n"
                        f"Human answer: {answer}\n\n"
                        f"Continue from where you stopped and respond to the user."
                    )
                    send_message(response)
                except Exception as e:
                    send_message(f"Sorry, I couldn't process your answer, can we try again? Details: {e}")
            elif _is_command(message, "/sprint"):
                try:
                    if not sprints_enabled():
                        send_message("Sprints are disabled. To enable them, set ENABLE_SPRINTS=true in your .env file.")
                        continue
                    raw = message[len("/sprint"):].strip().split()
                    if not raw or not raw[0].isdigit():
                        send_message("Usage: /sprint <todo_id> [minutes]\nUse /listtodos to find the id.")
                        continue
                    todo_id = int(raw[0])
                    minutes = int(raw[1]) if len(raw) > 1 and raw[1].isdigit() else default_minutes()
                    found = get_todo(todo_id)
                    if found.get("status") != "success":
                        send_message(f"Sorry, I couldn't find that to-do. {found.get('message')}")
                        continue
                    title = found["todo"]["title"]
                    sprint = start_sprint(todo_id, title, minutes)
                    extra = " (dropped the one already running)" if sprint["replaced"] else ""
                    send_message(f"⏳ {minutes} minutes on **{title}**, starting now{extra}. I'll check in when it's up.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't start that, can we try again? Details: {e}")
            elif _is_command(message, "/sprintdone"):
                try:
                    sprint = get_sprint(int(message[len("/sprintdone"):].strip()))
                    if not sprint:
                        send_message("That sprint is already wrapped up.")
                        continue
                    end_sprint(sprint["id"])
                    result = complete_todo(sprint["todo_id"])
                    if result.get("status") == "error":
                        send_message(f"🎉 Nice work on {sprint['title']}! I couldn't tick it off in Vikunja though: {result.get('message')}")
                        continue
                    send_message(f"🎉 **{sprint['title']}** done and ticked off. That's the hard part over.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't close that sprint, can we try again? Details: {e}")
            elif _is_command(message, "/sprintmore"):
                try:
                    parts = message[len("/sprintmore"):].strip().split()
                    sprint = get_sprint(int(parts[0]))
                    if not sprint:
                        send_message("That sprint is already wrapped up. Start a new one with /sprint <todo_id>.")
                        continue
                    minutes = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
                    extend_sprint(sprint["id"], minutes)
                    send_message(f"⏳ {minutes} more minutes on **{sprint['title']}**. Keep going.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't extend that, can we try again? Details: {e}")
            elif _is_command(message, "/sprintstuck"):
                try:
                    sprint = get_sprint(int(message[len("/sprintstuck"):].strip()))
                    if not sprint:
                        send_message("That sprint is already wrapped up.")
                        continue
                    end_sprint(sprint["id"])
                    response = prompt(
                        f"[system] The user just spent {sprint['minutes']} minutes on the to-do '{sprint['title']}' "
                        f"(id {sprint['todo_id']}) and said they're stuck. Getting stuck is information, not failure, so no "
                        "sympathy speech and absolutely no guilt. Ask exactly one short question to find where it jammed, "
                        "or if it's obvious the task is too big, offer to shrink it to a first step so small it's almost silly. "
                        "Two sentences maximum."
                    )
                    send_message(f"🤔 {response}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't handle that, can we try again? Details: {e}")
            elif _is_command(message, "/shrink"):
                try:
                    todo_id = int(message[len("/shrink"):].strip())
                    found = get_todo(todo_id)
                    if found.get("status") != "success":
                        send_message(f"Sorry, I couldn't find that to-do. {found.get('message')}")
                        continue
                    response = prompt(
                        f"[system] This to-do has been sitting untouched and the user wants it made smaller: "
                        f"{json.dumps(found['todo'])}. Rewrite it with update_todo so the title is one concrete action "
                        "they could finish in about ten minutes, keeping the rest for later in the description. "
                        "Then tell them the new version in one short sentence. No lecture about why it stalled."
                    )
                    send_message(f"🔪 {response}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't shrink that, can we try again? Details: {e}")
            elif _is_command(message, "/undotitle"):
                try:
                    todo_id = int(message[len("/undotitle"):].strip())
                    result = restore_todo_title(todo_id)
                    if result.get("status") != "success":
                        send_message(f"Sorry, I couldn't put that title back. {result.get('message')}")
                        continue
                    send_message(f"↩️ Back to your words: **{result['title']}**")
                except Exception as e:
                    send_message(f"Usage: /undotitle <todo_id>. Details: {e}")
            elif _is_command(message, "/retitle"):
                try:
                    if not retitle_enabled():
                        send_message("Title rewriting is off. Set ENABLE_TODO_RETITLE=true to turn it on.")
                        continue
                    todo_id = int(message[len("/retitle"):].strip())
                    found = get_todo(todo_id)
                    if found.get("status") != "success":
                        send_message(f"Sorry, I couldn't find that to-do. {found.get('message')}")
                        continue
                    response = prompt(
                        f"[system] The user wants this to-do's title made easier to start: {json.dumps(found['todo'])}. "
                        "Call improve_todo_title on it, then tell them the new wording in one short sentence. "
                        "If the title is already a clear action, say so and change nothing."
                    )
                    send_message(f"✒️ {response}", buttons=undo_title_buttons())
                except Exception as e:
                    send_message(f"Usage: /retitle <todo_id>. Details: {e}")
            elif _is_command(message, "/triagesetup"):
                try:
                    result = configure_triage_projects()
                    if result.get("status") != "success":
                        send_message(f"Sorry, I couldn't set your boxes up. {result.get('message')}")
                        continue
                    retired = "\nThe old Eisenhower board is gone, the projects say the same thing now." if result["retired_board"] else ""
                    send_message("🧭 Your four boxes are live in Vikunja as projects: " + " · ".join(result["projects"]) + retired)
                except Exception as e:
                    send_message(f"Sorry, I couldn't set your boxes up, can we try again? Details: {e}")
            elif _is_command(message, "/triage"):
                try:
                    if not triage_enabled():
                        send_message("Triage is off. Set ENABLE_TODO_TRIAGE=true to turn it on.")
                        continue
                    todo_id = int(message[len("/triage"):].strip())
                    found = get_todo(todo_id)
                    if found.get("status") != "success":
                        send_message(f"Sorry, I couldn't find that to-do. {found.get('message')}")
                        continue
                    response = prompt(
                        f"[system] The user wants this to-do sorted into their four boxes: {json.dumps(found['todo'])}. "
                        "Call triage_todo on it, then tell them the box in one short sentence and why in a few words. "
                        "If it already has a box, re-decide it honestly rather than agreeing with the old verdict."
                    )
                    send_message(f"🧭 {response}", buttons=todo_action_buttons())
                except Exception as e:
                    send_message(f"Usage: /triage <todo_id>. Details: {e}")
            elif _is_command(message, "/triageall"):
                try:
                    if not triage_enabled():
                        send_message("Triage is off. Set ENABLE_TODO_TRIAGE=true to turn it on.")
                        continue
                    pending = untriaged_todos()
                    if isinstance(pending, dict):
                        send_message(f"Sorry, I couldn't read your to-dos. {pending.get('message')}")
                        continue
                    if not pending:
                        send_message("🧭 Everything's already sorted into a box, nothing waiting.")
                        continue
                    response = prompt(
                        f"[system] The user asked you to sort their unsorted to-dos into the four boxes: {json.dumps(pending)}. "
                        "Call triage_todo once for each. Then give them the shape of it in two or three sentences, how many landed in "
                        "each box and anything that stood out, not a list of every task. No lecture, no advice about the pile."
                    )
                    send_message(f"🧭 {response}", buttons=todo_action_buttons())
                except Exception as e:
                    send_message(f"Sorry, I couldn't sort those, can we try again? Details: {e}")
            elif _is_command(message, "/quadrant"):
                try:
                    if not triage_enabled():
                        send_message("Triage is off. Set ENABLE_TODO_TRIAGE=true to turn it on.")
                        continue
                    parts = message[len("/quadrant"):].strip().split()
                    result = set_todo_quadrant(int(parts[0]), parts[1])
                    if result.get("status") != "success":
                        send_message(f"Sorry, I couldn't move that one. {result.get('message')}")
                        continue
                    send_message(f"🧭 **{result['title']}** is now in {result['quadrant']}.")
                except Exception as e:
                    send_message(f"Usage: /quadrant <todo_id> <urgent-important|not-urgent-important|urgent-not-important|not-urgent-not-important>. Details: {e}")
            elif _is_command(message, "/action"):
                try:
                    if not triage_enabled():
                        send_message("Triage is off. Set ENABLE_TODO_TRIAGE=true to turn it on.")
                        continue
                    parts = message[len("/action"):].strip().split()
                    result = set_todo_action(int(parts[0]), parts[1])
                    if result.get("status") != "success":
                        send_message(f"Sorry, I couldn't retag that one. {result.get('message')}")
                        continue
                    send_message(f"🧭 **{result['title']}** is now tagged {result['action']}.")
                except Exception as e:
                    send_message(f"Usage: /action <todo_id> <do|schedule|delegate|drop>. Details: {e}")
            elif _is_command(message, "/aicode"):
                try:
                    if not coder_enabled():
                        send_message("The coding agent is off. Set ENABLE_CODER=true (with ENABLE_CLAUDE_CODE=true) to turn it on.")
                        continue
                    todo_id = int(message[len("/aicode"):].strip())
                    result = accept_coding_offer(todo_id)
                    if result.get("status") != "success":
                        send_message(f"Sorry, I couldn't start that. {result.get('message')}")
                        continue
                    started = start_next_coding_job(send_message)
                    if started:
                        send_message(f"🧑‍💻 On it: {result['goal']}\nI'll report here when it's done.")
                    else:
                        send_message(f"🧑‍💻 Queued: {result['goal']}\nAnother job is running or today's runs are spent; it starts as soon as there's room.")
                except Exception as e:
                    send_message(f"Usage: /aicode <todo_id>. Details: {e}")
            elif _is_command(message, "/stopcode"):
                try:
                    raw = message[len("/stopcode"):].strip()
                    result = stop_coding_work(int(raw) if raw else 0)
                    if result.get("status") != "success":
                        send_message(f"⏹ {result.get('message')}")
                        continue
                    add_todo_comment(result["todo_id"], stop_report_html(result))
                    send_message(f"⏹ Stopped ({result['stopped']}). Status is in the task's comments.")
                except Exception as e:
                    send_message(f"Usage: /stopcode [todo_id] — no id stops whatever is running. Details: {e}")
            elif _is_command(message, "/journal"):
                try:
                    if not journal_enabled():
                        send_message("The journal is off. Set ENABLE_JOURNAL=true to turn it on.")
                        continue
                    date = message[len("/journal"):].strip()
                    entry = read_journal(date)
                    if entry.get("status") != "success":
                        send_message(f"Sorry, I couldn't read the journal. {entry.get('message')}")
                        continue
                    chose = " (picked by me)" if entry["plan_source"] == "capy" else ""
                    plan_text = "\n".join(f"{i+1}. {task}" for i, task in enumerate(entry["plan"])) or "—"
                    wins_text = "\n".join(f"• {win}" for win in entry["wins"]) or "—"
                    send_message(f"📓 {entry['date']}\nPlan{chose}:\n{plan_text}\nAchieved:\n{wins_text}")
                except Exception as e:
                    send_message(f"Usage: /journal [YYYY-MM-DD]. Details: {e}")
            elif _is_command(message, "/snooze"):
                try:
                    parts = message[len("/snooze"):].strip().split()
                    todo_id = int(parts[0])
                    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 7
                    due = datetime.now(timezone.utc) + timedelta(days=days)
                    result = update_todo(todo_id, due_date=due.strftime("%Y-%m-%dT%H:%M:%SZ"))
                    if result.get("status") == "error":
                        send_message(f"Sorry, I couldn't move that. {result.get('message')}")
                        continue
                    send_message(f"📅 Pushed **{result['todo']['title']}** out {days} days. Off your plate for now.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't snooze that, can we try again? Details: {e}")
            elif _is_command(message, "/low"):
                try:
                    todos = list_todos()
                    if isinstance(todos, dict) and todos.get("status") == "error":
                        send_message(f"Sorry, I couldn't check the to-dos. {todos.get('message')}")
                        continue
                    if not todos:
                        send_message("Nothing pending. Go rest 🌱")
                        continue
                    response = prompt(
                        "[system] The user is running on empty and wants something easy. These are their pending to-dos: "
                        f"{json.dumps(todos)}. Pick the single smallest one, the one closest to being finishable in a few "
                        "minutes with no thinking. Give it to them plus the first physical action. Two sentences, warm, "
                        "no mention of anything else on the list."
                    )
                    send_message(f"🪶 {response}")
                except Exception as e:
                    send_message(f"Sorry, I couldn't pick one, can we try again? Details: {e}")
            elif _is_command(message, "/approve"):
                try:
                    approval_id = int(message[len("/approve"):].strip())
                    approval = get_approval(approval_id)
                    if not approval:
                        send_message(f"Approval {approval_id} not found, it may already be handled. Use /listapprovals to check.")
                        continue
                    result = execute_approval(approval_id)
                    if result.get("status") != "success":
                        send_message(f"Sorry, I couldn't send it. {result.get('message')}\nThe draft is still waiting, so you can try /approve {approval_id} again.")
                        continue
                    if approval.get("message_id"):
                        edit_telegram_message(approval["message_id"], f"✅ Sent this {approval['label']}.\n\n{approval['summary']}")
                    send_message(f"✅ {approval['label'].capitalize()} sent.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't approve that, can we try again? Details: {e}")
            elif _is_command(message, "/reject"):
                try:
                    approval_id = int(message[len("/reject"):].strip())
                    approval = get_approval(approval_id)
                    if not approval:
                        send_message(f"Approval {approval_id} not found, it may already be handled.")
                        continue
                    delete_approval(approval_id)
                    if approval.get("message_id"):
                        edit_telegram_message(approval["message_id"], f"❌ Dropped this {approval['label']}, nothing was sent.")
                    send_message(f"❌ Dropped it, nothing went out.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't drop that, can we try again? Details: {e}")
            elif _is_command(message, "/tweak"):
                try:
                    raw = message[len("/tweak"):].strip()
                    parts = raw.split(" ", 1)
                    approval_id = int(parts[0].strip())
                    approval = get_approval(approval_id)
                    if not approval:
                        send_message(f"Approval {approval_id} not found, it may already be handled.")
                        continue
                    # Tapping the button carries no instructions, so remember which draft
                    # the next message is about instead of making the user retype the id
                    if len(parts) < 2 or not parts[1].strip():
                        set_awaiting_tweak(approval_id)
                        send_message(f"✏️ What should I change about the {approval['label']}? Just tell me, or send a voice note.")
                        continue
                    _rework_approval(approval, parts[1].strip())
                except Exception as e:
                    send_message(f"Sorry, I couldn't rework that, can we try again? Details: {e}")
            elif _is_command(message, "/listapprovals"):
                approvals = read_approvals()
                if not approvals:
                    send_message("🤝 Nothing waiting for your approval.")
                    continue
                approval_list = "\n".join([f"{a['id']}. [{a['label']}] {a['summary'].splitlines()[0]}" for a in approvals])
                send_message(f"🤝 Waiting for your approval:\n{approval_list}\n\nApprove with /approve <id>, drop with /reject <id>.")
            elif _is_command(message, "/autopilot"):
                if not autopilot_enabled():
                    send_message("Autopilot is disabled. To enable it, set ENABLE_AUTOPILOT=true in your .env file.")
                    continue
                queued = read_queue()
                if not queued:
                    send_message(f"🚀 Nothing queued. I can take on {remaining_today()} more to-do(s) today.")
                    continue
                queue_list = "\n".join([f"{job['todo_id']}. {job['goal']}" for job in queued])
                send_message(f"🚀 Working on these next:\n{queue_list}\n\n{remaining_today()} left in today's budget.")
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
                if not claude_code_enabled():
                    send_message(os.getenv("LLM_MODEL", "unknown"))
                    continue
                model = message[len("/model"):].strip()
                if model:
                    result = set_claude_model(model)
                    if result["status"] == "error":
                        send_message(f"🧠 {result['message']}")
                        continue
                    send_message(f"🧠 Model set to {claude_settings()['model']}, starting from the next message.")
                else:
                    send_message(f"🧠 Current model: {claude_settings()['model']}\nSet another one with /model opus, or /model default")
            elif _is_command(message, "/effort"):
                if not claude_code_enabled():
                    send_message("Effort levels need the Claude Code CLI. To enable it, set ENABLE_CLAUDE_CODE=true in your .env file.")
                    continue
                level = message[len("/effort"):].strip().lower()
                if level:
                    result = set_claude_effort(level)
                    if result["status"] == "error":
                        send_message(f"🎚️ {result['message']}")
                        continue
                    send_message(f"🎚️ Effort set to {claude_settings()['effort'] or 'the CLI default'}, starting from the next message.")
                else:
                    send_message(f"🎚️ Current effort: {claude_settings()['effort'] or 'the CLI default'}\nSet another one with /effort high, or /effort default")
            elif _is_command(message, "/usage"):
                usage = claude_usage()
                if usage.get("status") != "success":
                    send_message(f"Sorry, I couldn't read the usage. {usage.get('message')}")
                    continue
                send_message(
                    f"📊 Claude usage\n"
                    f"5 hour window: {usage['five_hour_percent']}% used, resets in {usage['five_hour_resets_in']}\n"
                    f"7 day window: {usage['seven_day_percent']}% used, resets in {usage['seven_day_resets_in']}\n"
                    f"Background work is buffered from {buffer_threshold_percent()}%. Queued now: {len(read_buffered())} item(s)."
                )
            elif _is_command(message, "/later"):
                task = message[len("/later"):].strip()
                if not task:
                    send_message("Usage: /later <something to do in the next usage window>")
                    continue
                send_message(add_buffered(task, "user"))
            elif _is_command(message, "/listbuffer"):
                buffered = read_buffered()
                if not buffered:
                    send_message("🪫 Nothing buffered for the next usage window.")
                    continue
                buffer_list = "\n".join([f"{item['id']}. [{item['source']}] {item['task']}" for item in buffered])
                send_message(f"🪫 Waiting for the next usage window:\n{buffer_list}")
            elif _is_command(message, "/deletebuffer"):
                try:
                    item_id = int(message[len("/deletebuffer"):].strip())
                    delete_buffered(item_id)
                    send_message(f"🪫 Buffered item {item_id} deleted.")
                except Exception as e:
                    send_message(f"Sorry, I couldn't delete that buffered item, can we try again? Details: {e}")
            elif _is_command(message, "/help"):
                try:
                    # Prints README.md content
                    with open("README.md") as f:
                        readme_content = f.read()
                    send_message(readme_content)
                except Exception as e:
                    send_message(f"Sorry, I couldn't read the README file, can we try again? Details: {e}")
            else:
                # After tapping Change on a draft, the next thing they say is the correction
                tweak = pending_tweak()
                if tweak:
                    _rework_approval(tweak, message)
                    continue
                response = prompt(f"User said: {message}")
                send_message(response, buttons=todo_action_buttons())