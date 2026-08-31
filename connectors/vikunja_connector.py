import difflib
import html
import json
import os
import re
import requests
import time
import unicodedata
from datetime import datetime, timezone

_no_due_date = "0001-01-01T00:00:00Z"
_capy_notes_marker = "<h4>🔎 Capy notes</h4>"
_capy_merge_marker = "<h4>➕ Also captured</h4>"
# Only kept to strip it off to-dos split before the steps went bare, never written
_capy_steps_marker = "<h4>✅ Steps</h4>"
_task_list_pattern = r'<ul data-type="taskList">.*?</ul>'
# Comments Capy writes come back from the API authored by the user's own account,
# since that is whose token it holds. Without a marker of its own the watcher would
# read its own replies as new instructions and talk to itself forever. The header is
# visible so the thread is readable in Vikunja; the trailer survives even if someone
# edits the header away.
_capy_comment_header = "<p>🐹 <b>Capy</b></p>"
_capy_comment_marker = "<!-- capy -->"
_seen_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hood", "vikunja_seen.json")
# The triage vocabulary. Slugs are what the code and the model use, titles are what
# the user sees in Vikunja. The quadrant and the action are two separate screenings
# now: urgent × important says what a task is, do/schedule/delegate/drop says what to
# do about it, and though they usually agree they are allowed not to — an urgent and
# important task the user can't do themselves is still a delegate.
_quadrant_slugs = ["urgent-important", "not-urgent-important", "urgent-not-important", "not-urgent-not-important"]
_action_slugs = ["do", "schedule", "delegate", "drop"]
_triage_labels = {
    # The quadrant labels are the boxes now: everything lives in the Inbox and
    # views filter or sort on tags alone
    "urgent-important": ("☸️ urgent and important", "8e44ad"),
    "not-urgent-important": ("🌱 not urgent and important", "27ae60"),
    "urgent-not-important": ("🔥 urgent and not important", "e67e22"),
    "not-urgent-not-important": ("🍂 not urgent and not important", "795548"),
    "do": ("✅ do", "e74c3c"),
    "schedule": ("🗓 schedule", "3498db"),
    "delegate": ("🤝 delegate", "e67e22"),
    "drop": ("✂️ drop", "95a5a6"),
    "not-needed": ("❓ does this need doing?", "9b59b6"),
    # The old single ai-can-do split in two: research the agent does inline,
    # code that a /start comment hands to a dsh session
    "ai-can-research": ("🔎 ai can research", "1abc9c"),
    "ai-can-code": ("🤖 ai can code", "2980b9"),
    "hire-out": ("🧑 hire this out", "16a085"),
    "buy-instead": ("📦 buy this instead", "27ae60"),
    "project": ("🧩 project · needs breaking down", "8e44ad"),
    "two-minute": ("⚡ 2 minutes", "f1c40f"),
    "low-energy": ("🔋 low energy", "7f8c8d"),
    "deep-focus": ("🪫 deep focus", "34495e"),
    "@computer": ("@computer", "2c3e50"),
    "@home": ("@home", "2c3e50"),
    "@errands": ("@errands", "2c3e50"),
    "@calls": ("@calls", "2c3e50"),
    "@waiting-for": ("@waiting-for", "2c3e50"),
}
# What each label was called before, so a redeploy renames the existing labels in
# place instead of creating twins and stranding every task's old assignments
_old_label_titles = {
    "do": "🔥 do · urgent + important",
    "schedule": "📅 schedule · important, not urgent",
    "delegate": "👤 delegate · urgent, not important",
    "drop": "🗑 drop · neither",
    "ai-can-research": "🤖 an AI can do this",
}
_triage_board_title = "Eisenhower"
# The old quadrant slugs doubled as the box names; cached state and callers using
# them still resolve to the box that action usually pairs with
_legacy_quadrant_slugs = {
    "do": "urgent-important",
    "schedule": "not-urgent-important",
    "delegate": "urgent-not-important",
    "drop": "not-urgent-not-important",
}
_pomodoro_label_pattern = r"^🍅 \d+$"
_pomodoro_label_color = "d35400"
_request_timeout_seconds = 15
_request_retries = 2
_request_retry_delays_seconds = [2, 5]

def vikunja_enabled() -> bool:
    return os.getenv("ENABLE_VIKUNJA", "false").lower() in ["true", "1", "yes"]

def subtasks_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_VIKUNJA_SUBTASKS", "false").lower() in ["true", "1", "yes"]

def comments_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_TODO_COMMENTS", "false").lower() in ["true", "1", "yes"]

def retitle_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_TODO_RETITLE", "false").lower() in ["true", "1", "yes"]

def triage_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_TODO_TRIAGE", "false").lower() in ["true", "1", "yes"]

def dedupe_enabled() -> bool:
    return vikunja_enabled() and os.getenv("ENABLE_TODO_DEDUPE", "false").lower() in ["true", "1", "yes"]

def pomodoro_enabled() -> bool:
    return triage_enabled() and os.getenv("ENABLE_TODO_POMODORO", "false").lower() in ["true", "1", "yes"]

def instant_ack_enabled() -> bool:
    """Whether the watcher greets a new to-do with a friendly hello, or waits and
    reports in one compact line once the assessment is done. On by default; turning
    it off is for the user who found the hello arriving before the substance."""
    return os.getenv("ENABLE_TODO_INSTANT_ACK", "true").lower() in ["true", "1", "yes"]

def pomodoro_minutes() -> int:
    return int(os.getenv("POMODORO_MINUTES", "25"))

def pomodoro_break_minutes() -> int:
    return int(os.getenv("POMODORO_BREAK_MINUTES", "5"))

def _disabled_error() -> dict:
    return {"status": "error", "tool": "vikunja", "message": "Vikunja to-do tool is disabled. To enable it, set ENABLE_VIKUNJA=true and configure VIKUNJA_API_HOST and VIKUNJA_API_TOKEN in your .env file."}

def _api_url(path: str) -> str:
    host = os.getenv("VIKUNJA_API_HOST", "").strip().rstrip("/")
    if not host.endswith("/api/v1"):
        host = f"{host}/api/v1"
    return f"{host}{path}"

