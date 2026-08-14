import glob
import json
import os
import re
import signal
import subprocess
import threading
from datetime import datetime, timezone

from connectors.claude_code_connector import claude_code_enabled

CODER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "coder.json")

# The coding agent runs with real shell access and no permission prompts, so nothing
# here ever starts on the agent's own initiative: an offer is a button, and the button
# is the user. One job at a time keeps the machine, the usage window and the blast
# radius all readable. The process handle is held so the panic button has something
# to kill; "stopped" marks a kill as deliberate, so the thread doesn't report a stop
# the user asked for as a failure.
_running_lock = threading.Lock()
_running = {"active": False, "job": None, "process": None, "stopped": False}

CODING_SYSTEM_PROMPT = (
    "You are a coding agent working for the user's personal assistant, Capy. You have a real shell on the "
    "assistant's machine and you work inside the working directory you were started in — keep everything you "
    "make in there unless the task itself says otherwise. You may use ssh to reach the user's other machines "
    "when the notes below name them; never guess at hosts that aren't named.\n"
    "Do the task properly: read before you write, test what you build, and prefer the smallest change that "
    "works. Never send messages, emails or anything outward-facing on the user's behalf.\n"
    "End your reply with a short report in plain text: what you did, where the artifacts live (paths, hosts, "
    "branches), and what, if anything, now needs the user. That report is all the user sees, so write it for "
    "them, not for yourself."
)


def coder_enabled() -> bool:
    return claude_code_enabled() and os.getenv("ENABLE_CODER", "false").lower() in ["true", "1", "yes"]


def _max_per_day() -> int:
    return int(os.getenv("CODER_MAX_PER_DAY", "2"))


