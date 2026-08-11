import os
import json
import time
import calendar
import random
import sys
import subprocess
import traceback
from dotenv import load_dotenv
load_dotenv()

from connectors.clock_connector import get_time
from connectors.taskbook_connector import delete_task, read_tasks
from connectors.routines_connector import read_routines
from connectors.calendar_connector import calendar_today
from connectors.vikunja_connector import (
    check_todo_comments,
    check_todo_updates,
    comments_enabled,
    daily_dateless_todos,
    daily_focus_todos,
    get_todo,
    mark_balance_sent,
    mark_comments_seen,
    mark_date_nudge_sent,
    mark_digest_sent,
    mark_focus_sent,
    mark_stale_sweep_sent,
    mark_todos_done,
    mark_todos_seen,
    retitle_enabled,
    subtasks_enabled,
    todo_action_buttons,
    triage_enabled,
    vikunja_enabled,
    weekly_quadrant_balance,
    weekly_stale_todos,
    weekly_wins,
)
from connectors.autopilot_connector import autopilot_enabled, fail_job, finish_job, next_job
from connectors.approval_connector import expired_approvals
from connectors.sprint_connector import due_sprints, mark_checked_in
from connectors.usage_connector import buffering_active, usage_alert_message
from connectors.buffer_connector import add_buffered, delete_buffered, due_buffered, read_buffered
from agent import prompt
from connectors.chat_connector import register_commands, send_message, read_messages
from datetime import datetime


heartbeat_interval_seconds = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))
announce_errors = os.getenv("ANNOUNCE_ERRORS", "false").lower()
vikunja_watch_interval_seconds = int(os.getenv("VIKUNJA_WATCH_INTERVAL_SECONDS", 30))
last_vikunja_check = 0
vikunja_watch_error_notified = False

chat_api_host = os.getenv("CHAT_API_HOST", "http://localhost:8000")
chat_api_bind = chat_api_host.replace("http://", "").replace("https://", "")
chat_api_bind_host, chat_api_bind_port = chat_api_bind.split(":")
chat_api_bind_host = os.getenv("CHAT_API_BIND_HOST", chat_api_bind_host)
chat_api_bind_port = os.getenv("CHAT_API_BIND_PORT", chat_api_bind_port)
    
now = int(get_time("timestamp"))
last_heartbeat = now
delta_time = 0

def heartbeat() -> bool:
    global now, last_heartbeat, delta_time
    now = int(get_time("timestamp"))
    delta_time = now - last_heartbeat
    if delta_time >= heartbeat_interval_seconds:
        last_heartbeat = now
        delta_time = 0
        return True
    return False

def deferred_prompt(text: str, source: str) -> str:
    # Above the usage threshold background work waits for the next window instead of burning it
    if buffering_active():
        add_buffered(text, source)
        return ""
    return prompt(text)