def _headers() -> dict:
    token = os.getenv("VIKUNJA_API_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def _default_project_id() -> int:
    return int(os.getenv("VIKUNJA_DEFAULT_PROJECT_ID", "1"))

def _request(method: str, path: str, **kwargs) -> requests.Response | dict:
    """Retries when the connection itself fails. A tailnet ingress occasionally
    answers a handshake with a TLS internal error or a DNS blip and recovers on its
    own moments later, which is not worth interrupting the user for. Timeouts are
    retried only for GETs: a timed-out write may mean the request arrived and was
    applied, and re-sending it would be a second write."""
    last_error = None
    retry_timeouts = method.lower() == "get"
    for attempt in range(_request_retries + 1):
        try:
            return requests.request(method, _api_url(path), headers=_headers(), timeout=_request_timeout_seconds, **kwargs)
        except requests.ConnectionError as e:
            last_error = e
        except requests.Timeout as e:
            if not retry_timeouts:
                return {"status": "error", "tool": "vikunja", "message": f"Vikunja is unreachable: {e}"}
            last_error = e
        except requests.RequestException as e:
            return {"status": "error", "tool": "vikunja", "message": f"Vikunja is unreachable: {e}"}
        if attempt < _request_retries:
            time.sleep(_request_retry_delays_seconds[min(attempt, len(_request_retry_delays_seconds) - 1)])
    return {"status": "error", "tool": "vikunja", "message": f"Vikunja is unreachable: {last_error}"}

def _patch_task(todo_id: int, changes: dict) -> requests.Response | dict:
    """Vikunja's task update replaces the whole task rather than merging: any field
    left out of the payload comes back blank. Posting {"done": true} on its own
    therefore erases the description, due date, priority and progress, which is how
    a to-do loses its notes the moment it gets ticked off. Everything that changes a
    task reads it first and writes it back whole."""
    response = _request("get", f"/tasks/{todo_id}")
    if isinstance(response, dict) or not response.ok:
        return response
    task = response.json()
    task.update(changes)
    return _request("post", f"/tasks/{todo_id}", json=task)

def _request_error(response: requests.Response) -> dict:
    try:
        details = response.json().get("message", response.text)
    except Exception:
        details = response.text
    return {"status": "error", "tool": "vikunja", "message": f"Vikunja API request failed with status {response.status_code}.", "details": details}

_quadrant_titles = {_triage_labels[slug][0] for slug in _quadrant_slugs}

def _box_title(task: dict) -> str:
    """The box a to-do is in, read off its quadrant label. The labels are the boxes
    now that everything lives in the Inbox."""
    for label in task.get("labels") or []:
        if (label.get("title") or "") in _quadrant_titles:
            return label["title"]
    return ""

def _simplify_todo(task: dict) -> dict:
    due_date = task.get("due_date") or ""
    if due_date == _no_due_date:
        due_date = ""
    related = task.get("related_tasks") or {}
    subtasks = related.get("subtask") or []
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "description": task.get("description") or "",
        "done": task.get("done", False),
        "due_date": due_date,
        "start_date": "" if task.get("start_date") in (None, _no_due_date) else task["start_date"],
        "end_date": "" if task.get("end_date") in (None, _no_due_date) else task["end_date"],
        # The box a to-do is in is its quadrant label now, everything lives in the Inbox
        "box": _box_title(task),
        "priority": task.get("priority", 0),
        "project_id": task.get("project_id"),
        "percent_done": task.get("percent_done", 0),
        "updated": task.get("updated") or "",
        "done_at": task.get("done_at") or "",
        "is_subtask": bool(related.get("parenttask")),
        "subtasks": [{"id": s.get("id"), "title": s.get("title"), "done": s.get("done", False)} for s in subtasks],
        # Steps live in the description now, so this is where a split-up to-do's
        # progress shows: without it the model can't see what's already ticked off
        "steps": _read_steps(task.get("description") or ""),
        # This projection is the whitelist of what ever reaches the model, so without
        # labels here it would re-triage tasks it has already classified
        "labels": [label.get("title") for label in task.get("labels") or []],
    }

def _plain_text(html_text: str) -> str:
    """Whatever a human would read out of a description: no markup, no entities."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", html_text or ""))).strip()

def _fold(text: str) -> str:
    """Lowercased and stripped of accents, so 'Consultório' and 'consultorio' are the
    same word — the second capture of a thought is rarely typed with the same care as
    the first."""
    stripped = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]", " ", stripped.lower())

# Function words only. Verbs stay in on purpose: 'call mom' and 'buy mom a gift' share
# their only other word, and dropping the verb would collapse them into one to-do.
_capture_stopwords = set(_fold(
    "a an the and or of to for from in on at by with about into my me i you your we us it its this that these those "
    "is are be am was were do does did done have has had need needs want wants should would could will shall "
    "so too also please just now then there here remember reminder todo task "
    "o os as um uma uns umas de do da dos das em no na nos nas ao aos e ou que se por pelo pela para pra pro com sem sobre "
    "meu minha meus minhas seu sua eu voce nos isso isto esse essa este esta aquele aquela "
    "e eh ser estar tem tenho ter preciso precisa quero quer devo deve vou vai ja agora aqui ali tarefa lembrar lembrete"
).split())

def _significant_words(text: str) -> list[str]:
    return [word for word in _fold(_plain_text(text)).split() if word not in _capture_stopwords and (len(word) > 1 or word.isdigit())]

def _same_word(one: str, other: str) -> bool:
    """Counts near-spellings as the same word, so a plural or a typo doesn't hide a
    duplicate. Only for words long enough that a high ratio means something."""
    if one == other:
        return True
    return min(len(one), len(other)) >= 4 and difflib.SequenceMatcher(None, one, other).ratio() >= 0.86

def _word_overlap(mine: list[str], theirs: list[str]) -> float:
    """How much two bags of words say the same thing. Dice on its own would miss the
    case that matters most — the same task written once in a hurry and once with detail
    — so a title whose every word appears in the other counts as a match outright:
    'dentist' sitting entirely inside 'Call the dentist about the cleaning' is the whole
    signal there. Sharing some words but not all is deliberately not enough, because
    that is also the shape of 'pay the water bill' next to 'pay the electricity bill'."""
    if not mine or not theirs:
        return 0.0
    remaining = list(theirs)
    hits = 0
    for word in mine:
        match = next((other for other in remaining if _same_word(word, other)), None)
        if match:
            remaining.remove(match)
            hits += 1
    dice = 2 * hits / (len(mine) + len(theirs))
    return max(dice, 0.75) if hits == min(len(mine), len(theirs)) else dice

def _similarity(mine: str, theirs: str) -> float:
    my_words, their_words = _significant_words(mine), _significant_words(theirs)
    if not my_words or not their_words:
        # Nothing but filler on one side, so fall back to comparing the raw wording
        return difflib.SequenceMatcher(None, _fold(mine), _fold(theirs)).ratio()
    return _word_overlap(my_words, their_words)

def _covered_by(my_words: list[str], text: str) -> bool:
    """True when everything the user just said is already written on that to-do, title
    or description. This is the case they actually described: the note was taken, they
    forgot, and they wrote the same thing again in fewer or different words."""
    their_words = _significant_words(text)
    return len(my_words) >= 2 and bool(their_words) and all(any(_same_word(word, other) for other in their_words) for word in my_words)

def _duplicate_threshold() -> float:
    """Deliberately permissive. Two to-dos sharing most of their words are ambiguous by
    nature — 'book dentist appointment' next to 'book doctor appointment' reads exactly
    like the same thing written twice — and the two mistakes are not equal: a duplicate
    that slips through is the problem this exists to solve, while a false catch costs
    one sentence and a tap, since the capture is held and offered back either way."""
    return float(os.getenv("TODO_DUPLICATE_THRESHOLD", "0.55"))

# Below the threshold but close enough to be worth naming, never enough to block a capture
_similar_margin = 0.04

def _recently_done(task: dict) -> bool:
    """A chore finished months ago and written down again is a new chore. One finished
    days ago is almost always the same one, forgotten."""
    done_at = _parse_timestamp(task.get("done_at") or "")
    if not done_at:
        return False
    return (datetime.now(timezone.utc) - done_at).days <= int(os.getenv("TODO_DUPLICATE_DONE_DAYS", "14"))

def _rank_duplicates(title: str, description: str = "", tasks: list[dict] = [], limit: int = 3, exclude_id: int = 0) -> list[dict]:
    """The to-dos that already say this, best match first. 'duplicate' means treat it as
    the same thing, 'similar' means worth mentioning and nothing more."""
    threshold = _duplicate_threshold()
    my_words = _significant_words(f"{title} {_plain_text(description)}")
    matches = []
    for task in tasks:
        if task.get("id") == exclude_id or (task.get("related_tasks") or {}).get("parenttask"):
            continue
        if task.get("done") and not _recently_done(task):
            continue
        their_title = task.get("title") or ""
        score = _similarity(title, their_title)
        if _covered_by(my_words, f"{their_title} {_user_description_text(task.get('description') or '')}"):
            score = max(score, threshold)
        if score < threshold - _similar_margin:
            continue
        matches.append({
            "score": round(score, 2),
            "match": "duplicate" if score >= threshold else "similar",
            "todo": _simplify_todo(task),
        })
    return sorted(matches, key=lambda match: match["score"], reverse=True)[:limit]

def find_duplicate_todos(title: str, description: str = "", limit: int = 3) -> list[dict] | dict:
    """To-dos that already cover what is about to be written down. Reads every page:
    the whole point is the to-do the user forgot, and that is exactly the one that has
    fallen off the first page."""
    if not vikunja_enabled():
        return _disabled_error()
    tasks = _all_tasks()
    if isinstance(tasks, dict):
        return tasks
    return _rank_duplicates(title, description, tasks, limit)

def duplicates_for_new_todos(todos: list[dict]) -> dict:
    """{to-do id: matches} for to-dos that just appeared, in a single scan, so the
    watcher can flag a duplicate written straight into Vikunja without paying for one
    sweep per task."""
    if not dedupe_enabled() or not todos:
        return {}
    tasks = _all_tasks()
    if isinstance(tasks, dict):
        return {}
    found = {}
    for todo in todos:
        duplicates = [match for match in _rank_duplicates(todo["title"], todo.get("description") or "", tasks, exclude_id=todo["id"]) if match["match"] == "duplicate"]
        if duplicates:
            found[todo["id"]] = duplicates
    return found

def _user_description_text(description: str) -> str:
    """What the user themselves put on the to-do: their own text and their steps, with
    Capy's research notes and merge log left out. Matching against those would let the
    bot's own writing make everything look like a duplicate of everything else."""
    head = (description or "").partition(_capy_notes_marker)[0].partition(_capy_merge_marker)[0]
    return _plain_text(head)

