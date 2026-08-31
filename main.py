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
    duplicates_for_new_todos,
    get_todo,
    instant_ack_enabled,
    list_todos,
    queue_merge_offer,
    mark_balance_sent,
    mark_comments_seen,
    mark_date_nudge_sent,
    mark_digest_sent,
    mark_focus_sent,
    mark_stale_sweep_sent,
    mark_todos_done,
    mark_todos_seen,
    add_todo_comment,
    plain_comment_text,
    pomodoro_enabled,
    retitle_enabled,
    subtasks_enabled,
    todo_action_buttons,
    triage_enabled,
    vikunja_enabled,
    weekly_quadrant_balance,
    weekly_stale_todos,
    weekly_wins,
)
from connectors.autopilot_connector import autopilot_enabled, cancel_work, fail_job, finish_job, next_job, queue_work
from connectors.coder_connector import coder_enabled, start_next_coding_job, sweep_interrupted_jobs
from connectors.dsh_connector import dsh_enabled, start_task_session, steer_task_session, stop_task_session
from connectors.journal_connector import evening_journal_due, get_plan, journal_enabled, mark_evening_sent
from connectors.approval_connector import expired_approvals
from connectors.sprint_connector import due_sprints, mark_checked_in
from connectors.usage_connector import buffering_active, usage_alert_message
from connectors.buffer_connector import add_buffered, delete_buffered, due_buffered, read_buffered
from agent import prompt
from connectors.chat_connector import register_commands, send_message, read_messages
from datetime import datetime, timezone


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
            "hood/coder.json": '{"offers": [], "queue": []}',
            "hood/dsh_sessions.json": '{}',
            "hood/journal.json": '{"days": {}}',
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
        # A coding job still marked running was killed with the process; requeue it
        # rather than letting silence read as the work having happened
        for interrupted in sweep_interrupted_jobs():
            send_message(f"🧑‍💻 The coding job for to-do {interrupted['todo_id']} was interrupted by a restart, I've put it back in the queue.")
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
                                coder_hint = (
                                    "If instead it needs writing or changing code, a repo, shell commands, or one of the user's machines, "
                                    "label it 'ai-can-code' in the triage call and mention in passing that commenting /start on the task "
                                    "puts an agent on it — never start anything yourself and never present it as already running. "
                                ) if dsh_enabled() else ""
                                autopilot_hint = (
                                    "If you could genuinely move one of these forward on your own, finding a phone number or address, checking opening "
                                    "hours, comparing options or prices, gathering links, drafting a message, then call queue_task_work with its id and "
                                    "exactly what you will find out, and say in a few words that you're on it. Only for research you can really do alone, "
                                    "not for anything needing their body, wallet or personal choice. "
                                    f"{coder_hint}"
                                ) if autopilot_enabled() else ""
                                retitle_hint = (
                                    "A title jotted down in a hurry is often a vague noun the user has to re-decide every time they see it. "
                                    "Where that's the case, call improve_todo_title to rewrite it as the first concrete action, and name the new "
                                    "wording in your reply. Leave the ones that are already clear actions exactly as they are. "
                                ) if retitle_enabled() else ""
                                pomodoro_hint = (
                                    "Estimate the pomodori in the same triage_todo call and mention it only in passing ('about two "
                                    "pomodori'), never as a verdict or a demand. "
                                ) if pomodoro_enabled() else ""
                                triage_hint = (
                                    "Call triage_todo once for each of these: screen urgent and important separately to pick its box, then "
                                    "decide the action (do/schedule/delegate/drop) as its own second question, since the two don't always "
                                    "agree. Mention the box in a few words, as a note not a verdict, and never explain the whole method back "
                                    "to them. Screen every task for whether an AI could take it: 'ai-can-research' for research, drafting, "
                                    "comparing, gathering or summarizing — and when you could genuinely do it alone, queue it with "
                                    "queue_task_work in the same breath — or 'ai-can-code' when it needs code, a repo, shell commands or one "
                                    "of the user's machines, which a /start comment on the task hands to an agent. If it comes out 'drop' or "
                                    "'not-needed', say so gently and leave it entirely up to them, a button will be offered and you must not delete "
                                    "anything yourself. If it comes out 'two-minute', say it's probably faster to just do than to plan. "
                                    f"{pomodoro_hint}"
                                ) if triage_enabled() else ""
                                # A to-do written straight into Vikunja never passes the check
                                # add_todo does, so the same thought lands twice under two
                                # different titles and the list quietly stops being trusted
                                repeats = duplicates_for_new_todos(new_todos)
                                for new_id, matches in repeats.items():
                                    queue_merge_offer(new_id, matches[0]["todo"]["id"], matches[0]["todo"]["title"])
                                duplicate_hint = (
                                    "Some of these look like things already on the list: "
                                    f"{json.dumps({new_id: [match['todo'] for match in matches] for new_id, matches in repeats.items()})}. "
                                    "Say so plainly in one sentence, naming the older to-do so they can recognise it, and leave the decision "
                                    "to them: a merge button is offered on this message. Never merge or delete anything yourself, and don't "
                                    "imply they should have remembered. "
                                ) if repeats else ""
                                # The friendly hello is optional: with it off, the same assessment
                                # happens but the message is one compact line per task, sent only
                                # once the work is done — a receipt, not a conversation
                                opening = (
                                    "Acknowledge them in one or two friendly sentences, mentioning the titles. "
                                    "Capturing the thought was the win, so don't demand decisions. "
                                ) if instant_ack_enabled() else (
                                    "Assess them silently with the tools named below, then reply with exactly one compact line per task — "
                                    "the box, the action, the estimate, anything you queued or offered — no greeting, no praise, and no "
                                    "questions unless something is genuinely blocking. "
                                )
                                response = deferred_prompt(
                                    "[system] The user just added these to-dos directly in Vikunja (not through you): "
                                    f"{json.dumps(new_todos)}. "
                                    f"{opening}"
                                    f"{duplicate_hint}"
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
                                    # /start and /stop are comment commands, matched here
                                    # mechanically: no model ever sits between the user's
                                    # panic button and the kill, or between their go and
                                    # the agent starting. Matched as prefixes, so
                                    # "/start focus on the API first" works and whatever
                                    # follows the command rides along as instructions.
                                    new_texts = [plain_comment_text(c).strip() for c in thread["new_comments"]]
                                    start_texts = [text for text in new_texts if text.lower().startswith("/start")]
                                    if any(text.lower().startswith("/stop") for text in new_texts):
                                        stopped = stop_task_session(todo["id"])
                                        research_cancelled = cancel_work(todo["id"])
                                        if stopped.get("status") == "success":
                                            add_todo_comment(todo["id"], f"<p>⏹ Stopped the agent session <b>{stopped['name']}</b>. Nothing more runs for this task.</p>")
                                            send_message(f"⏹ Stopped the dsh agent on '{todo['title']}'.")
                                        elif research_cancelled:
                                            add_todo_comment(todo["id"], "<p>⏹ Stopped: the queued research was cancelled before it ran. Nothing was changed.</p>")
                                            send_message(f"⏹ Cancelled the queued research on '{todo['title']}'.")
                                        else:
                                            add_todo_comment(todo["id"], "<p>⏹ Nothing was running or queued for this task.</p>")
                                        mark_comments_seen(todo["id"], thread["seen"])
                                        continue
                                    if start_texts:
                                        extra = start_texts[-1][len("/start"):].strip()
                                        if dsh_enabled():
                                            started = start_task_session(todo["id"], todo["title"], todo["description"], thread["thread"], extra)
                                            if started.get("status") == "success":
                                                note = "was already on it, passed your comment along" if started.get("existing") else "started"
                                                add_todo_comment(todo["id"], (
                                                    f"<p>🧠 Agent session <b>{started['name']}</b> {note} — "
                                                    f"watch it at <a href=\"{started['link']}\">{started['link']}</a> (it's in the sidebar under that name).</p>"
                                                    "<p>Comment here to steer it, /stop to cancel.</p>"
                                                ))
                                                send_message(f"🧠 dsh agent {note} on '{todo['title']}'.")
                                            else:
                                                # Marked seen anyway: a broken dsh would otherwise retry
                                                # forever on its own, and a fresh /start comment retries
                                                add_todo_comment(todo["id"], f"<p>⚠️ Couldn't start the dsh agent: {started.get('message')}</p><p>Comment /start again to retry.</p>")
                                                send_message(f"⚠️ Couldn't start the dsh agent on '{todo['title']}': {started.get('message')}")
                                        elif autopilot_enabled():
                                            queue_work(todo["id"], f"Advance this to-do as far as you can alone: research what is needed and write your findings into it. {extra}".strip())
                                            add_todo_comment(todo["id"], "<p>🔎 On it — I'll write what I find into this task. Comment /stop to cancel.</p>")
                                        else:
                                            add_todo_comment(todo["id"], "<p>The dsh agent and autopilot are both off, so nothing to start. Set ENABLE_DSH=true in .env.</p>")
                                        mark_comments_seen(todo["id"], thread["seen"])
                                        continue
                                    # A plain comment on a task with a live agent session is
                                    # steering for that agent, not a conversation with Capy —
                                    # forwarded verbatim so the user drives the work from the
                                    # task thread without opening dsh
                                    forwarded = steer_task_session(todo["id"], " ".join(new_texts))
                                    if forwarded.get("status") == "success":
                                        send_message(f"🧠 Passed your comment on '{todo['title']}' to the dsh agent.")
                                        mark_comments_seen(todo["id"], thread["seen"])
                                        continue
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
                            todays_plan = get_plan(datetime.now(timezone.utc).date().isoformat()) if journal_enabled() else {"plan": []}
                            if todays_plan["plan"]:
                                # The user chose these last night; the morning message is a
                                # reminder of their own decision, not a fresh negotiation
                                focus_prompt = (
                                    "[system] Morning focus time. Last night the user chose these as the first things for today: "
                                    f"{json.dumps(todays_plan['plan'])}. Their pending to-dos, for context: {json.dumps(focus_todos)}. "
                                    "Remind them of their three in the order they gave, then suggest starting with the first, with a first "
                                    "step so small it takes two minutes. Be brief, warm and encouraging — these are their own picks, so no "
                                    "reshuffling, no additions, no guilt."
                                )
                            elif journal_enabled():
                                focus_prompt = (
                                    "[system] Morning focus time, and the user didn't answer last night's journal ask, which is completely "
                                    f"fine. Their pending to-dos: {json.dumps(focus_todos)}. Pick exactly 3 for today — due or overdue first, "
                                    "then urgent and important, then the important but not urgent ones that are easiest to postpone forever — "
                                    "and record them with record_today_plan with chosen_by_capy set true. Then list the three, say in one "
                                    "light clause that you picked since they were away, and suggest starting with the first, with a first step "
                                    "so small it takes two minutes. Warm, brief, zero guilt."
                                )
                            else:
                                focus_prompt = (
                                    "[system] Morning focus time. These are the user's pending to-dos: "
                                    f"{json.dumps(focus_todos)}. Pick at most 6 for today and list them in the order they should be done, hardest "
                                    "first, so the one they'd most like to avoid is at the top and everything after it feels easier. Prefer the "
                                    "ones due or overdue, then the ones labelled as urgent and important, then the important but not urgent ones, "
                                    "which are the easiest to keep postponing forever. Then suggest exactly one to start with, with a first step so "
                                    "small it takes two minutes. Be brief, warm and encouraging. Never mention how many tasks are pending in total, "
                                    "never guilt about overdue ones, and don't explain why you ordered them that way."
                                )
                            response = deferred_prompt(focus_prompt, "daily focus")
                            if response.startswith("⚠️ Failed communicating"):
                                print("⚠️ Vikunja focus: LLM unavailable, will retry on the next heartbeat.")
                            else:
                                if response:
                                    send_message(f"🎯 {response}")
                                mark_focus_sent()
                    evening = evening_journal_due()
                    if isinstance(evening, dict):
                        plan_line = (
                            f"This morning's plan was {json.dumps(evening['todays_plan'])}; weave in one gentle sentence asking how it went. "
                        ) if evening["todays_plan"] else ""
                        pending = list_todos()
                        pending_json = json.dumps(pending if isinstance(pending, list) else [])
                        response = deferred_prompt(
                            "[system] Evening journal time. In one short warm message, ask the user two things: which 3 tasks they want "
                            f"to do first tomorrow — their pending to-dos, to pick from or ignore: {pending_json} — and 3 things they "
                            f"achieved today, however small. {plan_line}"
                            "When they answer, record with record_tomorrow_plan and record_daily_wins; partial answers count and get "
                            "recorded too. Keep the ask to a few lines, no list of rules, no lecture, and don't use tools now.",
                            "evening journal",
                        )
                        if response.startswith("⚠️ Failed communicating"):
                            print("⚠️ Journal: LLM unavailable, will retry on the next heartbeat.")
                        else:
                            if response:
                                send_message(f"📓 {response}")
                            mark_evening_sent()
                    if coder_enabled() and not buffering_active():
                        # Almost always a no-op: only does anything when a tapped offer
                        # sits queued and no job is running
                        start_next_coding_job(send_message)
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
                            "[system] Weekly balance check on the user's four boxes, which are quadrant labels in Vikunja. Open to-dos per box right now: "
                            f"{json.dumps(balance['counts'])}, plus {balance['untriaged']} still unsorted with no box label. Last week's numbers were "
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