def _workdir() -> str:
    return os.path.expanduser(os.getenv("CODER_WORKDIR", "~/coderwork"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_state() -> dict:
    try:
        with open(CODER_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    with open(CODER_PATH, "w") as f:
        json.dump(state, f, indent=4)


def _roll_day(state: dict) -> dict:
    if state.get("day") != _today():
        state["day"] = _today()
        state["done_today"] = 0
    return state


def offer_coding_work(todo_id: int, goal: str) -> dict:
    """Parks an offer to put a coding agent on a to-do. Only ever an offer: a button
    rides to the user on the next message, and nothing runs until they tap it. The
    assistant proposing work and the user authorizing it are two different moments,
    and for an agent holding a shell that separation is the whole safety story."""
    if not coder_enabled():
        return {"status": "error", "tool": "coder", "message": "The coding agent is disabled. To enable it, set ENABLE_CODER=true (and ENABLE_CLAUDE_CODE=true) in your .env file."}
    state = _read_state()
    offers = state.get("offers", [])
    queue = state.get("queue", [])
    if any(offer["todo_id"] == todo_id for offer in offers) or any(job["todo_id"] == todo_id for job in queue):
        return {"status": "success", "message": f"To-do {todo_id} already has a coding offer or job, nothing to do."}
    offers.append({"todo_id": todo_id, "goal": goal, "offered_at": _now()})
    state["offers"] = offers
    _write_state(state)
    return {"status": "success", "message": f"Offered. The user will get a button to start a coding agent on to-do {todo_id}."}


def pop_pending_coder_offers(limit: int = 2) -> list[dict]:
    """Offers not yet turned into buttons, taken off the pending pile the same way
    drops and merges are: they ride the message being composed, and the ones that
    don't fit wait for the next one. The offer itself stays known (accept checks the
    stored goal), only the button-raising is consumed."""
    state = _read_state()
    offers = [offer for offer in state.get("offers", []) if not offer.get("buttoned")]
    for offer in offers[:limit]:
        offer["buttoned"] = True
    if offers:
        state["offers"] = state.get("offers", [])
        _write_state(state)
    return offers[:limit]


def accept_coding_offer(todo_id: int) -> dict:
    """The user tapped. Moves the offer into the job queue; the heartbeat starts it."""
    if not coder_enabled():
        return {"status": "error", "tool": "coder", "message": "The coding agent is disabled."}
    state = _read_state()
    offer = next((o for o in state.get("offers", []) if o["todo_id"] == todo_id), None)
    if not offer:
        return {"status": "error", "tool": "coder", "message": f"No coding offer waiting for to-do {todo_id}. Offers are raised during triage; ask me to look at the task again if you want one."}
    state["offers"] = [o for o in state.get("offers", []) if o["todo_id"] != todo_id]
    state["next_id"] = state.get("next_id", 0) + 1
    state.setdefault("queue", []).append({
        "id": state["next_id"],
        "todo_id": todo_id,
        "goal": offer["goal"],
        "status": "queued",
        "accepted_at": _now(),
    })
    _write_state(state)
    return {"status": "success", "queued": len(state["queue"]), "goal": offer["goal"]}


def read_coding_work() -> dict:
    state = _read_state()
    return {
        "offers": [{k: v for k, v in o.items() if k != "buttoned"} for o in state.get("offers", [])],
        "queue": state.get("queue", []),
        "done_today": _roll_day(state).get("done_today", 0),
        "max_per_day": _max_per_day(),
    }


def sweep_interrupted_jobs() -> list[dict]:
    """Jobs still marked running were killed by a restart — the thread died with the
    process. They go back to queued rather than vanishing: the user authorized them
    once and silence would read as the work having happened."""
    state = _read_state()
    interrupted = [job for job in state.get("queue", []) if job.get("status") == "running"]
    for job in interrupted:
        job["status"] = "queued"
        job["interrupted_at"] = _now()
    if interrupted:
        _write_state(state)
    return interrupted


def start_next_coding_job(send_message) -> bool:
    """Starts the oldest queued job in a background thread, if allowed. The heartbeat
    calls this every pass; almost every call is a cheap no-op. send_message is injected
    so this module never imports the chat stack (which imports vikunja, which would
    import this back for the buttons)."""
    if not coder_enabled():
        return False
    with _running_lock:
        if _running["active"]:
            return False
        state = _roll_day(_read_state())
        _write_state(state)
        if state.get("done_today", 0) >= _max_per_day():
            return False
        job = next((j for j in state.get("queue", []) if j.get("status") == "queued"), None)
        if not job:
            return False
        job["status"] = "running"
        job["started_at"] = _now()
        _write_state(state)
        _running["active"] = True
        _running["job"] = job
        _running["stopped"] = False
    thread = threading.Thread(target=_run_coding_job, args=(job, send_message), daemon=True)
    thread.start()
    return True


def _job_workdir(job: dict, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30] or "task"
    path = os.path.join(_workdir(), f"job-{job['id']}-{slug}")
    os.makedirs(path, exist_ok=True)
    return path


def _finish(job_id: int, status: str) -> None:
    state = _roll_day(_read_state())
    if status == "done":
        state["queue"] = [j for j in state.get("queue", []) if j["id"] != job_id]
        state["done_today"] = state.get("done_today", 0) + 1
    else:
        for j in state.get("queue", []):
            if j["id"] == job_id:
                j["status"] = status
                j[f"{status}_at"] = _now()
    _write_state(state)
    with _running_lock:
        _running["active"] = False
        _running["job"] = None
        _running["process"] = None
        _running["stopped"] = False


def _job_dir_of(job_id: int) -> str:
    matches = glob.glob(os.path.join(_workdir(), f"job-{job_id}-*"))
    return matches[0] if matches else ""


def _workdir_snapshot(job_id: int) -> list[str]:
    """What the job's workdir holds, for the stopped-work report. Local files are the
    part of the state that can be listed mechanically; anything done over ssh can only
    be named as unknown, never guessed at."""
    root = _job_dir_of(job_id)
    if not root:
        return []
    files = []
    for base, _, names in os.walk(root):
        for name in names:
            files.append(os.path.relpath(os.path.join(base, name), root))
    return sorted(files)[:20]


def stop_coding_work(todo_id: int = 0) -> dict:
    """The panic button. Withdraws an offer, cancels a queued job, or kills the running
    one — whichever this to-do is at; with no id, kills whatever is running. Killing is
    mechanical (SIGTERM to the process group, no model in the loop) and the caller gets
    the facts for the status comment: how long it ran, what its workdir holds, and that
    remote state over ssh is unknown rather than pretended clean."""
    if not coder_enabled():
        return {"status": "error", "tool": "coder", "message": "The coding agent is disabled."}
    state = _read_state()
    # A running job outranks everything else the to-do might also have
    with _running_lock:
        job = _running["job"]
        if _running["active"] and job and (not todo_id or job["todo_id"] == todo_id):
            _running["stopped"] = True
            process = _running["process"]
            if process:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except Exception:
                    pass
            started = job.get("started_at", "")
            minutes = 0
            try:
                begun = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                minutes = int((datetime.now(timezone.utc) - begun).total_seconds() // 60)
            except Exception:
                pass
            return {
                "status": "success", "stopped": "running", "todo_id": job["todo_id"], "goal": job["goal"],
                "minutes": minutes, "files": _workdir_snapshot(job["id"]),
                "workdir": _job_dir_of(job["id"]),
            }
    if not todo_id:
        return {"status": "error", "tool": "coder", "message": "Nothing is running."}
    offers = state.get("offers", [])
    if any(o["todo_id"] == todo_id for o in offers):
        state["offers"] = [o for o in offers if o["todo_id"] != todo_id]
        _write_state(state)
        return {"status": "success", "stopped": "offer", "todo_id": todo_id}
    queued = next((j for j in state.get("queue", []) if j["todo_id"] == todo_id and j.get("status") == "queued"), None)
    if queued:
        state["queue"] = [j for j in state.get("queue", []) if j["id"] != queued["id"]]
        _write_state(state)
        return {"status": "success", "stopped": "queued", "todo_id": todo_id, "goal": queued["goal"]}
    return {"status": "error", "tool": "coder", "message": f"No coding offer, queued job or running job found for to-do {todo_id}."}


def stop_report_html(result: dict) -> str:
    """The status comment the stop leaves on the task, built from facts only. An agent
    interrupted mid-thought can't be asked what it finished, so the report never claims
    to know — it says what ran, what's on disk, and what to double-check."""
    if result["stopped"] == "offer":
        return "<p>⏹ Stopped: the coding offer was withdrawn before anything ran. Nothing was changed.</p>"
    if result["stopped"] == "queued":
        return f"<p>⏹ Stopped: the queued coding job ({result['goal']}) was cancelled before it started. Nothing was changed.</p>"
    files = "".join(f"<li>{name}</li>" for name in result["files"])
    files_block = f"<p>Files in its working directory:</p><ul>{files}</ul>" if files else "<p>Its working directory has no files.</p>"
    return (
        f"<p>⏹ Stopped the coding agent after {result['minutes']} minute(s), mid-task: {result['goal']}</p>"
        f"{files_block}"
        "<p>It was interrupted, so treat the state as unfinished: anything it may have done over ssh or outside its "
        "working directory isn't captured here and is worth a look before relying on it.</p>"
    )


def _run_coding_job(job: dict, send_message) -> None:
    """The job itself, on its own thread so an hour of compiling never freezes the
    heartbeat, the chat or the watcher. Everything it touches is either its own state
    file (guarded), the Vikunja API, or Telegram — all plain requests."""
    from connectors.vikunja_connector import get_todo, append_todo_description, add_todo_comment, comments_enabled
    try:
        found = get_todo(job["todo_id"])
        todo = found.get("todo") if found.get("status") == "success" else None
        title = todo["title"] if todo else f"to-do {job['todo_id']}"
        notes = os.getenv("CODER_NOTES", "").strip()
        system_prompt = CODING_SYSTEM_PROMPT + (f"\nNotes from the user about their machines:\n{notes}" if notes else "")
        task_text = (
            f"The task, from the user's to-do list:\n"
            f"Title: {title}\n"
            f"Description: {(todo or {}).get('description') or '(empty)'}\n"
            f"What the assistant judged an agent could do here: {job['goal']}"
        )
        command = [
            os.getenv("CLAUDE_CODE_BINARY", "claude"),
            "-p", task_text,
            "--output-format", "json",
            "--no-session-persistence",
            "--system-prompt", system_prompt,
            "--model", os.getenv("CODER_MODEL", "opus"),
            "--tools", os.getenv("CODER_BUILTIN_TOOLS", "Bash,Read,Write,Edit,Glob,Grep,WebSearch"),
            "--permission-mode", "bypassPermissions",
        ]
        environment = dict(os.environ)
        # Without this the CLI bills an API key instead of using the logged in subscription
        environment.pop("ANTHROPIC_API_KEY", None)
        # Popen in its own session rather than run(): the panic button kills the whole
        # process group, ssh children included, and a handle is what it kills by
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=_job_workdir(job, title),
            env=environment,
            start_new_session=True,
        )
        with _running_lock:
            if _running["stopped"]:
                # The stop landed between spawn and registration; honour it
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            _running["process"] = process
        try:
            stdout, stderr = process.communicate(timeout=int(os.getenv("CODER_TIMEOUT_SECONDS", "3600")))
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.communicate()
            raise RuntimeError(f"timed out after {os.getenv('CODER_TIMEOUT_SECONDS', '3600')}s")
        if _running["stopped"]:
            # The user pulled the plug; the stop path owns the messaging and the
            # status comment, this thread only tidies the state
            _finish(job["id"], "stopped")
            return
        if not stdout.strip():
            raise RuntimeError(stderr.strip() or f"claude exited with code {process.returncode}")
        data = json.loads(stdout)
        if data.get("is_error"):
            raise RuntimeError(data.get("result"))
        report = data["result"].strip()
        # The report lives on the task first, the chat message is just the doorbell
        report_html = "<p>" + "</p><p>".join(line for line in report.splitlines() if line.strip()) + "</p>"
        if todo:
            append_todo_description(job["todo_id"], f"<h4>🧑‍💻 Coding agent</h4>\n{report_html}")
            if comments_enabled():
                add_todo_comment(job["todo_id"], f"<p>Coding agent finished.</p>\n{report_html}")
        _finish(job["id"], "done")
        send_message(f"🧑‍💻 Done with '{title}':\n{report}")
    except Exception as e:
        if _running["stopped"]:
            _finish(job["id"], "stopped")
            return
        _finish(job["id"], "failed")
        send_message(f"🧑‍💻 The coding agent hit a wall on to-do {job['todo_id']}: {e}")