def _append_merge_note(description: str, details_html: str) -> str:
    """Adds one dated line to the to-do's merge log, creating the block if this is the
    first merge. It sits above the research notes and below whatever the user wrote, so
    add_todo_context and add_subtasks can each rewrite their own block without touching
    this one."""
    head, notes_marker, notes = (description or "").partition(_capy_notes_marker)
    model = _watermark_model()
    item = f"<li>{datetime.now(timezone.utc).strftime('%Y-%m-%d')} — {details_html}{f' <i>({model})</i>' if model else ''}</li>"
    before, marker, block = head.partition(_capy_merge_marker)
    if marker and "</ul>" in block:
        head = before + marker + block.replace("</ul>", f"{item}</ul>", 1)
    else:
        head = "\n".join(part for part in [head.rstrip(), f"{_capy_merge_marker}<ul>{item}</ul>"] if part.strip())
    return "\n".join(part for part in [head, notes_marker + notes if notes_marker else ""] if part)

def merge_into_todo(todo_id: int, details: str, due_date: str = "", priority: int = 0) -> dict:
    """Folds a second capture of the same thing into the to-do that already exists.
    Empty fields get filled, fields that already have a value are never overwritten —
    they come back as conflicts for the user to settle, because a due date silently
    replaced is a promise the list quietly stops keeping."""
    if not vikunja_enabled():
        return _disabled_error()
    current = get_todo(todo_id)
    if current.get("status") != "success":
        return current
    todo = current["todo"]
    conflicts = []
    changes = {"description": _append_merge_note(todo["description"], _normalize_model_html(details))}
    if due_date:
        if not todo["due_date"]:
            changes["due_date"] = due_date
            # Same reason as update_todo: the Gantt bar is drawn to the end date
            changes["end_date"] = due_date
        elif due_date != todo["due_date"]:
            conflicts.append({"field": "due_date", "existing": todo["due_date"], "new": due_date})
    if priority > 0:
        if not todo["priority"]:
            changes["priority"] = priority
        elif priority != todo["priority"]:
            conflicts.append({"field": "priority", "existing": todo["priority"], "new": priority})
    saved = _patch_task(todo_id, changes)
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    return {"status": "success", "todo": _simplify_todo(saved.json()), "merged": details, "conflicts": conflicts}

def merge_todos(source_id: int, target_id: int) -> dict:
    """Folds a duplicate to-do into the one it repeats, then deletes it. Only ever
    reached by the user tapping the offer, since deciding two to-dos are the same thing
    is theirs to make."""
    if not vikunja_enabled():
        return _disabled_error()
    if source_id == target_id:
        return {"status": "error", "tool": "vikunja", "message": "A to-do can't be merged into itself."}
    source = get_todo(source_id)
    if source.get("status") != "success":
        return source
    duplicate = source["todo"]
    text = _user_description_text(duplicate["description"])
    details = f"also written down as “{duplicate['title']}”" + (f": {text}" if text else "")
    merged = merge_into_todo(target_id, details, due_date=duplicate["due_date"], priority=duplicate["priority"])
    if merged.get("status") != "success":
        return merged
    removed = delete_todo(source_id)
    if removed.get("status") != "success":
        return removed
    return {
        "status": "success",
        "todo": merged["todo"],
        "merged_title": duplicate["title"],
        "removed_todo_id": source_id,
        "conflicts": merged["conflicts"],
    }

def queue_merge_offer(source_id: int, target_id: int, target_title: str) -> None:
    """The same pair is never offered twice: a failed announcement leaves the to-dos
    unseen and the watcher finds them again on the next pass, which would otherwise
    stack the same button up on one message."""
    state = _read_state()
    pending = (state.get("pending_merges") or [])[-10:]
    if any(merge["source"] == source_id and merge["target"] == target_id for merge in pending):
        return
    state["pending_merges"] = pending + [{"source": source_id, "target": target_id, "title": target_title}]
    _write_state(state)

def pop_pending_merges(limit: int = 2) -> list[dict]:
    state = _read_state()
    merges = state.get("pending_merges") or []
    if merges:
        state["pending_merges"] = merges[limit:]
        _write_state(state)
    return merges[:limit]

def _hold_blocked_capture(capture: dict) -> None:
    """Keeps the to-do a duplicate check refused, so 'add it anyway' is a tap rather
    than the user typing the whole thing out a second time. This is what makes catching
    duplicates eagerly safe: a wrong catch can never end with the thought lost."""
    state = _read_state()
    state["blocked_capture"] = dict(capture, at=time.time())
    _write_state(state)

def take_blocked_capture() -> dict:
    state = _read_state()
    capture = state.pop("blocked_capture", None)
    if capture:
        _write_state(state)
        capture.pop("at", None)
        capture.pop("offered", None)
    return capture or {}

def _blocked_capture_button() -> list[list[tuple[str, str]]]:
    """Offers the refused capture back exactly once, and only while it is still the
    thing being talked about. Without this the user has only the agent's word for it
    that the to-do already exists, and no way back if it doesn't."""
    state = _read_state()
    capture = state.get("blocked_capture") or {}
    if not capture or capture.get("offered") or time.time() - capture.get("at", 0) > 600:
        return []
    capture["offered"] = True
    state["blocked_capture"] = capture
    _write_state(state)
    return [[("➕ Add it anyway", "/addtodoanyway")]]

def add_todo(title: str, due_date: str = "", description: str = "", priority: int = 0, project_id: int = 0, allow_duplicate: bool = False) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    similar = []
    if dedupe_enabled() and not allow_duplicate:
        matches = find_duplicate_todos(title, description)
        # A dict here is Vikunja being unreachable; capture still wins over the check
        if isinstance(matches, list):
            duplicates = [match for match in matches if match["match"] == "duplicate"]
            if duplicates:
                _hold_blocked_capture({"title": title, "due_date": due_date, "description": description, "priority": priority, "project_id": project_id})
                return {
                    "status": "duplicate",
                    "tool": "vikunja",
                    "message": "This is already on the list, so nothing was added. Merge the new details into the existing to-do with merge_into_todo, or add it anyway with allow_duplicate=true if it is genuinely a different thing.",
                    "existing": duplicates,
                    "not_added": {"title": title, "due_date": due_date, "description": description, "priority": priority},
                }
            similar = matches
    payload = {"title": title, "description": description, "priority": priority}
    if due_date:
        payload["due_date"] = due_date
    response = _request("put", f"/projects/{project_id or _default_project_id()}/tasks", json=payload)
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    created = response.json()
    if created.get("id"):
        mark_todo_seen(created["id"])
    result = {"status": "success", "todo": _simplify_todo(created)}
    if similar:
        # Close, but not close enough to hold the capture back: capturing is the win,
        # and the user is the one who knows whether these are the same errand
        result["similar"] = similar
        result["similar_hint"] = "Added. These look related though, so mention in one short sentence that they are already on the list and let the user decide."
    return result