if __name__ == "__main__":
    try:
        # if IDENTITY.md and .env doesn't exist, create them with default content
        if not os.path.exists("IDENTITY.md"):
            print("⚙️ IDENTITY.md not found, creating with default content. Make sure to update it later!")
            with open("IDENTITY.md.EXAMPLE") as src, open("IDENTITY.md", "w") as dst:
                dst.write(src.read())
        if not os.path.exists(".env"):
            print("⚙️ .env not found, creating with default content. Make sure to update it later!")
            with open(".env.EXAMPLE") as src, open(".env", "w") as dst:
                dst.write(src.read())
        
        hood_files = {
            "hood/memory.json": '{"memory": []}',
            "hood/routines.json": '{"routines": []}',
            "hood/taskbook.json": '{"tasks": []}',
            "hood/human_pending.json": '{"tasks": []}',
            "hood/calendar_oauth.json": '{"state": "", "refresh_token": "", "redirect_uri": ""}',  
            "hood/whitelist.json": '[]',
            "hood/buffer.json": '{"items": []}',
            "hood/approvals.json": '{"approvals": []}',
            "hood/autopilot.json": '{"queue": []}',
            "hood/sprints.json": '{"sprints": []}',
            "hood/claude_code.json": '{"model": "", "effort": "", "notified_for_reset": 0}',
            "hood/notebook.md": "",
        }
        for path, default in hood_files.items():
            valid = False
            if os.path.exists(path):
                try:
                    if path.endswith(".json"):
                        json.loads(open(path).read())
                    valid = True
                except Exception:
                    pass
            if not valid:
                print(f"⚙️ {path} missing or invalid, recreating with default content.")
                with open(path, "w") as f:
                    f.write(default)

        register_commands()
        try:
            subprocess.Popen([sys.executable, "-m", "uvicorn", "api.api:app", "--host", chat_api_bind_host, "--port", chat_api_bind_port], stdout=subprocess.DEVNULL)
        except Exception as e:
            print(f"⚠️ Failed to start API: {e}")
        time.sleep(2)  # Wait for API server to start
        print("\n\n⚙️ Waking up your Capy, this may take a minute..")
        send_message("⚙️ Waking up your Capy, this may take a minute...")
        wake_style = random.choice([
            "fun and playful",
            "sleepy and grumpy but lovable",
            "dramatic and theatrical",
            "chill and minimal, barely a word",
            "overly formal butler style, tongue in cheek",
            "like you overslept and are pretending you didn't",
        ])
        wake_message = prompt(f"[system] Wake up! Greet the user in a {wake_style} way, in one or two short sentences. Do not reuse greetings or phrasing from your memory.")
        send_message(f"{wake_message}\n\n🟢 Ready to work!")
        print(f"\n\nNavigate to {chat_api_host}/ to start chatting.\n\n🟢 Ready to work!\n\n")

        while True:
            try:
                time.sleep(1)
                if heartbeat():
                    read_messages()
                    # Read tasks and execute if in time
                    tasks = read_tasks()
                    for task in tasks:
                        task_time = calendar.timegm(time.strptime(task["timestamp"], "%Y-%m-%dT%H:%M:%SZ"))
                        if now >= task_time:
                            response = deferred_prompt(f"[system] This task just triggered, if it requires a tool, execute, if not, treat as a notification to the user: {task['task']}", "task")
                            if response:
                                send_message(f"🕰️ {response}")
                            delete_task(task["id"])
                    routines = read_routines()
                    for routine in routines:
                        routine_start = calendar.timegm(time.strptime(routine["start_time"], "%Y-%m-%dT%H:%M:%SZ"))
                        if now >= routine_start and (now - routine_start) % routine["interval"] < heartbeat_interval_seconds:
                            response = deferred_prompt(f"[system] This routine just triggered, if it requires a tool, execute, if not, treat as a notification to the user: {routine['task']}", "routine")
                            if response:
                                send_message(f"♾️ {response}")
                    calendar_events = calendar_today()
                    if isinstance(calendar_events, list) and calendar_events:
                        response = deferred_prompt(f"[system] These are today's calendar events: {calendar_events}. If it requires a tool, execute, if not, treat as a notification to the user.", "calendar")
                        if response:
                            send_message(f"📅 {response}")
                    elif isinstance(calendar_events, dict):
                        print(f"⚠️ Calendar daily check failed: {calendar_events.get('message')}")
                    if vikunja_enabled() and now - last_vikunja_check >= vikunja_watch_interval_seconds:
                        last_vikunja_check = now
                        todo_updates = check_todo_updates()
                        if todo_updates.get("status") != "success":
                            if not vikunja_watch_error_notified:
                                vikunja_watch_error_notified = True
                                if announce_errors == "true":
                                    send_message(f"⚠️ Vikunja watcher: {todo_updates.get('message')}")
                                print(f"⚠️ Vikunja watcher: {todo_updates.get('message')}")
                        else:
                            vikunja_watch_error_notified = False
                            new_todos = todo_updates["new"]
                            completed_todos = todo_updates["completed"]
                            if new_todos:
                                breakdown_hint = (
                                    "If one is clearly a multi-step project, break it into 3 to 6 small steps with add_subtasks and mention you did; they "
                                    "become a checklist inside that to-do rather than new to-dos, so the list stays the same length. If the breakdown "
                                    "isn't obvious, don't guess, just acknowledge. "
                                ) if subtasks_enabled() else ""
                                # Triage rides along with the acknowledgement instead of costing a second call
                                autopilot_hint = (
                                    "If you could genuinely move one of these forward on your own, finding a phone number or address, checking opening "
                                    "hours, comparing options or prices, gathering links, drafting a message, then call queue_task_work with its id and "
                                    "exactly what you will find out, and say in a few words that you're on it. Only for research you can really do alone, "
                                    "not for anything needing their body, wallet or personal choice. "
                                ) if autopilot_enabled() else ""
                                retitle_hint = (
                                    "A title jotted down in a hurry is often a vague noun the user has to re-decide every time they see it. "
                                    "Where that's the case, call improve_todo_title to rewrite it as the first concrete action, and name the new "
                                    "wording in your reply. Leave the ones that are already clear actions exactly as they are. "
                                ) if retitle_enabled() else ""
                                triage_hint = (
                                    "Call triage_todo once for each of these to file it into the user's four boxes. Mention the box in a few words, "
                                    "as a note not a verdict, and never explain the whole method back to them. If it comes out as 'ai-can-do' and you "
                                    "could genuinely do it alone, queue it with queue_task_work in the same breath. If it comes out 'drop' or "
                                    "'not-needed', say so gently and leave it entirely up to them, a button will be offered and you must not delete "
                                    "anything yourself. If it comes out 'two-minute', say it's probably faster to just do than to plan. "
                                ) if triage_enabled() else ""
                                response = deferred_prompt(
                                    "[system] The user just added these to-dos directly in Vikunja (not through you): "
                                    f"{json.dumps(new_todos)}. Acknowledge them in one or two friendly sentences, mentioning the titles. "
                                    "Capturing the thought was the win, so don't demand decisions. "
                                    f"{retitle_hint}"
                                    f"{triage_hint}"
                                    f"{breakdown_hint}"
                                    f"{autopilot_hint}"
                                    "Ask at most one short optional question, and only if something is clearly time-sensitive and missing a due date. "
                                    "No guilt, no lectures, no tools beyond the ones named here.",
                                    "new to-dos",
                                )
                                if response.startswith("⚠️ Failed communicating"):
                                    print(f"⚠️ Vikunja watcher: LLM unavailable, will retry announcing new to-dos on the next check.")
                                else:
                                    if response:
                                        # The undo rides on the same message: a rewrite the user doesn't
                                        # recognise has to be one tap from their own words coming back
                                        send_message(f"👀 {response}", buttons=todo_action_buttons())
                                    mark_todos_seen([todo["id"] for todo in new_todos])
                            if completed_todos:
                                response = deferred_prompt(
                                    "[system] The user just completed these to-dos in Vikunja: "
                                    f"{json.dumps(completed_todos)}. Cheer them on! One or two sentences, genuine and warm, "
                                    "mentioning what they finished. Finishing things is a real win worth "
                                    "celebrating. No 'what's next', no new demands, don't use tools.",
                                    "completed to-dos",
                                )
                                if response.startswith("⚠️ Failed communicating"):
                                    print(f"⚠️ Vikunja watcher: LLM unavailable, will retry cheering completed to-dos on the next check.")
                                else:
                                    if response:
                                        send_message(f"🎉 {response}")
                                    mark_todos_done([todo["id"] for todo in completed_todos])
                            if comments_enabled():
                                comment_updates = check_todo_comments()
                                if comment_updates.get("status") != "success":
                                    print(f"⚠️ Vikunja comments: {comment_updates.get('message')}")
                                for thread in comment_updates.get("threads", []):
                                    todo = thread["todo"]
                                    response = deferred_prompt(
                                        "[system] The user just commented on one of their own to-dos in Vikunja. They are steering this task, "
                                        "so treat the comment as an instruction about it and act on it, don't just acknowledge.\n\n"
                                        f"To-do {todo['id']}: {todo['title']}\n"
                                        f"Description: {todo['description'] or '(empty)'}\n"
                                        f"The thread so far, oldest first: {json.dumps(thread['thread'])}\n"
                                        f"What they just wrote: {json.dumps(thread['new_comments'])}\n\n"
                                        "Do the thing they asked with the tools you have: change the due date, priority or title, write what you "
                                        "know into the description, break it into steps, mark it done, or take the research on yourself. If it needs "
                                        "digging you can genuinely do alone, queue it. If the next step is outward facing, like an email or a message "
                                        "to someone, draft it with the right tool so it goes to them for approval, and never send it yourself.\n"
                                        "Then always call reply_on_todo on this to-do to answer in the thread, saying plainly what you did or found, "
                                        "so the conversation stays attached to the task. Finally reply here with at most two short sentences. "
                                        "No preamble, no repeating their comment back at them.",
                                        "to-do comment",
                                    )
                                    if response.startswith("⚠️ Failed communicating"):
                                        print(f"⚠️ Vikunja comments: LLM unavailable, will retry to-do {todo['id']} on the next check.")
                                    else:
                                        if response:
                                            send_message(f"💬 {response}", buttons=todo_action_buttons())
                                        mark_comments_seen(todo["id"], thread["seen"])
                    focus_todos = daily_focus_todos()
                    if isinstance(focus_todos, list):
                        if not focus_todos:
                            mark_focus_sent()
                        else:
                            response = deferred_prompt(
                                "[system] Morning focus time. These are the user's pending to-dos: "
                                f"{json.dumps(focus_todos)}. Pick at most 6 for today and list them in the order they should be done, hardest "
                                "first, so the one they'd most like to avoid is at the top and everything after it feels easier. Prefer the "
                                "ones due or overdue, then the ones labelled as urgent and important, then the important but not urgent ones, "
                                "which are the easiest to keep postponing forever. Then suggest exactly one to start with, with a first step so "
                                "small it takes two minutes. Be brief, warm and encouraging. Never mention how many tasks are pending in total, "
                                "never guilt about overdue ones, and don't explain why you ordered them that way.",
                                "daily focus",
                            )
                            if response.startswith("⚠️ Failed communicating"):
                                print("⚠️ Vikunja focus: LLM unavailable, will retry on the next heartbeat.")
                            else:
                                if response:
                                    send_message(f"🎯 {response}")
                                mark_focus_sent()
                    dateless_todos = daily_dateless_todos()
                    if isinstance(dateless_todos, list):
                        if not dateless_todos:
                            mark_date_nudge_sent()
                        else:
                            response = deferred_prompt(
                                "[system] Daily planning nudge. These to-dos have no due date: "
                                f"{json.dumps(dateless_todos)}. In one short friendly message, list them (at most 5) and ask the user "
                                "to reply with rough dates so their Gantt timeline and planning views stay useful. Make clear that rough "
                                "answers like 'friday' or 'next week' are fine and that skipping any of them is ok. "
                                "When they reply later, set the dates with the update_todo tool. No guilt, keep it inviting.",
                                "date nudge",
                            )
                            if response.startswith("⚠️ Failed communicating"):
                                print("⚠️ Vikunja date nudge: LLM unavailable, will retry on the next heartbeat.")
                            else:
                                if response:
                                    send_message(f"🗓️ {response}")
                                mark_date_nudge_sent()
                    # Templated rather than generated: when a timer goes off the point is
                    # that it is instant, and an LLM round trip would make it arrive late
                    for sprint in due_sprints():
                        send_message(
                            f"⏰ Time's up on **{sprint['title']}**. How did it go?",
                            buttons=[
                                [("✅ Done", f"/sprintdone {sprint['id']}"), ("➕ 10 min", f"/sprintmore {sprint['id']}")],
                                [("😵 Stuck", f"/sprintstuck {sprint['id']}")],
                            ],
                        )
                        mark_checked_in(sprint["id"])
                    stale_todos = weekly_stale_todos()
                    if isinstance(stale_todos, list):
                        for todo in stale_todos:
                            since = f" since {todo['updated'][:10]}" if todo["updated"] else ""
                            send_message(
                                f"🧹 This one's been sitting{since}: **{todo['title']}**\n"
                                "No pressure either way, dropping it is a perfectly good answer.",
                                buttons=[
                                    [("🔪 Make it smaller", f"/shrink {todo['id']}"), ("📅 Next week", f"/snooze {todo['id']} 7")],
                                    [("🗑️ Drop it", f"/deletetodo {todo['id']}")],
                                ],
                            )
                        mark_stale_sweep_sent()
                    wins = weekly_wins()
                    if isinstance(wins, list):
                        # Silence when there are no wins: a "you finished nothing" message
                        # is exactly the kind of thing that makes someone stop opening the app
                        if wins:
                            response = deferred_prompt(
                                "[system] Weekly wins. The user finished these to-dos in the last 7 days: "
                                f"{json.dumps(wins)}. Tell them what they got done, warmly and specifically, naming a few. "
                                "This is evidence against their own memory, which undercounts badly. Keep it short, "
                                "no advice, no mention of anything still pending, no 'next week let's...'.",
                                "weekly wins",
                            )
                            if response.startswith("⚠️ Failed communicating"):
                                print("⚠️ Weekly wins: LLM unavailable, will retry on the next heartbeat.")
                            else:
                                if response:
                                    send_message(f"🏆 {response}")
                                mark_digest_sent()
                        else:
                            mark_digest_sent()
                    balance = weekly_quadrant_balance()
                    if isinstance(balance, dict):
                        response = deferred_prompt(
                            "[system] Weekly balance check on the user's four boxes. Open to-dos per box right now: "
                            f"{json.dumps(balance['counts'])}, plus {balance['untriaged']} not yet sorted. Last week's numbers were "
                            f"{json.dumps(balance['last_week'])}. The thing worth noticing is the direction of travel, not the totals: "
                            "'schedule' (important but not urgent) growing is the healthy sign, and a big 'do' pile means they're living in "
                            "firefights. Two or three sentences, curious rather than scored, no advice unless one number really stands out. "
                            "Never call it a report and never suggest they triage more.",
                            "weekly balance",
                        )
                        if response.startswith("⚠️ Failed communicating"):
                            print("⚠️ Weekly balance: LLM unavailable, will retry on the next heartbeat.")
                        else:
                            if response:
                                send_message(f"🧭 {response}")
                            mark_balance_sent(balance["counts"])
                    usage_alert = usage_alert_message()
                    if usage_alert:
                        send_message(f"🪫 {usage_alert} Queued so far: {len(read_buffered())} item(s).")
                    buffered = due_buffered()
                    if buffered:
                        # one per heartbeat, so draining a full queue doesn't immediately burn the fresh window
                        item = buffered[0]
                        response = prompt(f"[system] This work was buffered while the usage window was full ({item['source']}, buffered at {item['timestamp']}): {item['task']}")
                        if response.startswith("⚠️ Failed communicating"):
                            print("⚠️ Work buffer: LLM unavailable, will retry on the next heartbeat.")
                        else:
                            send_message(f"🪫 {response}")
                            delete_buffered(item["id"])
                    for approval in expired_approvals():
                        send_message(
                            f"⌛ The {approval['label']} I drafted for you expired without an answer, so I dropped it and nothing went out.\n\n"
                            f"{approval['summary'].splitlines()[0]}"
                        )
                    # The queue is its own buffer, so above the usage threshold it simply
                    # waits instead of being handed to the work buffer and running twice
                    if autopilot_enabled() and not buffering_active():
                        job = next_job()
                        if job:
                            todo = get_todo(job["todo_id"])
                            if todo.get("status") != "success":
                                if fail_job(job["id"]):
                                    print(f"⚠️ Autopilot: gave up reading to-do {job['todo_id']}, dropped the job.")
                                else:
                                    print(f"⚠️ Autopilot: couldn't read to-do {job['todo_id']}, will retry.")
                            else:
                                todo = todo["todo"]
                                response = prompt(
                                    "[system] Autopilot. You took this to-do on yourself, now do the work.\n\n"
                                    f"To-do {todo['id']}: {todo['title']}\n"
                                    f"Current description: {todo['description'] or '(empty)'}\n"
                                    f"What you said you would find out: {job['goal']}\n\n"
                                    "Research it properly. Then call add_todo_context on this to-do with what you found, as short HTML, "
                                    "leading with the single most useful fact and ending with the concrete next step. "
                                    "If the next step is outward facing, like an email or a message to someone, draft it with the right tool "
                                    "so it goes to the user for approval, and never send it yourself. "
                                    "Then reply with at most two short sentences: what you found, and the one small thing they do next. "
                                    "No preamble, no recap of what you searched."
                                )
                                if response.startswith("⚠️ Failed communicating"):
                                    if fail_job(job["id"]):
                                        print(f"⚠️ Autopilot: LLM unavailable 3 times for to-do {job['todo_id']}, dropped the job.")
                                    else:
                                        print("⚠️ Autopilot: LLM unavailable, will retry on the next heartbeat.")
                                else:
                                    if response:
                                        send_message(f"🔎 {response}", buttons=todo_action_buttons())
                                    finish_job(job["id"])

            except Exception as e:
                try:
                    error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error_type = type(e).__name__
                    frames = traceback.extract_tb(e.__traceback__)
                    connector_frame = next((frame for frame in reversed(frames) if "/connectors/" in frame.filename and frame.filename.endswith("_connector.py")), None)
                    error_frame = connector_frame or frames[-1]
                    error_module = os.path.splitext(os.path.basename(error_frame.filename))[0]
                    error_trace = traceback.format_exc()
                    error_msg = f"\n⚠️ [{error_time}][{error_module}] {error_type}.\n\n{e if announce_errors == "true" else ""}\n🔵 Continuing execution...\n\n"
                    print(error_msg)
                    if announce_errors == "true":
                        send_message(f"⚠️ Error at {error_time}:\nModule: {error_module}\n{error_type}: {e}")
                except Exception:
                    pass
    except KeyboardInterrupt:
        print("\n\n⚙️ Ctrl+C detected, running stop.sh..\n\n")
        subprocess.run(["bash", "stop.sh"])