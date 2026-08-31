"""One-time migration to the labels-only layout. Run on the opencapy host with the
service STOPPED (old code would recreate the quadrant projects on its next pass):

    cd ~/opencapy && .venv/bin/python scripts/migrate_labels_only.py [--dry-run]
    .venv/bin/python scripts/migrate_labels_only.py --set-code 12 34 56

What it does, idempotently:
  1. ensure_triage_labels(refresh=True) — renames the old ai-can-do label in place
     (keeping every assignment) and creates the new vocabulary.
  2. Moves every task out of the quadrant projects into the Inbox, stamping the
     matching quadrant label on first so no information is lost.
  3. Deletes the quadrant projects and the empty "Agents" project — refusing any
     project that still reports tasks.
  4. Prints the tasks wearing "ai can research" as the reclassification worklist;
     --set-code swaps the listed task ids over to "ai can code".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from connectors.vikunja_connector import (
    _all_tasks,
    _default_project_id,
    _patch_task,
    _read_state,
    _request,
    _triage_labels,
    _write_state,
    ensure_triage_labels,
)

# The quadrant projects being retired, by the titles the old code gave them,
# mapped to the label slug that says the same thing
_project_titles_to_slugs = {
    "☸️ Urgent and important": "urgent-important",
    "🌱 Not urgent and important": "not-urgent-important",
    "🔥 Urgent and not important": "urgent-not-important",
    "🍂 Not urgent and not important": "not-urgent-not-important",
}
_extra_projects_to_delete = ["Agents"]

def fail(message: str) -> None:
    print(f"❌ {message}")
    sys.exit(1)

def task_label_ids(task: dict) -> set:
    return {label["id"] for label in task.get("labels") or []}

def add_label(task_id: int, label_id: int) -> None:
    response = _request("put", f"/tasks/{task_id}/labels", json={"label_id": label_id})
    if isinstance(response, dict) or not response.ok:
        fail(f"Couldn't add label {label_id} to task {task_id}: {getattr(response, 'text', response)}")

def remove_label(task_id: int, label_id: int) -> None:
    response = _request("delete", f"/tasks/{task_id}/labels/{label_id}")
    if isinstance(response, dict) or not (response.ok or response.status_code == 404):
        fail(f"Couldn't remove label {label_id} from task {task_id}: {getattr(response, 'text', response)}")

def main() -> None:
    dry_run = "--dry-run" in sys.argv
    set_code_ids = []
    if "--set-code" in sys.argv:
        set_code_ids = [int(arg) for arg in sys.argv[sys.argv.index("--set-code") + 1:] if arg.isdigit()]
        if not set_code_ids:
            fail("--set-code needs task ids, e.g. --set-code 12 34")

    print("1) Labels: renaming/creating the triage vocabulary...")
    label_ids = ensure_triage_labels(refresh=True)
    if not label_ids:
        fail("ensure_triage_labels failed — is Vikunja reachable and the token valid?")
    research_id = label_ids["ai-can-research"]
    code_id = label_ids["ai-can-code"]
    print(f"   ai-can-research → label {research_id}, ai-can-code → label {code_id}")

    if set_code_ids:
        for task_id in set_code_ids:
            if not dry_run:
                remove_label(task_id, research_id)
                add_label(task_id, code_id)
            print(f"   task {task_id}: {'would swap' if dry_run else 'swapped'} → {_triage_labels['ai-can-code'][0]}")
        return

    print("2) Projects: reading the current layout...")
    response = _request("get", "/projects", params={"per_page": 100})
    if isinstance(response, dict) or not response.ok:
        fail("Couldn't list projects.")
    projects = response.json() or []
    inbox = _default_project_id()
    retire = [p for p in projects if p["title"] in _project_titles_to_slugs or p["title"] in _extra_projects_to_delete]
    if not retire:
        print("   Nothing to retire — already migrated.")
    for project in retire:
        print(f"   retiring: {project['id']} {project['title']}")

    tasks = _all_tasks()
    if isinstance(tasks, dict):
        fail(f"Couldn't list tasks: {tasks.get('message')}")
    retire_ids = {p["id"]: p["title"] for p in retire}
    moved = 0
    for task in tasks:
        title = retire_ids.get(task.get("project_id"))
        if not title:
            continue
        slug = _project_titles_to_slugs.get(title)
        quadrant_label = label_ids.get(slug) if slug else None
        needs_label = quadrant_label and quadrant_label not in task_label_ids(task)
        print(f"   task {task['id']} '{task['title'][:40]}' ← {title}"
              + (f" (+{_triage_labels[slug][0]})" if needs_label else ""))
        if dry_run:
            continue
        if needs_label:
            add_label(task["id"], quadrant_label)
        saved = _patch_task(task["id"], {"project_id": inbox})
        if isinstance(saved, dict) or not saved.ok:
            fail(f"Couldn't move task {task['id']} to the Inbox: {getattr(saved, 'text', saved)}")
        moved += 1
    print(f"   moved {moved} task(s) to the Inbox (project {inbox}).")

    print("3) Deleting the retired projects...")
    if dry_run:
        print("   (dry run, skipping)")
    else:
        remaining = _all_tasks()
        if isinstance(remaining, dict):
            fail("Couldn't re-list tasks before deleting projects.")
        for project in retire:
            leftovers = [t["id"] for t in remaining if t.get("project_id") == project["id"]]
            if leftovers:
                fail(f"Refusing to delete project {project['id']} '{project['title']}': still holds tasks {leftovers}.")
            response = _request("delete", f"/projects/{project['id']}")
            if isinstance(response, dict) or not response.ok:
                fail(f"Couldn't delete project {project['id']} '{project['title']}'.")
            print(f"   deleted {project['id']} {project['title']}")

    state = _read_state()
    if state.pop("triage_project_ids", None) is not None and not dry_run:
        _write_state(state)
        print("   dropped stale triage_project_ids from hood/vikunja_seen.json")

    print("4) Reclassification worklist — open tasks wearing 'ai can research':")
    tasks = tasks if dry_run else _all_tasks()
    if isinstance(tasks, dict):
        fail("Couldn't re-list tasks for the worklist.")
    worklist = [t for t in tasks if not t.get("done") and research_id in task_label_ids(t)]
    for task in worklist:
        print(f"   {task['id']:>4}  {task['title']}")
    print(f"   {len(worklist)} task(s). Swap the coding ones with:")
    print("   .venv/bin/python scripts/migrate_labels_only.py --set-code <id> <id> ...")
    print("✅ Done.")

if __name__ == "__main__":
    main()