def _all_tasks() -> list[dict] | dict:
    """Every task, paged until exhausted. list_todos deliberately reads one page because
    a prompt does not want two hundred to-dos in it, but anything that has to be complete
    rather than representative needs this — a sweep that reports "all done" while a
    second page still holds work is worse than no sweep at all."""
    tasks = []
    page = 1
    while True:
        response = _request("get", "/tasks", params={"per_page": 50, "page": page, "sort_by": "id", "order_by": "desc"})
        if isinstance(response, dict):
            return response
        if not response.ok:
            return _request_error(response)
        batch = response.json() or []
        tasks += batch
        if len(batch) < 50:
            return tasks
        page += 1

def list_todos(include_done: bool = False) -> list[dict] | dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", "/tasks", params={"per_page": 50, "sort_by": "due_date", "order_by": "asc"})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    tasks = response.json() or []
    todos = [_simplify_todo(task) for task in tasks]
    if not include_done:
        todos = [todo for todo in todos if not todo["done"]]
    return todos

def update_todo(todo_id: int, title: str = "", description: str = "", due_date: str = "", start_date: str = "", priority: int = -1) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    payload = {}
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    if due_date:
        payload["due_date"] = due_date
        # The Gantt bar is drawn from start to end, so a due date that isn't also an end
        # date moves nothing on the chart the user actually plans in
        payload["end_date"] = due_date
    if start_date:
        payload["start_date"] = start_date
    if priority >= 0:
        payload["priority"] = priority
    if not payload:
        return {"status": "error", "tool": "vikunja", "message": "Nothing to update, provide at least one field."}
    response = _patch_task(todo_id, payload)
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo": _simplify_todo(response.json())}

def get_todo(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", f"/tasks/{todo_id}")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo": _simplify_todo(response.json())}

def append_todo_description(todo_id: int, notes_html: str) -> dict:
    """Writes research findings into the to-do under a marker heading. Everything the
    user wrote lives above the marker and is never touched, and a previous Capy block
    is replaced rather than stacked, so re-running research stays idempotent."""
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", f"/tasks/{todo_id}")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    notes_html = _normalize_model_html(notes_html)
    model = _watermark_model()
    if model and "<i>· " not in notes_html:
        # Inside the block, so the wholesale replace on the next research run
        # refreshes the signature along with the findings instead of stacking it.
        # Skipped when the caller signed already — the coder thread brings its own,
        # and this process's record may belong to someone else's prompt.
        notes_html += f"\n<p><i>· researched by {model}</i></p>"
    current = response.json().get("description") or ""
    user_text = current.split(_capy_notes_marker)[0].rstrip()
    updated = f"{user_text}\n{_capy_notes_marker}\n{notes_html}" if user_text else f"{_capy_notes_marker}\n{notes_html}"
    saved = _patch_task(todo_id, {"description": updated})
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    return {"status": "success", "todo": _simplify_todo(saved.json())}

def _checklist_item(text: str, done: bool) -> str:
    checked = "true" if done else "false"
    box = '<input type="checkbox" checked="checked">' if done else '<input type="checkbox">'
    return f'<li data-checked="{checked}" data-type="taskItem"><label>{box}<span></span></label><div><p>{text}</p></div></li>'

def _read_steps(description: str) -> list[dict]:
    """The steps as they currently stand, ticked or not. Vikunja stores the checklist
    as TipTap markup in the description and updates data-checked in place when a box is
    tapped, so the description is the only record of progress there is.

    The checklist element is its own anchor, with no heading marking it out: a heading
    would be one more thing to read on a task whose steps already say what they are.
    Anchoring on the markup rather than on a comment is what makes that safe, since the
    editor reserialises the whole description every time a box is tapped and would drop
    a comment on the way through."""
    block = re.search(_task_list_pattern, description.partition(_capy_notes_marker)[0], re.DOTALL)
    steps = []
    for item in re.findall(r"<li[^>]*data-type=\"taskItem\".*?</li>", block.group(0) if block else "", re.DOTALL):
        text = re.sub(r"<[^>]+>", "", item.partition("<div>")[2]).strip()
        # The estimate rides in the step text — steps aren't real tasks, so a label
        # can't carry it — and is parsed back out here so the model sees it as data
        estimate = re.search(r"🍅\s*(\d+)\s*$", text)
        steps.append({
            "text": text,
            "done": 'data-checked="true"' in item,
            "pomodoros": int(estimate.group(1)) if estimate else 0,
        })
    return steps

def _write_steps_block(description: str, titles: list[str]) -> str:
    """Puts the checklist in its own block between whatever the user wrote and the
    research notes, so the three can be rewritten independently and adding steps never
    eats an autopilot finding, or the other way round."""
    head, notes_marker, notes = description.partition(_capy_notes_marker)
    # A step that survives a rewrite keeps its tick, so refining the breakdown never
    # quietly undoes work the user already did. Matching ignores the 🍅 annotation so
    # adding or changing an estimate doesn't read as a brand new step and drop the tick.
    bare = lambda text: re.sub(r"\s*🍅\s*\d+\s*$", "", text)
    ticked = {bare(step["text"]): step["done"] for step in _read_steps(description)}
    # The old heading is stripped alongside the old list, so tasks split before the
    # steps went bare lose it the next time they are rewritten
    user_text = re.sub(_task_list_pattern, "", head, flags=re.DOTALL).replace(_capy_steps_marker, "").strip()
    checklist = "".join(_checklist_item(title, ticked.get(bare(title), False)) for title in titles)
    steps = f'<ul data-type="taskList">{checklist}</ul>'
    return "\n".join(part for part in [user_text, steps, notes_marker + notes if notes_marker else ""] if part)

def _is_capy_comment(comment: str) -> bool:
    return _capy_comment_marker in comment or _capy_comment_header in comment

# Escaped-tag shapes like &lt;p&gt; — the fingerprint of a model that HTML-escaped its
# own markup. Real text about HTML would be quoting a tag or two, not writing whole
# paragraphs of them, so requiring a closing shape keeps false positives out.
_escaped_html_pattern = r"&lt;/?(?:p|b|i|u|em|strong|ul|ol|li|a|code|pre|br|h[1-6])(?:\s[^&]*)?&gt;"

def _normalize_model_html(text: str) -> str:
    """Un-escapes markup a model delivered as entities. The local fallback model
    HTML-escapes its output where the primary one doesn't, and content is stored
    verbatim, so without this every buffered evening quietly writes descriptions
    that render as a wall of literal tags. Applied once at the write boundary,
    and only when escaped tags are actually present."""
    if re.search(_escaped_html_pattern, text or ""):
        return html.unescape(text)
    return text

def plain_comment_text(comment_html: str) -> str:
    """A comment as the user typed it, markup stripped. The watcher matches comment
    commands like /start and /stop against this, mechanically — the whole point of a
    comment command is that no model sits between typing it and it happening."""
    return _plain_text(comment_html)

def _watermark_model() -> str:
    # Imported lazily: llm_connector is loaded by everything and must not pull the
    # whole Vikunja module graph in at import time
    from connectors.llm_connector import authoring_model
    return authoring_model()

def list_todo_comments(todo_id: int) -> dict:
    """The conversation held on the to-do itself, oldest first, each flagged with
    whether Capy or the user wrote it."""
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", f"/tasks/{todo_id}/comments")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    comments = response.json() or []
    return {
        "status": "success",
        "todo_id": todo_id,
        "comments": [{
            "id": comment.get("id"),
            "comment": comment.get("comment") or "",
            "created": comment.get("created") or "",
            "by_capy": _is_capy_comment(comment.get("comment") or ""),
        } for comment in sorted(comments, key=lambda c: c.get("id") or 0)],
    }

def add_todo_comment(todo_id: int, comment_html: str) -> dict:
    """Replies in the to-do's own thread, signed, so the back and forth about a task
    stays attached to the task instead of scrolling away in chat."""
    if not vikunja_enabled():
        return _disabled_error()
    model = _watermark_model()
    signature = f"\n<p><i>· {model}</i></p>" if model and "<i>· " not in comment_html else ""
    body = f"{_capy_comment_header}\n{_normalize_model_html(comment_html)}{signature}\n{_capy_comment_marker}"
    response = _request("put", f"/tasks/{todo_id}/comments", json={"comment": body})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo_id": todo_id, "comment_id": response.json().get("id")}

def rename_todo(todo_id: int, new_title: str) -> dict:
    """Rewrites the title and remembers the original. Vikunja keeps no title history,
    and a rewrite the user doesn't recognise is worse than the clumsy title they wrote
    themselves, so undo has to be possible."""
    if not vikunja_enabled():
        return _disabled_error()
    current = get_todo(todo_id)
    if current.get("status") != "success":
        return current
    old_title = current["todo"]["title"]
    new_title = (new_title or "").strip()
    if not new_title or new_title == old_title:
        return {"status": "success", "changed": False, "title": old_title, "message": "The title was already fine, left it alone."}
    saved = _patch_task(todo_id, {"title": new_title})
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    state = _read_state()
    originals = state.get("original_titles") or {}
    # Only the first rename is the user's own wording, so never overwrite it
    originals.setdefault(str(todo_id), old_title)
    state["original_titles"] = dict(list(originals.items())[-50:])
    # Picked up by the caller after the message is composed, so the undo button can
    # ride along on the same message rather than arriving as a second notification
    state["pending_renames"] = (state.get("pending_renames") or [])[-10:] + [{"id": todo_id, "from": old_title, "to": new_title}]
    _write_state(state)
    return {"status": "success", "changed": True, "todo_id": todo_id, "from": old_title, "to": new_title}

def pop_pending_renames() -> list[dict]:
    state = _read_state()
    renames = state.get("pending_renames") or []
    if renames:
        state["pending_renames"] = []
        _write_state(state)
    return renames

def undo_title_buttons() -> list[list[tuple[str, str]]] | None:
    """Undo offers for whatever was renamed while composing the message being sent.
    Called on every path that could have triggered a rename, so the offer always sits
    on the message that announced the change instead of drifting onto a later one."""
    return [
        [(f"↩️ Undo: {rename['from'][:22]}", f"/undotitle {rename['id']}")]
        for rename in pop_pending_renames()[-3:]
    ] or None

def restore_todo_title(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    state = _read_state()
    originals = state.get("original_titles") or {}
    old_title = originals.get(str(todo_id))
    if not old_title:
        return {"status": "error", "tool": "vikunja", "message": f"I don't have the original title for to-do {todo_id} anymore."}
    saved = _patch_task(todo_id, {"title": old_title})
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    originals.pop(str(todo_id), None)
    state["original_titles"] = originals
    _write_state(state)
    return {"status": "success", "todo_id": todo_id, "title": old_title}

def _rename_label(label: dict, title: str, color: str) -> bool:
    """Renames a label in place, keeping its id — and therefore every task it is
    already attached to. Creating a fresh label with the new name instead would leave
    the whole backlog wearing the old one."""
    updated = _request("post", f"/labels/{label['id']}", json={**label, "title": title, "hex_color": color})
    return not isinstance(updated, dict) and updated.ok

def ensure_triage_labels(refresh: bool = False) -> dict:
    """Creates the triage labels once and caches slug -> id. The ids are what matters:
    Vikunja's task filters match labels by id and reject titles outright, so the board's
    bucket filters can only be built after this has run. Returns {} if Vikunja said no.
    Deleting a label in Vikunja leaves the cache pointing at an id that no longer exists,
    so /triagesetup refreshes rather than trusting it — otherwise the obvious way to fix
    a broken board would be the one thing that couldn't.

    A label found under its old title is renamed in place rather than recreated:
    matching is by title, so without the rename a retitled vocabulary would quietly
    spawn twins and strand every existing task's assignments on the old set."""
    cached = _read_state().get("triage_label_ids") or {}
    if not refresh and set(cached) >= set(_triage_labels):
        return cached
    response = _request("get", "/labels", params={"per_page": 100})
    if isinstance(response, dict) or not response.ok:
        return {}
    labels = response.json() or []
    existing = {label["title"]: label for label in labels}
    ids = {}
    for slug, (title, color) in _triage_labels.items():
        if title in existing:
            ids[slug] = existing[title]["id"]
            continue
        old = existing.get(_old_label_titles.get(slug, ""))
        if old and _rename_label(old, title, color):
            ids[slug] = old["id"]
            continue
        created = _request("put", "/labels", json={"title": title, "hex_color": color})
        if isinstance(created, dict) or not created.ok:
            return {}
        ids[slug] = created.json()["id"]
    state = _read_state()
    state["triage_label_ids"] = ids
    _write_state(state)
    return ids

def _is_pomodoro_title(title: str) -> bool:
    return bool(re.match(_pomodoro_label_pattern, title or ""))

def _ensure_pomodoro_label(count: int) -> int | None:
    """Find-or-create the 🍅 {count} label, id cached per count. The titles are exact
    counts on purpose — the user chose uncapped precision over buckets — and they never
    embed minutes, so changing POMODORO_MINUTES later re-scales every estimate at once
    instead of orphaning a generation of labels."""
    state = _read_state()
    cached = state.get("pomodoro_label_ids") or {}
    if str(count) in cached:
        return cached[str(count)]
    title = f"🍅 {count}"
    response = _request("get", "/labels", params={"per_page": 100, "s": "🍅"})
    if isinstance(response, dict) or not response.ok:
        return None
    found = next((label for label in response.json() or [] if label["title"] == title), None)
    if not found:
        created = _request("put", "/labels", json={"title": title, "hex_color": _pomodoro_label_color})
        if isinstance(created, dict) or not created.ok:
            return None
        found = created.json()
    state = _read_state()
    cached = state.get("pomodoro_label_ids") or {}
    cached[str(count)] = found["id"]
    state["pomodoro_label_ids"] = cached
    _write_state(state)
    return found["id"]

def set_todo_labels(todo_id: int, slugs: list[str], pomodoros: int = 0) -> dict:
    """Sets the task's triage labels in one call. Deliberately not _patch_task: the bulk
    endpoint touches only labels, so unlike a whole-task write it cannot blank the
    description or the due date on its way past. It does replace the whole label set
    though, so anything the user labelled the task with themselves is read first and
    carried over, otherwise triage would quietly strip it. Pomodoro labels are ours
    too, never carried: a fresh estimate must replace the old one, not stack next to
    it, or a re-triaged task would wear two counts at once."""
    ids = ensure_triage_labels()
    if not ids:
        return {"status": "error", "tool": "vikunja", "message": "Could not read or create the triage labels in Vikunja."}
    current = _request("get", f"/tasks/{todo_id}")
    if isinstance(current, dict):
        return current
    if not current.ok:
        return _request_error(current)
    theirs = [
        {"id": label["id"]} for label in current.json().get("labels") or []
        if label["id"] not in set(ids.values()) and not _is_pomodoro_title(label.get("title") or "")
    ]
    ours = [{"id": ids[slug]} for slug in slugs if slug in ids]
    titles = [_triage_labels[slug][0] for slug in slugs if slug in ids]
    if pomodoros > 0:
        pomodoro_id = _ensure_pomodoro_label(pomodoros)
        if pomodoro_id:
            ours.append({"id": pomodoro_id})
            titles.append(f"🍅 {pomodoros}")
    response = _request("post", f"/tasks/{todo_id}/labels/bulk", json={"labels": theirs + ours})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "todo_id": todo_id, "labels": titles}

def _quadrant_for(urgent: bool, important: bool) -> str:
    return f"{'urgent' if urgent else 'not-urgent'}-{'important' if important else 'not-important'}"

def triage_todo(todo_id: int, urgent: bool, important: bool, action: str, extra_labels: list[str] = [], pomodoros: int = 0, reason: str = "") -> dict:
    """Files a to-do by two separate screenings. Urgent × important says what the task
    is and decides its box — the quadrant tag, which is all a box is now that every
    task lives in the Inbox. The action, do/schedule/delegate/drop, says what to
    do about it and is its own tag: the two usually agree, but an urgent and important
    task the user can't do themselves is still a delegate, and forcing the pairing
    would erase exactly the cases worth noticing. The pomodoro estimate rides in the
    same label write; a two-minute task never gets one, the tag would outweigh the task."""
    if not triage_enabled():
        return {"status": "error", "tool": "vikunja", "message": "To-do triage is disabled. To enable it, set ENABLE_TODO_TRIAGE=true in your .env file."}
    if action not in _action_slugs:
        return {"status": "error", "tool": "vikunja", "message": f"Unknown action '{action}', pick one of {_action_slugs}."}
    quadrant = _quadrant_for(urgent, important)
    extras = [slug for slug in extra_labels if slug in _triage_labels and slug not in _quadrant_slugs and slug not in _action_slugs]
    estimate = 0 if "two-minute" in extras or not pomodoro_enabled() else max(0, pomodoros)
    saved = set_todo_labels(todo_id, [quadrant, action] + extras, pomodoros=estimate)
    if saved.get("status") != "success":
        return saved
    # A drop is only ever offered, never carried out, so it has to leave something the
    # user can act on. The reasoning goes in a comment rather than the description: the
    # Capy block there belongs to research notes, which would overwrite it the moment
    # autopilot finishes a job on the same task.
    if action == "drop" or "not-needed" in extras:
        if reason:
            add_todo_comment(todo_id, f"<p>{reason}</p>")
        current = get_todo(todo_id)
        if current.get("status") == "success":
            _queue_drop_offer(todo_id, current["todo"]["title"])
    return {
        "status": "success",
        "todo_id": todo_id,
        "quadrant": _triage_labels[quadrant][0],
        "action": _triage_labels[action][0],
        "labels": saved["labels"],
        "pomodoros": estimate,
    }

def _current_triage_slugs(todo: dict) -> list[str]:
    titles = set(todo["labels"])
    return [slug for slug, (title, _) in _triage_labels.items() if title in titles]

def _current_pomodoros(todo: dict) -> int:
    """The estimate a task already wears, read back from its 🍅 label so a manual
    override can rewrite the label set without losing it."""
    for title in todo["labels"]:
        if _is_pomodoro_title(title):
            return int(title.split()[-1])
    return 0

def set_todo_quadrant(todo_id: int, quadrant: str) -> dict:
    """Moves a to-do to another box by hand, keeping the action, the extras and the
    estimate exactly as triage left them. This is how the user overrules a verdict
    without having to re-run triage and hope it lands differently."""
    quadrant = _legacy_quadrant_slugs.get(quadrant, quadrant)
    if quadrant not in _quadrant_slugs:
        return {"status": "error", "tool": "vikunja", "message": f"Unknown quadrant '{quadrant}', pick one of {_quadrant_slugs}."}
    current = get_todo(todo_id)
    if current.get("status") != "success":
        return current
    kept = [slug for slug in _current_triage_slugs(current["todo"]) if slug not in _quadrant_slugs]
    saved = set_todo_labels(todo_id, [quadrant] + kept, pomodoros=_current_pomodoros(current["todo"]))
    if saved.get("status") != "success":
        return saved
    return {"status": "success", "todo_id": todo_id, "title": current["todo"]["title"], "quadrant": _triage_labels[quadrant][0]}

def set_todo_action(todo_id: int, action: str) -> dict:
    """Swaps only the action tag — what to do about the task — leaving its box, extras
    and estimate alone. The counterpart to set_todo_quadrant for the second screening."""
    if action not in _action_slugs:
        return {"status": "error", "tool": "vikunja", "message": f"Unknown action '{action}', pick one of {_action_slugs}."}
    current = get_todo(todo_id)
    if current.get("status") != "success":
        return current
    kept = [slug for slug in _current_triage_slugs(current["todo"]) if slug not in _action_slugs]
    saved = set_todo_labels(todo_id, kept + [action], pomodoros=_current_pomodoros(current["todo"]))
    if saved.get("status") != "success":
        return saved
    return {"status": "success", "todo_id": todo_id, "title": current["todo"]["title"], "action": _triage_labels[action][0]}

def _queue_drop_offer(todo_id: int, title: str) -> None:
    state = _read_state()
    state["pending_drops"] = (state.get("pending_drops") or [])[-10:] + [{"id": todo_id, "title": title}]
    _write_state(state)

def pop_pending_drops(limit: int = 3) -> list[dict]:
    """Takes at most limit offers off the queue. A sweep over a backlog can propose more
    drops than fit on one message, and the ones that don't fit wait for the next message
    rather than being thrown away with the user none the wiser."""
    state = _read_state()
    drops = state.get("pending_drops") or []
    if drops:
        state["pending_drops"] = drops[limit:]
        _write_state(state)
    return drops[:limit]

def todo_action_buttons() -> list[list[tuple[str, str]]] | None:
    """Every offer raised while composing the message being sent: undo a rename, drop
    something triage doubts, fold a duplicate into the to-do it repeats, put a coding
    agent on something. They ride on the message that announced them, so acting on one
    is a tap rather than a task the user has to remember to come back to."""
    drops = [
        [(f"🗑 Drop: {drop['title'][:22]}", f"/deletetodo {drop['id']}")]
        for drop in pop_pending_drops()
    ]
    merges = [
        [(f"🔗 Merge into: {merge['title'][:18]}", f"/mergetodo {merge['source']} {merge['target']}")]
        for merge in pop_pending_merges()
    ]
    # Imported here rather than at the top: the coder needs this module for the
    # report write-back, and Python cycles break at whichever import runs first
    from connectors.coder_connector import pop_pending_coder_offers
    coding = [
        [(f"🧑‍💻 Code it: {offer['goal'][:20]}", f"/aicode {offer['todo_id']}")]
        for offer in pop_pending_coder_offers()
    ]
    return (undo_title_buttons() or []) + drops + merges + coding + _blocked_capture_button() or None

def configure_triage() -> dict:
    """Creates the tags, then retires the old Eisenhower view. Everything lives in the
    Inbox and the quadrant labels are the boxes, so any board drawing the four columns
    is built from label filters in the Inbox project itself."""
    if not triage_enabled():
        return {"status": "error", "tool": "vikunja", "message": "To-do triage is disabled. To enable it, set ENABLE_TODO_TRIAGE=true in your .env file."}
    labels = ensure_triage_labels(refresh=True)
    if not labels:
        return {"status": "error", "tool": "vikunja", "message": "Could not read or create the triage labels in Vikunja."}
    # The quadrant projects are gone; a cache entry pointing at them would only confuse
    state = _read_state()
    if state.pop("triage_project_ids", None) is not None:
        _write_state(state)
    views = _request("get", f"/projects/{_default_project_id()}/views")
    retired = False
    if not isinstance(views, dict) and views.ok:
        for view in views.json() or []:
            if view.get("title") == _triage_board_title:
                _request("delete", f"/projects/{_default_project_id()}/views/{view['id']}")
                retired = True
    return {"status": "success", "labels": len(labels), "retired_board": retired}

def untriaged_todos() -> list[dict] | dict:
    """Open to-dos with no quadrant label yet, which is now the whole definition of
    untriaged — everything lives in the Inbox, so the project says nothing. Paged
    rather than capped: a sweep that quietly stops at fifty would report the list
    clear while a second page still held work."""
    tasks = _all_tasks()
    if isinstance(tasks, dict):
        return tasks
    return [_simplify_todo(task) for task in tasks if not task.get("done") and not _box_title(task) and not (task.get("related_tasks") or {}).get("parenttask")]

def add_subtasks(parent_todo_id: int, titles: list[str], pomodoros: list[int] = []) -> dict:
    """Writes the steps as a checklist inside the to-do's own description. Breaking a
    project into real subtasks doubles or triples the length of the list, and a list
    that long is the thing that makes someone stop opening it at all — the steps belong
    inside the task they belong to, not beside it. Each step carries its own pomodoro
    estimate in its text — steps aren't real tasks, so a label can't hold it — and the
    parent's 🍅 label becomes the sum, so the task's own tag says what the whole thing
    costs while the checklist says where the time goes."""
    if not subtasks_enabled():
        return {"status": "error", "tool": "vikunja", "message": "Subtask splitting is disabled. To enable it, set ENABLE_VIKUNJA_SUBTASKS=true in your .env file."}
    response = _request("get", f"/tasks/{parent_todo_id}")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    estimates = list(pomodoros)[:len(titles)] if pomodoro_enabled() else []
    if estimates:
        titles = [
            f"{title} 🍅{estimate}" if estimate > 0 else title
            for title, estimate in zip(titles, estimates + [0] * (len(titles) - len(estimates)))
        ]
    current = response.json().get("description") or ""
    saved = _patch_task(parent_todo_id, {"description": _write_steps_block(current, titles)})
    if isinstance(saved, dict):
        return saved
    if not saved.ok:
        return _request_error(saved)
    total = sum(estimate for estimate in estimates if estimate > 0)
    if total > 0:
        task = saved.json()
        current_slugs = [
            slug for slug, (title, _) in _triage_labels.items()
            if title in [label.get("title") for label in task.get("labels") or []]
        ]
        set_todo_labels(parent_todo_id, current_slugs, pomodoros=total)
    return {"status": "success", "parent_todo_id": parent_todo_id, "steps": _read_steps(saved.json().get("description") or ""), "total_pomodoros": total}

def complete_todo(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _patch_task(todo_id, {"done": True})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    mark_todos_done([todo_id])
    return {"status": "success", "todo": _simplify_todo(response.json())}

def delete_todo(todo_id: int) -> dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("delete", f"/tasks/{todo_id}")
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    return {"status": "success", "message": f"To-do {todo_id} deleted."}

def _read_state() -> dict:
    try:
        with open(_seen_path) as f:
            return json.load(f)
    except Exception:
        return {}

def _write_state(state: dict) -> None:
    with open(_seen_path, "w") as f:
        json.dump(state, f)

def _read_seen_ids() -> list[int] | None:
    return _read_state().get("seen_ids")

def _write_seen_ids(ids: list[int]) -> None:
    state = _read_state()
    state["seen_ids"] = sorted(ids)
    _write_state(state)

def mark_todos_seen(todo_ids: list[int]) -> None:
    seen = set(_read_seen_ids() or [])
    if not set(todo_ids) <= seen:
        _write_seen_ids(list(seen | set(todo_ids)))

def mark_todo_seen(todo_id: int) -> None:
    mark_todos_seen([todo_id])

def _sync_subtask_progress(tasks: list[dict]) -> None:
    """Keeps each task's percent_done bar in sync with how many of its steps are done,
    so ticking boxes anywhere fills the progress bar and the Gantt view stays honest.
    Steps written into the description count the same as older real subtasks, which
    still exist on tasks split before the checklist became the way to do it."""
    for task in tasks:
        steps = _read_steps(task.get("description") or "")
        subtasks = (task.get("related_tasks") or {}).get("subtask") or []
        done = [step["done"] for step in steps] or [s.get("done", False) for s in subtasks]
        if not done or task.get("done"):
            continue
        progress = round(sum(1 for is_done in done if is_done) / len(done), 2)
        if abs(task.get("percent_done", 0) - progress) >= 0.01:
            _patch_task(task["id"], {"percent_done": progress})

def _has_date(task: dict, field: str) -> bool:
    return bool(task.get(field)) and task.get(field) != _no_due_date

def _sync_gantt_dates(tasks: list[dict]) -> None:
    """Gives every to-do the two dates a Gantt bar is drawn between. The start comes from
    the task's own created stamp rather than from now, so a to-do captured while the bot
    was down still shows its real age. The end is the moment it was finished, which is
    what turns the bar into how long the thing actually took — done_at is system
    controlled and cannot be written, so the value has to be copied across. An open task
    with a due date gets that as its end instead, so planned work draws a bar too."""
    for task in tasks:
        changes = {}
        if not _has_date(task, "start_date") and task.get("created"):
            changes["start_date"] = task["created"]
        if not _has_date(task, "end_date"):
            if task.get("done") and _has_date(task, "done_at"):
                changes["end_date"] = task["done_at"]
            elif not task.get("done") and _has_date(task, "due_date"):
                changes["end_date"] = task["due_date"]
        if changes:
            _patch_task(task["id"], changes)

def check_todo_updates() -> dict:
    """Returns {"status": "success", "new": [...], "completed": [...]} with to-dos
    created outside the bot and to-dos completed since the last check, without
    marking them handled — the caller must mark_todos_seen / mark_todos_done after
    successfully notifying the user, so a failed notification is retried on the
    next check. First run seeds the state without reporting anything."""
    if not vikunja_enabled():
        return {"status": "success", "new": [], "completed": []}
    # Every page, not the newest fifty: the server caps per_page at 50, and a task
    # that fell off the first page used to become invisible to the watcher forever
    tasks = _all_tasks()
    if isinstance(tasks, dict):
        return tasks
    _sync_subtask_progress(tasks)
    _sync_gantt_dates(tasks)
    current_ids = {task["id"] for task in tasks}
    current_done_ids = {task["id"] for task in tasks if task.get("done", False)}
    state = _read_state()
    seen = state.get("seen_ids")
    done = state.get("done_ids")
    new_tasks = []
    completed_tasks = []
    if seen is None:
        state["seen_ids"] = sorted(current_ids)
    else:
        new_tasks = [task for task in tasks if task["id"] not in seen and not task.get("done", False)]
        new_ids = {task["id"] for task in new_tasks}
        state["seen_ids"] = sorted((set(seen) | current_ids) - new_ids)
    if done is None:
        state["done_ids"] = sorted(current_done_ids)
    else:
        completed_tasks = [task for task in tasks if task["id"] in current_done_ids and task["id"] not in done]
        state["done_ids"] = sorted(set(done) & current_done_ids)
    _write_state(state)
    return {
        "status": "success",
        "new": [_simplify_todo(task) for task in new_tasks],
        "completed": [_simplify_todo(task) for task in completed_tasks],
    }

def mark_todos_done(todo_ids: list[int]) -> None:
    state = _read_state()
    done = set(state.get("done_ids") or [])
    if not set(todo_ids) <= done:
        state["done_ids"] = sorted(done | set(todo_ids))
        _write_state(state)

def check_todo_comments() -> dict:
    """Returns {"status": "success", "threads": [...]} for comments the user has
    written on their to-dos since the last check, so a task can be steered from
    inside Vikunja instead of only through chat.

    Posting a comment bumps the task's own updated timestamp, which is what makes
    this affordable: only tasks that actually changed get their thread fetched, so
    a quiet list costs exactly one request. State is kept per task, so a thread that
    fails to deliver is retried on its own without holding up or swallowing the rest.
    The caller must mark_comments_seen once the user has actually been told."""
    if not comments_enabled():
        return {"status": "success", "threads": []}
    # Every page, not the newest fifty: a /start on an old task used to be invisible
    tasks = _all_tasks()
    if isinstance(tasks, dict):
        return tasks
    state = _read_state()
    # Absent on the very first run only: existing threads are history, not instructions
    seeding = "comment_state" not in state
    comment_state = state.get("comment_state") or {}
    # Carried over rather than rebuilt, so a watermark is never dropped back to zero —
    # which would replay a whole old thread as fresh instructions. Same reasoning as
    # keeping done tasks' watermarks.
    fresh_state = dict(comment_state)
    # The cheap skip below trusts the task's updated stamp, which has one second
    # resolution and can miss a comment landing in the same second as a scan. Reading
    # every open task's thread every pass would cover that but costs a request per
    # task per pass, so instead a full sweep runs every Nth pass: the race is caught
    # within about ten minutes instead of never, and the ordinary pass stays cheap.
    sweep_every = int(os.getenv("VIKUNJA_COMMENT_SWEEP_PASSES", "20"))
    pass_count = int(state.get("comment_pass_count") or 0) + 1
    sweeping = sweep_every > 0 and pass_count >= sweep_every
    state["comment_pass_count"] = 0 if sweeping else pass_count
    threads = []
    for task in tasks:
        key = str(task["id"])
        known = comment_state.get(key) or {}
        # Done tasks keep their watermark rather than being pruned, so reopening one
        # doesn't replay its whole thread as if it were new
        if task.get("done", False):
            if known:
                fresh_state[key] = known
            continue
        # The changed check is only a way to avoid pointless requests, never the thing
        # that decides what counts as new: the periodic sweep reads every open thread
        # regardless, so nothing the stamp misses stays missed.
        if not sweeping and known.get("updated") == (task.get("updated") or ""):
            fresh_state[key] = known
            continue
        found = list_todo_comments(task["id"])
        if found.get("status") != "success":
            # Leave this one exactly as it was so the next pass tries again
            if known:
                fresh_state[key] = known
            continue
        comments = found["comments"]
        watermark = known.get("watermark", 0)
        scanned = {
            "updated": task.get("updated") or "",
            "watermark": max([c["id"] for c in comments] + [watermark]),
            "has_comments": bool(comments),
        }
        new_comments = [c for c in comments if c["id"] > watermark and not c["by_capy"]]
        if seeding or not new_comments:
            fresh_state[key] = scanned
            continue
        # Held back until delivered, so a failed message doesn't lose the comment
        fresh_state[key] = known
        threads.append({
            "todo": _simplify_todo(task),
            "thread": comments,
            "new_comments": [c["comment"] for c in new_comments],
            "seen": scanned,
        })
    state["comment_state"] = fresh_state
    _write_state(state)
    return {"status": "success", "threads": threads}

def mark_comments_seen(todo_id: int, seen: dict) -> None:
    state = _read_state()
    comment_state = state.get("comment_state") or {}
    comment_state[str(todo_id)] = seen
    state["comment_state"] = comment_state
    _write_state(state)

def daily_focus_todos() -> list[dict] | dict | bool:
    """Once a day at VIKUNJA_DAILY_FOCUS_HOUR (UTC, -1 disables), returns the
    pending to-dos for the morning focus message. Returns False when it's not
    time yet or already sent today — the caller must mark_focus_sent after
    successfully sending, so a failure is retried on the next heartbeat."""
    focus_hour = int(os.getenv("VIKUNJA_DAILY_FOCUS_HOUR", "-1"))
    if not vikunja_enabled() or focus_hour < 0:
        return False
    now = datetime.now(timezone.utc)
    if now.hour < focus_hour:
        return False
    if _read_state().get("last_focus_date") == now.date().isoformat():
        return False
    return list_todos()

def mark_focus_sent() -> None:
    state = _read_state()
    state["last_focus_date"] = datetime.now(timezone.utc).date().isoformat()
    _write_state(state)

def daily_dateless_todos() -> list[dict] | dict | bool:
    """Once a day at VIKUNJA_DATE_NUDGE_HOUR (UTC, -1 disables), returns the pending
    top-level to-dos missing a due date, so the agent can ask the user for dates.
    Returns False when it's not time yet or already sent today — the caller must
    mark_date_nudge_sent after successfully sending."""
    nudge_hour = int(os.getenv("VIKUNJA_DATE_NUDGE_HOUR", "-1"))
    if not vikunja_enabled() or nudge_hour < 0:
        return False
    now = datetime.now(timezone.utc)
    if now.hour < nudge_hour:
        return False
    if _read_state().get("last_date_nudge_date") == now.date().isoformat():
        return False
    todos = list_todos()
    if isinstance(todos, dict):
        return todos
    return [todo for todo in todos if not todo["due_date"] and not todo["is_subtask"]]

def mark_date_nudge_sent() -> None:
    state = _read_state()
    state["last_date_nudge_date"] = datetime.now(timezone.utc).date().isoformat()
    _write_state(state)

def _parse_timestamp(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None

def _weekly_slot(state_key: str) -> str | bool:
    """Shared gate for the once-a-week moments. Returns the week key to store when it
    is time, or False otherwise, mirroring how the daily ones work."""
    review_day = int(os.getenv("WEEKLY_REVIEW_DAY", "-1"))
    if not vikunja_enabled() or review_day < 0:
        return False
    now = datetime.now(timezone.utc)
    if now.weekday() != review_day or now.hour < int(os.getenv("WEEKLY_REVIEW_HOUR", "9")):
        return False
    week = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    if _read_state().get(state_key) == week:
        return False
    return week

def weekly_stale_todos() -> list[dict] | dict | bool:
    """Up to 3 to-dos nobody has touched in STALE_TODO_DAYS. Capped deliberately:
    the point is to make the list trustworthy again, and a wall of forgotten tasks
    does the opposite. The caller must mark_stale_sweep_sent after sending."""
    if not _weekly_slot("last_stale_sweep_week"):
        return False
    todos = list_todos()
    if isinstance(todos, dict):
        return todos
    cutoff = int(os.getenv("STALE_TODO_DAYS", "21"))
    now = datetime.now(timezone.utc)
    stale = []
    for todo in todos:
        updated = _parse_timestamp(todo["updated"])
        if todo["is_subtask"] or not updated:
            continue
        if (now - updated).days >= cutoff:
            stale.append(todo)
    return stale[:3]

def mark_stale_sweep_sent() -> None:
    now = datetime.now(timezone.utc)
    state = _read_state()
    state["last_stale_sweep_week"] = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    _write_state(state)

def weekly_wins() -> list[dict] | dict | bool:
    """What actually got finished in the last 7 days. ADHD memory badly undercounts
    wins, so this exists to be evidence. Caller must mark_digest_sent after sending."""
    if not _weekly_slot("last_digest_week"):
        return False
    todos = list_todos(include_done=True)
    if isinstance(todos, dict):
        return todos
    now = datetime.now(timezone.utc)
    wins = []
    for todo in todos:
        if not todo["done"]:
            continue
        done_at = _parse_timestamp(todo["done_at"])
        if done_at and (now - done_at).days < 7:
            wins.append(todo)
    return wins

def mark_digest_sent() -> None:
    now = datetime.now(timezone.utc)
    state = _read_state()
    state["last_digest_week"] = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    _write_state(state)

def weekly_quadrant_balance() -> dict | bool:
    """How the open list is split across the four boxes, against last week's split.
    Covey's argument in First Things First is that a healthy system grows quadrant II
    and shrinks quadrant III, so the movement is the point, not the raw counts. Caller
    must mark_balance_sent after sending."""
    if not triage_enabled() or not _weekly_slot("last_balance_week"):
        return False
    tasks = _all_tasks()
    if isinstance(tasks, dict):
        return False
    # Counted by quadrant label — the labels are the boxes now — and paging means
    # the split is the real one instead of the first fifty rows of it
    title_to_slug = {_triage_labels[slug][0]: slug for slug in _quadrant_slugs}
    counts = {slug: 0 for slug in _quadrant_slugs}
    untriaged = 0
    for task in tasks:
        if task.get("done"):
            continue
        slug = title_to_slug.get(_box_title(task))
        if slug:
            counts[slug] += 1
        else:
            untriaged += 1
    return {"counts": counts, "untriaged": untriaged, "last_week": _read_state().get("last_balance_counts") or {}}

def mark_balance_sent(counts: dict) -> None:
    now = datetime.now(timezone.utc)
    state = _read_state()
    state["last_balance_week"] = f"{now.isocalendar().year}-W{now.isocalendar().week}"
    state["last_balance_counts"] = counts
    _write_state(state)

def list_todo_projects() -> list[dict] | dict:
    if not vikunja_enabled():
        return _disabled_error()
    response = _request("get", "/projects", params={"per_page": 50})
    if isinstance(response, dict):
        return response
    if not response.ok:
        return _request_error(response)
    projects = response.json() or []
    return [{"id": p.get("id"), "title": p.get("title")} for p in projects]
